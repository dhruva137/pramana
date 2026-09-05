"""Execute ADMITted decisions: HOLD → Razorpay → CAPTURE | RELEASE | AMBIGUOUS."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Decision, Episode, Execution
from core.exec.razorpay_client import (
    FaultKind,
    PaymentResult,
    RazorpayAmbiguousError,
    RazorpayClient,
    RazorpayHttpError,
)
from core.ledger import service as ledger


def idempotency_key_for(decision_id: str) -> str:
    return hashlib.sha256(decision_id.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExecuteResult:
    decision_id: str
    state: str
    rzp_order_id: str | None
    rzp_payment_id: str | None
    idempotency_key: str
    last_error: str | None
    replayed: bool


class ExecuteError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_fault_header(value: str | None) -> FaultKind:
    if not value:
        return None
    v = value.strip().lower()
    if v in ("timeout", "http500", "dup"):
        return v  # type: ignore[return-value]
    raise ExecuteError("INVALID_FAULT", f"unknown X-Pramana-Fault: {value}")


async def execute_decision(
    session: AsyncSession,
    decision_id: str,
    *,
    client: RazorpayClient,
    fault: FaultKind = None,
) -> ExecuteResult:
    """HOLD under episode lock, then call Razorpay. Idempotent on decision_id."""
    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise ExecuteError("DECISION_NOT_FOUND", f"decision not found: {decision_id}")
    if decision.verdict != "ADMIT":
        raise ExecuteError(
            "NOT_ADMITTED",
            f"refuse execute: verdict is {decision.verdict}, require ADMIT",
        )

    idem_key = idempotency_key_for(decision_id)

    # Idempotent replay — never re-call Razorpay
    existing = await session.get(Execution, decision_id)
    if existing is not None:
        return ExecuteResult(
            decision_id=decision_id,
            state=existing.state,
            rzp_order_id=existing.rzp_order_id,
            rzp_payment_id=existing.rzp_payment_id,
            idempotency_key=existing.idempotency_key,
            last_error=existing.last_error,
            replayed=True,
        )

    # Also check unique idempotency_key (same decision always same key)
    by_key = await session.execute(
        select(Execution).where(Execution.idempotency_key == idem_key)
    )
    prior = by_key.scalar_one_or_none()
    if prior is not None:
        return ExecuteResult(
            decision_id=prior.decision_id,
            state=prior.state,
            rzp_order_id=prior.rzp_order_id,
            rzp_payment_id=prior.rzp_payment_id,
            idempotency_key=prior.idempotency_key,
            last_error=prior.last_error,
            replayed=True,
        )

    episode = await ledger.begin_episode_lock(session, decision.episode_id)
    if episode.status != "OPEN":
        raise ExecuteError(
            "EPISODE_NOT_OPEN",
            f"refuse execute: episode status is {episode.status}",
        )

    action = decision.action or {}
    amount_paise = int(action["amount_paise"])
    payee = action.get("payee") or {}
    payee_id = payee.get("merchant_id") or payee.get("payee_id")
    if not payee_id:
        raise ExecuteError("INVALID_ACTION", "action.payee.merchant_id required")
    currency = action.get("currency", "INR")
    category = action.get("category")

    # HOLD before Razorpay (I7)
    await ledger.hold(
        session,
        episode_id=episode.id,
        amount_paise=amount_paise,
        payee_id=payee_id,
        decision_id=decision_id,
        category=category,
        lock=False,  # already locked
    )

    execution = Execution(
        decision_id=decision_id,
        idempotency_key=idem_key,
        rzp_order_id=None,
        rzp_payment_id=None,
        state="PENDING",
        attempts=1,
        last_error=None,
        updated_at=_utcnow(),
    )
    session.add(execution)
    await session.flush()

    try:
        result = await client.create_order_and_pay(
            amount_paise=amount_paise,
            currency=currency,
            receipt=decision_id,
            idempotency_key=idem_key,
            notes={"decision_id": decision_id, "episode_id": episode.id},
            fault=fault,
        )
    except RazorpayAmbiguousError as exc:
        execution.state = "AMBIGUOUS"
        execution.rzp_order_id = exc.order_id
        execution.last_error = str(exc)
        execution.updated_at = _utcnow()
        episode.status = "QUARANTINED"
        # HOLD retained
        await session.flush()
        return _to_result(execution, replayed=False)

    except RazorpayHttpError as exc:
        # Definite failure → RELEASE hold
        await ledger.release(
            session,
            episode_id=episode.id,
            amount_paise=amount_paise,
            payee_id=payee_id,
            decision_id=decision_id,
            category=category,
            lock=False,
        )
        execution.state = "FAILED"
        execution.last_error = f"http{exc.status_code}: {exc}"
        execution.updated_at = _utcnow()
        await session.flush()
        return _to_result(execution, replayed=False)

    # Success → CAPTURE
    await _apply_success(session, episode, execution, result, amount_paise, payee_id, category)
    return _to_result(execution, replayed=False)


async def _apply_success(
    session: AsyncSession,
    episode: Episode,
    execution: Execution,
    result: PaymentResult,
    amount_paise: int,
    payee_id: str,
    category: str | None,
) -> None:
    await ledger.capture(
        session,
        episode_id=episode.id,
        amount_paise=amount_paise,
        payee_id=payee_id,
        decision_id=execution.decision_id,
        category=category,
        lock=False,
    )
    execution.state = "SUCCEEDED"
    execution.rzp_order_id = result.order_id
    execution.rzp_payment_id = result.payment_id
    execution.last_error = None
    execution.updated_at = _utcnow()
    await session.flush()


def _to_result(execution: Execution, *, replayed: bool) -> ExecuteResult:
    return ExecuteResult(
        decision_id=execution.decision_id,
        state=execution.state,
        rzp_order_id=execution.rzp_order_id,
        rzp_payment_id=execution.rzp_payment_id,
        idempotency_key=execution.idempotency_key,
        last_error=execution.last_error,
        replayed=replayed,
    )


def execution_to_dict(result: ExecuteResult) -> dict[str, Any]:
    return {
        "decision_id": result.decision_id,
        "state": result.state,
        "rzp_order_id": result.rzp_order_id,
        "rzp_payment_id": result.rzp_payment_id,
        "idempotency_key": result.idempotency_key,
        "last_error": result.last_error,
        "replayed": result.replayed,
    }

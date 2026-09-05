"""Resolve AMBIGUOUS executions via fetch_order_payments; settle HOLD→CAPTURE|RELEASE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Decision, Episode, Execution
from core.exec.razorpay_client import RazorpayClient
from core.ledger import service as ledger


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ReconcileResult:
    decision_id: str
    previous_state: str
    new_state: str
    resolved: bool
    detail: str


async def reconcile_execution(
    session: AsyncSession,
    decision_id: str,
    *,
    client: RazorpayClient,
) -> ReconcileResult:
    """Probe Razorpay for an AMBIGUOUS execution and settle the ledger."""
    execution = await session.get(Execution, decision_id)
    if execution is None:
        raise LookupError(f"execution not found: {decision_id}")
    if execution.state != "AMBIGUOUS":
        return ReconcileResult(
            decision_id=decision_id,
            previous_state=execution.state,
            new_state=execution.state,
            resolved=False,
            detail="not AMBIGUOUS",
        )

    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise LookupError(f"decision not found: {decision_id}")

    episode = await ledger.begin_episode_lock(session, decision.episode_id)
    action = decision.action or {}
    amount_paise = int(action["amount_paise"])
    payee = action.get("payee") or {}
    payee_id = payee.get("merchant_id") or payee.get("payee_id")
    category = action.get("category")
    prev = execution.state

    order_id = execution.rzp_order_id
    if not order_id:
        # Nothing was sent / no order id — treat as definite failure
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
        execution.last_error = (execution.last_error or "") + "; reconcile: no order_id"
        execution.updated_at = _utcnow()
        if episode.status == "QUARANTINED":
            episode.status = "OPEN"
        await session.flush()
        return ReconcileResult(
            decision_id=decision_id,
            previous_state=prev,
            new_state="FAILED",
            resolved=True,
            detail="no order_id → RELEASE",
        )

    payments = await client.fetch_order_payments(order_id)
    captured = [
        p
        for p in payments
        if str(p.get("status", "")).lower() in ("captured", "authorized", "paid")
    ]

    if captured:
        pay = captured[0]
        await ledger.capture(
            session,
            episode_id=episode.id,
            amount_paise=amount_paise,
            payee_id=payee_id,
            decision_id=decision_id,
            category=category,
            lock=False,
        )
        execution.state = "SUCCEEDED"
        execution.rzp_payment_id = str(pay.get("id") or execution.rzp_payment_id)
        execution.last_error = None
        execution.updated_at = _utcnow()
        if episode.status == "QUARANTINED":
            episode.status = "OPEN"
        await session.flush()
        return ReconcileResult(
            decision_id=decision_id,
            previous_state=prev,
            new_state="SUCCEEDED",
            resolved=True,
            detail=f"order {order_id} has captured payment",
        )

    # No successful payment — definite miss → RELEASE
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
    execution.last_error = (execution.last_error or "") + "; reconcile: no payment on order"
    execution.updated_at = _utcnow()
    if episode.status == "QUARANTINED":
        episode.status = "OPEN"
    await session.flush()
    return ReconcileResult(
        decision_id=decision_id,
        previous_state=prev,
        new_state="FAILED",
        resolved=True,
        detail=f"order {order_id} has no captured payment → RELEASE",
    )


async def reconcile_all_ambiguous(
    session: AsyncSession,
    *,
    client: RazorpayClient,
) -> list[ReconcileResult]:
    result = await session.execute(select(Execution).where(Execution.state == "AMBIGUOUS"))
    rows = list(result.scalars().all())
    out: list[ReconcileResult] = []
    for ex in rows:
        out.append(await reconcile_execution(session, ex.decision_id, client=client))
    return out

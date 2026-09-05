"""Episode / authorize / proof persistence helpers."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.api.constants import MERCHANT_RECORDS
from core.api.ctx_ledger import append_context_entry, load_ctx_ledger
from core.api.schemas import normalize_episode_mode
from core.api.seal_fix import attach_seal_pubkey, envelope_for_gate
from core.config import Settings
from core.db.models import Decision, Episode, Proof
from core.gate import evaluate
from core.gate.rules import genesis_hash
from core.gate.types import Decision as GateDecision
from core.ledger import service as ledger
from core.proof.builder import build_dvp
from core.seal.sealer import ContextTaintedError, SealRequest, seal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _provenance_for_gate(
    provenance: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if provenance is None:
        return None
    if isinstance(provenance, list):
        return {"records": {str(r.get("field", i)): r for i, r in enumerate(provenance)}}
    if "records" in provenance:
        return provenance
    return provenance


def _provenance_list(
    provenance: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if provenance is None:
        return []
    if isinstance(provenance, list):
        return list(provenance)
    records = provenance.get("records") if "records" in provenance else provenance
    if isinstance(records, dict):
        out = []
        for k, v in records.items():
            if isinstance(v, dict):
                rec = dict(v)
                rec.setdefault("field", k)
                out.append(rec)
        return out
    return []


def _decision_hash(prev: str, body: dict[str, Any]) -> str:
    material = prev.encode("utf-8") + hashlib.sha256(
        repr(sorted(body.items())).encode("utf-8")
    ).digest()
    return hashlib.sha256(material).hexdigest()


def ledger_state_to_gate(state: Any) -> dict[str, Any]:
    return {
        "exposure_paise": int(state.exposure_paise),
        "txn_count": int(state.txn_count),
        "distinct_payees": sorted(state.distinct_payees),
        "committed_paise": int(state.committed_paise),
        "held_paise": int(state.held_paise),
    }


async def create_sealed_episode(
    session: AsyncSession,
    settings: Settings,
    *,
    utterance: str,
    user_ref: str,
    consent_ref: str,
    consent_cap_paise: int,
    agent_id: str = "agt_claude_demo",
    mode: str = "PRAMANA_ON",
    delivery_address_hash: str = "sha256:demo_address",
    allowed_instruments: list[str] | None = None,
    force_mock: bool | None = None,
    episode_id: str | None = None,
) -> tuple[Episode, dict[str, Any], list[dict[str, Any]]]:
    """Seal utterance, persist episode + initial USER context entry."""
    ep_id = episode_id or f"ep_{ULID()}"
    instruments = allowed_instruments or ["upi_reserve_pay:tok_x"]
    use_mock = force_mock if force_mock is not None else settings.mock_mode

    # Placeholder episode so FK for context ledger exists
    now = _utcnow()
    placeholder = Episode(
        id=ep_id,
        user_ref=user_ref,
        agent_id=agent_id,
        status="OPEN",
        envelope={},
        envelope_sig="",
        envelope_kid=settings.pramana_seal_kid,
        ctx_ledger_head=genesis_hash(ep_id),
        seal_index=0,
        mode=normalize_episode_mode(mode),
        created_at=now,
        expires_at=now,
    )
    session.add(placeholder)
    await session.flush()

    ctx0 = await append_context_entry(
        session,
        episode_id=ep_id,
        role="user",
        taint="USER",
        content=utterance,
        source_uri="user://utterance",
    )

    try:
        result = seal(
            SealRequest(
                utterance=utterance,
                user_ref=user_ref,
                consent_ref=consent_ref,
                consent_cap_paise=consent_cap_paise,
                agent_id=agent_id,
                episode_id=ep_id,
                delivery_address_hash=delivery_address_hash,
                allowed_instruments=instruments,
                ledger_head=ctx0["hash"],
                seal_index=0,
                ctx_entries=[ctx0],
                seal_sk_b64=settings.pramana_seal_sk,
                kid=settings.pramana_seal_kid,
                force_mock=use_mock,
                now=now,
            )
        )
    except ContextTaintedError:
        raise

    # Store the envelope in EXACTLY the form that was signed. SealedIntentEnvelope
    # .without_seal() dumps with exclude_none=True, so dumping without it here left
    # null predicate bounds in the stored copy — different bytes, R1 false-DENY, and
    # an int(None) crash in R7. Do not "fix" that downstream by re-signing.
    env = result.envelope.model_dump(mode="json", by_alias=True, exclude_none=True)
    env = attach_seal_pubkey(env, seal_sk_raw=settings.seal_sk_raw())

    seal_block = env.get("seal") or {}
    placeholder.envelope = env
    placeholder.envelope_sig = str(seal_block.get("sig") or "")
    placeholder.envelope_kid = str(seal_block.get("kid") or settings.pramana_seal_kid)
    placeholder.ctx_ledger_head = ctx0["hash"]
    placeholder.seal_index = 0
    placeholder.created_at = result.envelope.created_at
    placeholder.expires_at = result.envelope.expires_at
    await session.flush()

    ctx = await load_ctx_ledger(session, ep_id)
    return placeholder, env, ctx


async def authorize_action(
    session: AsyncSession,
    settings: Settings,
    *,
    episode_id: str,
    action: dict[str, Any],
    provenance: dict[str, Any] | list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Run gate.evaluate at the API boundary (inject now=).

    Always returns a verdict payload (HTTP 200). On DENY/ESCALATE builds a DVP.

    Gate evaluation + decision persist run under ``ledger.begin_episode_lock``
    (same lock as execute) so concurrent authorize/execute cannot race R6 on a
    stale ledger snapshot.
    """
    try:
        episode = await ledger.begin_episode_lock(session, episode_id)
    except LookupError:
        return {
            "ok": False,
            "error": {"code": "EPISODE_NOT_FOUND", "message": f"unknown episode {episode_id}"},
        }
    if episode.status not in ("OPEN",):
        return {
            "ok": False,
            "error": {
                "code": "EPISODE_NOT_OPEN",
                "message": f"episode status is {episode.status}",
            },
            "episode_status": episode.status,
        }

    when = now or _utcnow()
    envelope = dict(episode.envelope or {})
    ctx = await load_ctx_ledger(session, episode_id)
    state = await ledger.get_ledger_state(session, episode_id)
    ledger_before = ledger_state_to_gate(state)

    act = dict(action)
    if "human_confirmed" not in act and action.get("human_confirmed") is not None:
        act["human_confirmed"] = bool(action["human_confirmed"])

    mode = (episode.mode or "PRAMANA_ON").upper()
    t0 = time.perf_counter()

    if mode == "BASELINE":
        # Demo "gate off": agent executes freely (scare screen). The fair AP2-shaped
        # baseline arm lives in bench/ — not this console toggle.
        amount = int(act.get("amount_paise") or 0)
        if amount <= 0:
            gate_decision = GateDecision(
                verdict="DENY",
                rule_id="BASELINE_INVALID_AMOUNT",
                rule_trace=(),
                ruleset_version="baseline-demo-1.0",
            )
        else:
            gate_decision = GateDecision(
                verdict="ADMIT",
                rule_id=None,
                rule_trace=(),
                ruleset_version="baseline-demo-1.0",
            )
    else:
        env_gate = envelope_for_gate(envelope, MERCHANT_RECORDS)
        gate_decision = evaluate(
            env_gate,
            act,
            _provenance_for_gate(provenance),
            ledger_before,
            ctx,
            when,
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Decision chain
    prior = await session.execute(
        select(Decision)
        .where(Decision.episode_id == episode_id)
        .order_by(Decision.created_at.asc())
    )
    prior_rows = list(prior.scalars().all())
    prev_hash = prior_rows[-1].hash if prior_rows else ("0" * 64)
    decision_id = f"dec_{ULID()}"
    body = {
        "decision_id": decision_id,
        "verdict": gate_decision.verdict,
        "rule_id": gate_decision.rule_id,
        "action": act,
    }
    dec_hash = _decision_hash(prev_hash, body)

    row = Decision(
        id=decision_id,
        episode_id=episode_id,
        action=act,
        provenance=_provenance_for_gate(provenance) or {},
        verdict=gate_decision.verdict,
        rule_id=gate_decision.rule_id,
        rule_trace=[r.as_dict() for r in gate_decision.rule_trace],
        ledger_before=ledger_before,
        latency_ms=latency_ms,
        prev_hash=prev_hash,
        hash=dec_hash,
        created_at=when,
    )
    session.add(row)
    await session.flush()

    proof_id = None
    proof_doc = None
    if gate_decision.verdict in ("DENY", "ESCALATE") and mode != "BASELINE":
        proof_doc, proof_id = await _persist_proof(
            session,
            settings,
            episode=episode,
            decision_row=row,
            gate_decision=gate_decision,
            ctx=ctx,
            provenance=provenance,
            when=when,
            prior_rows=prior_rows,
        )
        if gate_decision.verdict == "DENY" and gate_decision.rule_id == "R6":
            episode.status = "FROZEN"

    await session.flush()
    return {
        "ok": True,
        "decision_id": decision_id,
        "episode_id": episode_id,
        "verdict": gate_decision.verdict,
        "rule_id": gate_decision.rule_id,
        "ruleset_version": gate_decision.ruleset_version,
        "rule_trace": [r.as_dict() for r in gate_decision.rule_trace],
        "ledger_before": ledger_before,
        "latency_ms": latency_ms,
        "proof_id": proof_id,
        "proof": proof_doc,
        "mode": mode,
    }


async def _persist_proof(
    session: AsyncSession,
    settings: Settings,
    *,
    episode: Episode,
    decision_row: Decision,
    gate_decision: GateDecision,
    ctx: list[dict[str, Any]],
    provenance: dict[str, Any] | list[dict[str, Any]] | None,
    when: datetime,
    prior_rows: list[Decision],
) -> tuple[dict[str, Any], str]:
    decision_entries = [
        {
            "index": i,
            "decision_id": d.id,
            "verdict": d.verdict,
            "rule_id": d.rule_id,
        }
        for i, d in enumerate([*prior_rows, decision_row])
    ]
    state = await ledger.get_ledger_state(session, episode.id)
    entries = await ledger.load_entries(session, episode.id)
    snap = {
        "entries": [
            {
                "kind": e.kind,
                "amount_paise": e.amount_paise,
                "payee_id": e.payee_id,
                "decision_id": e.decision_id,
            }
            for e in entries
        ],
        "exposure_paise": state.exposure_paise,
        "txn_count": state.txn_count,
        "distinct_payees": len(state.distinct_payees),
        "payee_ids": sorted(state.distinct_payees),
    }
    decision_dict = {
        "decision_id": decision_row.id,
        "verdict": gate_decision.verdict,
        "rule_id": gate_decision.rule_id,
        "rule_trace": [r.as_dict() for r in gate_decision.rule_trace],
        "ruleset_version": gate_decision.ruleset_version,
    }
    issued = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = build_dvp(
        episode={
            "episode_id": episode.id,
            "user_ref": episode.user_ref,
            "agent_id": episode.agent_id,
        },
        envelope=dict(episode.envelope or {}),
        action=decision_row.action,
        decision=decision_dict,
        provenance=_provenance_list(provenance),
        ctx_ledger=[
            {**e, "index": e.get("idx", e.get("index", 0))} for e in ctx
        ],
        episode_ledger_snapshot=snap,
        decision_entries=decision_entries,
        proof_private_key=settings.proof_private_key(),
        proof_kid=settings.pramana_proof_kid,
        now=issued,
        merchant_records=MERCHANT_RECORDS,
        mode=episode.mode,
    )
    proof_id = str(doc.get("dvp_id") or f"dvp_{ULID()}")
    sig = (doc.get("signature") or {}).get("sig") or ""
    kid = (doc.get("signature") or {}).get("kid") or settings.pramana_proof_kid
    session.add(
        Proof(
            id=proof_id,
            episode_id=episode.id,
            decision_id=decision_row.id,
            document=doc,
            signature=str(sig),
            kid=str(kid),
            created_at=when,
        )
    )
    await session.flush()
    return doc, proof_id


async def episode_snapshot(session: AsyncSession, episode_id: str) -> dict[str, Any] | None:
    episode = await session.get(Episode, episode_id)
    if episode is None:
        return None
    state = await ledger.get_ledger_state(session, episode_id)
    ctx = await load_ctx_ledger(session, episode_id)
    decs = await session.execute(
        select(Decision)
        .where(Decision.episode_id == episode_id)
        .order_by(Decision.created_at.asc())
    )
    decisions = [
        {
            "id": d.id,
            "verdict": d.verdict,
            "rule_id": d.rule_id,
            "action": d.action,
            "latency_ms": d.latency_ms,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in decs.scalars().all()
    ]
    return {
        "episode_id": episode.id,
        "status": episode.status,
        "mode": episode.mode,
        "envelope": episode.envelope,
        "seal_index": episode.seal_index,
        "ctx_ledger_head": episode.ctx_ledger_head,
        "ledger": ledger_state_to_gate(state),
        "context_ledger": ctx,
        "decisions": decisions,
        "created_at": episode.created_at.isoformat() if episode.created_at else None,
        "expires_at": episode.expires_at.isoformat() if episode.expires_at else None,
    }

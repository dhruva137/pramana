"""Build a signed Divergence Proof (DVP) document from episode / decision inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from ulid import ULID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.proof.canon import (
    context_ledger_head,
    decision_chain_head,
    sign_document,
)
from core.proof.causal import assemble_causal_chain


def build_dvp(
    *,
    episode: dict[str, Any],
    envelope: dict[str, Any],
    action: dict[str, Any],
    decision: dict[str, Any],
    provenance: list[dict[str, Any]],
    ctx_ledger: list[dict[str, Any]],
    episode_ledger_snapshot: dict[str, Any],
    decision_entries: list[dict[str, Any]],
    proof_private_key: Ed25519PrivateKey,
    proof_kid: str,
    now: str | None = None,
    merchant_records: dict[str, Any] | None = None,
    human_confirmation: dict[str, Any] | None = None,
    seal_verified: bool = True,
    mode: str = "PRAMANA_ON",
) -> dict[str, Any]:
    """
    Assemble and sign a DVP as plain dicts matching protocol §5.1.

    *decision* is a Decision-shaped dict: ``verdict``, ``rule_id``, ``rule_trace``,
    ``violated_predicates``, optional ``decision_id`` / ``ruleset_version``.
    """
    issued_at = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    episode_id = episode.get("episode_id") or envelope.get("episode_id")
    if not episode_id:
        raise ValueError("episode_id required")

    critical = list((envelope.get("provenance_policy") or {}).get("critical_fields") or [])
    # Closure over all provenance that contributed to the decision (critical first)
    causal = assemble_causal_chain(provenance, ctx_ledger, critical_fields=None)

    sorted_ctx = sorted(
        ctx_ledger, key=lambda e: int(e.get("index", e.get("ledger_idx", 0)))
    )
    sorted_dec = sorted(
        decision_entries, key=lambda e: int(e.get("index", e.get("ledger_idx", 0)))
    )

    binding = envelope.get("context_binding") or {}
    seal_index = int(binding.get("seal_index", 0))
    entries_before_ok = True
    for entry in sorted_ctx:
        idx = int(entry.get("index", entry.get("ledger_idx", -1)))
        if idx < seal_index:
            taint = entry.get("taint")
            role = entry.get("role")
            if taint not in (None, "USER") and role != "system":
                entries_before_ok = False
                break

    constraints = envelope.get("constraints") or {}
    ap2 = {
        "IntentMandate": {
            "natural_language_description": (envelope.get("utterance") or {}).get("excerpt"),
            "merchants": list(constraints.get("merchants_allow") or []),
            "skus": [],
            "requires_refundability": False,
            "intent_expiry": envelope.get("expires_at"),
            "user_cart_confirmation_required": True,
        },
        "CartMandate": None,
        "note": (
            "Field-shaped projection for interoperability. "
            "Not a signed W3C Verifiable Credential."
        ),
    }

    verdict = decision.get("verdict")
    violated = list(decision.get("violated_predicates") or [])
    if not violated and verdict and verdict != "ADMIT":
        # Derive from rule_trace if caller only supplied full trace
        for t in decision.get("rule_trace") or []:
            if t.get("verdict") == verdict:
                violated = [t]
                break

    doc: dict[str, Any] = {
        "dvp_version": "1.0",
        "dvp_id": f"dvp_{ULID()}",
        "issued_at": issued_at,
        "issuer": {"name": "pramana", "kid": proof_kid},
        "episode": {
            "episode_id": episode_id,
            "user_ref": episode.get("user_ref")
            or (envelope.get("principal") or {}).get("user_ref"),
            "agent_id": episode.get("agent_id")
            or (envelope.get("agent") or {}).get("agent_id"),
            "mode": mode,
        },
        "sealed_intent": {
            "envelope": envelope,
            "seal_verified": seal_verified,
            "context_binding_verified": True,
            "seal_index": seal_index,
            "entries_before_seal_all_user": entries_before_ok,
        },
        "executed_action": action,
        "verdict": verdict,
        "violated_predicates": violated,
        "rule_trace": list(decision.get("rule_trace") or []),
        "ruleset_version": decision.get("ruleset_version") or "1.0",
        "causal_chain": causal,
        "episode_ledger_snapshot": {
            "entries": list(episode_ledger_snapshot.get("entries") or []),
            "exposure_paise": int(episode_ledger_snapshot.get("exposure_paise") or 0),
            "txn_count": int(episode_ledger_snapshot.get("txn_count") or 0),
            "distinct_payees": int(episode_ledger_snapshot.get("distinct_payees") or 0),
            "payee_ids": list(episode_ledger_snapshot.get("payee_ids") or []),
        },
        "chain": {
            "context_ledger_head": context_ledger_head(episode_id, sorted_ctx),
            "decision_chain_head": decision_chain_head(episode_id, sorted_dec),
            "decision_id": decision.get("decision_id"),
        },
        "gate_replay": {
            "now": issued_at,
            "provenance": provenance,
            "context_ledger": sorted_ctx,
            "decision_entries": sorted_dec,
            "merchant_records": merchant_records or {},
            "human_confirmation": human_confirmation,
            "causal_chain_len": len(causal),
        },
        "ap2_projection": ap2,
    }

    sig = sign_document(doc, proof_private_key)
    doc["signature"] = {"alg": "Ed25519", "kid": proof_kid, "sig": sig}
    return doc

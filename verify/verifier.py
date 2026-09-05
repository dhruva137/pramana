"""Offline Divergence Proof verifier (no network, no DB, no core imports)."""

from __future__ import annotations

from typing import Any

from verify.hash import (
    CTX_GENESIS,
    context_ledger_head,
    decision_chain_head,
    excerpt_sha,
    head_at_index,
)
from verify.rules import evaluate
from verify.sign import load_jwks, verify_jcs


#: Envelope keys attached at runtime AFTER sealing, and therefore not part of the
#: signed body: the seal itself, the embedded public key, the merchant registry
#: injected for R3/R4, and the golden-fixture test hooks.
#: Declared here rather than imported from ``core`` — invariant I6 requires this
#: package to stay independent. It mirrors ``core.gate.rules._UNSEALED_KEYS``;
#: ``tests/unit/verify/test_verifier.py`` pins the two together.
UNSEALED_ENVELOPE_KEYS = frozenset(
    {"seal", "_seal_pub", "_test", "_test_pub", "seal_ok", "merchant_records"}
)


class VerifyError(Exception):
    """Raised when a named check fails. ``.check`` names the failing check."""

    def __init__(self, check: str, message: str) -> None:
        self.check = check
        super().__init__(f"{check}: {message}")


def verify_proof(document: dict[str, Any], jwks: str | dict[str, Any]) -> None:
    """
    Verify a DVP document against JWKS.

    Checks (in order):
      1. signature — Ed25519 over JCS(document without signature)
      2. envelope_seal — envelope seal signature
      3. context_ledger_head — recomputed from included entries
      4. decision_chain_head — recomputed from included entries
      5. rules_replay — independent R1–R12 reaches same verdict
      6. excerpt_hashes — every causal_chain excerpt matches excerpt_sha
      7. causal_chain_closure — provenance closure not truncated
    """
    keys = load_jwks(jwks)

    # --- 1. document signature ---
    sig_block = document.get("signature") or {}
    kid = sig_block.get("kid")
    sig = sig_block.get("sig")
    if not kid or not sig:
        raise VerifyError("signature", "missing signature.kid or signature.sig")
    if kid not in keys:
        raise VerifyError("signature", f"unknown kid {kid!r}")
    body = {k: v for k, v in document.items() if k != "signature"}
    if not verify_jcs(body, str(sig), keys[kid]):
        raise VerifyError("signature", "invalid proof signature")

    # Version gate
    dvp_version = str(document.get("dvp_version") or "")
    if not dvp_version.startswith("1."):
        raise VerifyError("signature", f"unknown dvp_version {dvp_version!r}")

    sealed = document.get("sealed_intent") or {}
    envelope = sealed.get("envelope") or {}
    replay = document.get("gate_replay") or {}
    episode = document.get("episode") or {}
    episode_id = episode.get("episode_id") or envelope.get("episode_id") or ""

    # --- 2. envelope seal ---
    seal = envelope.get("seal") or {}
    seal_kid = seal.get("kid")
    seal_sig = seal.get("sig")
    if not seal_kid or not seal_sig:
        raise VerifyError("envelope_seal", "missing envelope seal")
    if seal_kid not in keys:
        raise VerifyError("envelope_seal", f"unknown seal kid {seal_kid!r}")
    env_body = {k: v for k, v in envelope.items() if k not in UNSEALED_ENVELOPE_KEYS}
    if not verify_jcs(env_body, str(seal_sig), keys[seal_kid]):
        raise VerifyError("envelope_seal", "invalid envelope seal signature")

    # --- 3. context ledger head ---
    ctx_entries = list(replay.get("context_ledger") or document.get("context_ledger") or [])
    chain = document.get("chain") or {}
    expected_ctx = chain.get("context_ledger_head")
    if expected_ctx is None:
        raise VerifyError("context_ledger_head", "missing chain.context_ledger_head")
    got_ctx = context_ledger_head(episode_id, _sorted_entries(ctx_entries))
    if got_ctx != expected_ctx:
        raise VerifyError(
            "context_ledger_head",
            f"recomputed {got_ctx} != claimed {expected_ctx}",
        )
    # Binding consistency at seal_index
    binding = envelope.get("context_binding") or {}
    seal_index = int(binding.get("seal_index", 0))
    if binding.get("ledger_head"):
        at_seal = head_at_index(CTX_GENESIS, episode_id, ctx_entries, seal_index)
        if at_seal != binding["ledger_head"]:
            raise VerifyError(
                "context_ledger_head",
                f"seal binding head {binding['ledger_head']} != recomputed {at_seal}",
            )

    # --- 4. decision chain head ---
    dec_entries = list(replay.get("decision_entries") or document.get("decision_entries") or [])
    expected_dec = chain.get("decision_chain_head")
    if expected_dec is None:
        raise VerifyError("decision_chain_head", "missing chain.decision_chain_head")
    got_dec = decision_chain_head(episode_id, _sorted_entries(dec_entries))
    if got_dec != expected_dec:
        raise VerifyError(
            "decision_chain_head",
            f"recomputed {got_dec} != claimed {expected_dec}",
        )

    # --- 5. rules replay ---
    action = document.get("executed_action") or {}
    provenance = list(replay.get("provenance") or document.get("provenance") or [])
    ledger_snap = document.get("episode_ledger_snapshot") or {}
    ledger_state = {
        "exposure_paise": ledger_snap.get("exposure_paise", 0),
        "txn_count": ledger_snap.get("txn_count", 0),
        "distinct_payees": ledger_snap.get("distinct_payees", 0),
        "payee_ids": ledger_snap.get("payee_ids") or [],
    }
    now = str(replay.get("now") or document.get("issued_at") or "")
    seal_pk = keys[seal_kid].public_bytes_raw()
    decision = evaluate(
        envelope,
        action,
        provenance,
        ledger_state,
        ctx_entries,
        now,
        seal_public_key_raw=seal_pk,
        merchant_records=replay.get("merchant_records") or {},
        human_confirmation=replay.get("human_confirmation"),
        episode_id=episode_id,
    )
    claimed = document.get("verdict")
    if decision["verdict"] != claimed:
        raise VerifyError(
            "rules_replay",
            f"recomputed verdict {decision['verdict']} != claimed {claimed}",
        )

    # --- 6. excerpt hashes ---
    causal = list(document.get("causal_chain") or [])
    for step in causal:
        excerpt = step.get("excerpt")
        claimed_sha = step.get("excerpt_sha")
        if excerpt is None or claimed_sha is None:
            raise VerifyError("excerpt_hashes", f"step {step.get('step')} missing excerpt/sha")
        got = excerpt_sha(str(excerpt))
        if got != claimed_sha:
            raise VerifyError(
                "excerpt_hashes",
                f"step {step.get('step')}: {got} != {claimed_sha}",
            )

    # --- 7. causal chain covers provenance closure (truncation check) ---
    critical = list((envelope.get("provenance_policy") or {}).get("critical_fields") or [])
    needed: set[int] = set()
    for rec in provenance:
        if rec.get("field") in critical and rec.get("ledger_idx") is not None:
            needed.add(int(rec["ledger_idx"]))
    present = {
        int(s["ledger_idx"])
        for s in causal
        if s.get("ledger_idx") is not None
    }
    missing = needed - present
    if missing:
        raise VerifyError(
            "causal_chain_closure",
            f"truncated causal chain; missing ledger_idx {sorted(missing)}",
        )

    expected_len = replay.get("causal_chain_len")
    if expected_len is not None and len(causal) != int(expected_len):
        raise VerifyError(
            "causal_chain_closure",
            f"causal_chain length {len(causal)} != expected {expected_len}",
        )


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda e: int(e.get("index", e.get("ledger_idx", 0))),
    )

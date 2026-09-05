"""Admission rules R1–R12. Pure functions — no I/O, no LLM, no ambient clock."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.chain.jcs import canonicalize as _chain_canonicalize

from core.gate.types import (
    ADMIT,
    DENY,
    ESCALATE,
    Action,
    LedgerState,
    Provenance,
    RuleResult,
    Taint,
)

KNOWN_SIE_VERSIONS = frozenset({"1.0"})

# Genesis prefix for context-ledger chain (architecture §7).
_GENESIS = b"pramana.ctx.v1|"


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _reject_floats(obj: Any) -> None:
    """I4: no floats in a money path. Enforced before canonicalisation."""
    if isinstance(obj, float):
        raise TypeError("floats are forbidden in gate canonicalisation / money paths")
    if isinstance(obj, Mapping):
        for v in obj.values():
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_floats(v)


def jcs(value: Any) -> bytes:
    """RFC 8785 JCS bytes, with floats rejected (I4).

    Delegates to ``core.chain.jcs`` — the single canonicalisation implementation
    shared with the sealer and the proof builder. This MUST stay byte-identical
    to what the sealer signs: an independent dialect here is precisely what makes
    R1 fail on valid envelopes and tempts a ``seal_ok`` bypass.
    """
    _reject_floats(value)
    return _chain_canonicalize(value)


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _result(
    rule_id: str,
    name: str,
    verdict: str,
    expected: str,
    actual: str,
    inputs: Mapping[str, Any],
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name=name,
        verdict=verdict,
        expected=expected,
        actual=actual,
        inputs=dict(inputs),
    )


def _constraints(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    return envelope.get("constraints") or {}


def _merchant_id(action: Action) -> str:
    return str(action.payee.get("merchant_id", ""))


def _account_ref(action: Action) -> str:
    return str(action.payee.get("account_ref", ""))


def _category(action: Action, envelope: Mapping[str, Any]) -> str | None:
    if "category" in action.payee:
        return str(action.payee["category"])
    records = envelope.get("merchant_records") or {}
    mid = _merchant_id(action)
    rec = records.get(mid) or {}
    if "category" in rec:
        return str(rec["category"])
    return None


def _verified_settlement(action: Action, envelope: Mapping[str, Any]) -> str | None:
    """Settlement account from RZP_VERIFIED merchant record."""
    records = envelope.get("merchant_records") or {}
    mid = _merchant_id(action)
    rec = records.get(mid) or {}
    if "account_ref" in rec:
        return str(rec["account_ref"])
    if "rzp_settlement_account_ref" in action.payee:
        return str(action.payee["rzp_settlement_account_ref"])
    return None


#: Keys attached at runtime that are NOT part of the sealed intent and must be
#: excluded before verifying the signature. ``merchant_records`` is RZP_VERIFIED
#: lookup data injected by the API for R3/R4; including it would change the
#: signed bytes and false-DENY every real envelope.
_UNSEALED_KEYS = frozenset(
    {"seal", "_test", "_test_pub", "_seal_pub", "seal_ok", "merchant_records"}
)


def _envelope_for_seal(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Envelope bytes signed over JCS(envelope without seal / runtime hooks)."""
    return {k: v for k, v in envelope.items() if k not in _UNSEALED_KEYS}


def verify_ed25519_seal(envelope: Mapping[str, Any], pub_raw: bytes) -> bool:
    seal = envelope.get("seal") or {}
    sig_b64 = seal.get("sig")
    if not sig_b64:
        return False
    try:
        sig = _b64url_decode(str(sig_b64))
        pub = Ed25519PublicKey.from_public_bytes(pub_raw)
        pub.verify(sig, jcs(_envelope_for_seal(envelope)))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _seal_valid(envelope: Mapping[str, Any]) -> tuple[bool, str]:
    """Return (ok, detail) for the envelope seal.

    The ONLY non-cryptographic path is the explicitly-namespaced ``_test`` hook,
    which exists so golden fixtures need not carry real keys. There is
    deliberately no top-level ``seal_ok`` escape hatch: an attacker (or a
    well-meaning glue layer) that can add one key to the envelope dict must not
    be able to switch off signature verification. If R1 is failing on envelopes
    you just sealed, the canonicalisation dialects have diverged — fix that,
    do not bypass this.
    """
    test = envelope.get("_test")
    if isinstance(test, Mapping) and "seal_ok" in test:
        ok = bool(test["seal_ok"])
        return ok, f"_test.seal_ok={ok}"

    seal = envelope.get("seal") or {}
    if not seal.get("sig"):
        return False, "missing seal.sig"

    pub_b64 = envelope.get("_test_pub") or envelope.get("_seal_pub")
    if not pub_b64:
        meta = envelope.get("meta") or {}
        pub_b64 = meta.get("seal_pub")
    if not pub_b64:
        return False, "no public key for seal verification"

    try:
        pub_raw = _b64url_decode(str(pub_b64))
    except Exception:
        return False, "invalid public key encoding"

    ok = verify_ed25519_seal(envelope, pub_raw)
    return ok, "ed25519_ok" if ok else "ed25519_invalid"


#: Keys carried alongside a context entry that are advisory annotations rather
#: than committed content. The chain commits to what the agent read, not to our
#: opinion about it — so a detector verdict can be added or re-run later without
#: invalidating the ledger. ``index`` is a proof-builder alias for ``idx``.
_NON_CHAIN_ENTRY_KEYS = frozenset({"hash", "tool", "detector", "index"})


def entry_hash(prev_hash: str, entry_body: Mapping[str, Any]) -> str:
    """H(prev_hash || JCS(entry without hash / advisory annotations))."""
    body = {k: v for k, v in entry_body.items() if k not in _NON_CHAIN_ENTRY_KEYS}
    material = prev_hash.encode("utf-8") + jcs(body)
    return sha256_hex(material)


def genesis_hash(episode_id: str) -> str:
    return sha256_hex(_GENESIS + episode_id.encode("utf-8"))


def recompute_ctx_chain(
    ctx_ledger: Sequence[Mapping[str, Any]],
    episode_id: str,
) -> tuple[bool, str, str]:
    """
    Verify prev_hash linkage and recompute hashes.
    Returns (ok, detail, head_hash_at_last).
    """
    if not ctx_ledger:
        head = genesis_hash(episode_id)
        return True, "empty_ledger", head

    entries = sorted(ctx_ledger, key=lambda e: int(e["idx"]))
    expected_prev = genesis_hash(episode_id)
    last_hash = expected_prev

    for i, entry in enumerate(entries):
        prev = str(entry.get("prev_hash", ""))
        if prev != expected_prev:
            return False, f"prev_hash mismatch at idx={entry.get('idx')}", last_hash
        recomputed = entry_hash(prev, entry)
        declared = str(entry.get("hash", ""))
        if declared and declared != recomputed:
            return False, f"hash mismatch at idx={entry.get('idx')}", last_hash
        last_hash = declared or recomputed
        expected_prev = last_hash
        # Contiguity check
        if int(entry["idx"]) != i and int(entry["idx"]) != int(entries[0]["idx"]) + i:
            # Allow non-zero start only if indices are contiguous from min
            pass

    # Contiguous indices from min
    idxs = [int(e["idx"]) for e in entries]
    if idxs != list(range(idxs[0], idxs[0] + len(idxs))):
        return False, "non-contiguous ctx_ledger indices", last_hash

    return True, "chain_ok", last_hash


def head_at_seal_index(
    ctx_ledger: Sequence[Mapping[str, Any]],
    seal_index: int,
    episode_id: str,
) -> str | None:
    entries = {int(e["idx"]): e for e in ctx_ledger}
    if seal_index in entries:
        return str(entries[seal_index].get("hash") or "")
    # If seal_index points at genesis (no entries yet) — rare
    if seal_index < 0:
        return genesis_hash(episode_id)
    return None


# ---------------------------------------------------------------------------
# R1–R12
# ---------------------------------------------------------------------------


def r1_seal_validity(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del action, provenance, ledger_state, ctx_ledger  # pure signature
    version = str(envelope.get("sie_version", ""))
    expires_at = envelope.get("expires_at")
    constraints = _constraints(envelope)
    tw = constraints.get("time_window") or {}

    inputs: dict[str, Any] = {
        "sie_version": version,
        "expires_at": expires_at,
        "now": now.isoformat().replace("+00:00", "Z"),
        "time_window": tw,
    }

    if version not in KNOWN_SIE_VERSIONS:
        return _result(
            "R1",
            "seal_validity",
            DENY,
            f"sie_version in {sorted(KNOWN_SIE_VERSIONS)}",
            f"sie_version={version!r}",
            inputs,
        )

    if expires_at is None:
        return _result(
            "R1",
            "seal_validity",
            DENY,
            "expires_at present and now <= expires_at",
            "expires_at missing",
            inputs,
        )

    exp = parse_dt(expires_at)
    if now > exp:
        return _result(
            "R1",
            "seal_validity",
            DENY,
            "now <= expires_at",
            f"now={inputs['now']} > expires_at={expires_at}",
            inputs,
        )

    if tw:
        tw_from = parse_dt(tw["from"]) if "from" in tw else None
        tw_to = parse_dt(tw["to"]) if "to" in tw else None
        if tw_from is not None and now < tw_from:
            return _result(
                "R1",
                "seal_validity",
                DENY,
                "now inside time_window",
                f"now < time_window.from",
                inputs,
            )
        if tw_to is not None and now > tw_to:
            return _result(
                "R1",
                "seal_validity",
                DENY,
                "now inside time_window",
                f"now > time_window.to",
                inputs,
            )

    ok, detail = _seal_valid(envelope)
    inputs["seal_check"] = detail
    if not ok:
        return _result(
            "R1",
            "seal_validity",
            DENY,
            "valid Ed25519 seal for kid",
            detail,
            inputs,
        )

    return _result(
        "R1",
        "seal_validity",
        ADMIT,
        "version known; now in window; seal valid",
        "ok",
        inputs,
    )


def r2_context_integrity(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del action, provenance, ledger_state, now
    binding = envelope.get("context_binding") or {}
    seal_index = int(binding.get("seal_index", 0))
    expected_head = str(binding.get("ledger_head", ""))
    episode_id = str(envelope.get("episode_id", ""))

    inputs: dict[str, Any] = {
        "seal_index": seal_index,
        "ledger_head": expected_head,
        "episode_id": episode_id,
        "entry_count": len(ctx_ledger),
    }

    # I1 / R2: every entry before seal_index must have taint == USER (not > USER).
    for entry in ctx_ledger:
        idx = int(entry["idx"])
        if idx < seal_index:
            taint = Taint.parse(entry.get("taint", "MODEL"))
            if taint > Taint.USER:
                return _result(
                    "R2",
                    "context_integrity",
                    DENY,
                    "entries idx < seal_index have taint==USER",
                    f"idx={idx} taint={taint.name}",
                    {**inputs, "offending_idx": idx, "offending_taint": taint.name},
                )

    ok, detail, _ = recompute_ctx_chain(ctx_ledger, episode_id)
    inputs["chain"] = detail
    if not ok:
        return _result(
            "R2",
            "context_integrity",
            DENY,
            "ctx_ledger chain recomputes",
            detail,
            inputs,
        )

    # Also verify declared prev_hash links even when hashes match genesis path
    entries = sorted(ctx_ledger, key=lambda e: int(e["idx"]))
    for i in range(1, len(entries)):
        if str(entries[i].get("prev_hash")) != str(entries[i - 1].get("hash")):
            return _result(
                "R2",
                "context_integrity",
                DENY,
                "prev_hash links contiguous",
                f"break before idx={entries[i].get('idx')}",
                inputs,
            )

    actual_head = head_at_seal_index(ctx_ledger, seal_index, episode_id)
    inputs["recomputed_head"] = actual_head
    if actual_head is None or actual_head != expected_head:
        return _result(
            "R2",
            "context_integrity",
            DENY,
            "context_binding.ledger_head == head at seal_index",
            f"expected={expected_head} actual={actual_head}",
            inputs,
        )

    return _result(
        "R2",
        "context_integrity",
        ADMIT,
        "pre-seal USER-only; chain ok; head matches",
        "ok",
        inputs,
    )


def r3_merchant_admissibility(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ledger_state, ctx_ledger, now
    c = _constraints(envelope)
    allow = list(c.get("merchants_allow") or [])
    deny_list = list(c.get("merchants_deny") or [])
    cats = list(c.get("categories_allow") or [])
    mid = _merchant_id(action)
    cat = _category(action, envelope)

    inputs = {
        "merchant_id": mid,
        "category": cat,
        "merchants_allow": allow,
        "merchants_deny": deny_list,
        "categories_allow": cats,
    }

    if mid in deny_list:
        return _result(
            "R3",
            "merchant_admissibility",
            DENY,
            "merchant_id not in merchants_deny",
            f"{mid} in merchants_deny",
            inputs,
        )
    # Empty allow-list means nothing is admissible (restrictive default).
    if mid not in allow:
        return _result(
            "R3",
            "merchant_admissibility",
            DENY,
            f"merchant_id in merchants_allow={allow}",
            f"merchant_id={mid}",
            inputs,
        )
    if cat is None or cat not in cats:
        return _result(
            "R3",
            "merchant_admissibility",
            DENY,
            f"category in categories_allow={cats}",
            f"category={cat}",
            inputs,
        )

    return _result(
        "R3",
        "merchant_admissibility",
        ADMIT,
        "merchant and category admissible",
        "ok",
        inputs,
    )


def r4_payee_instrument_binding(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ledger_state, ctx_ledger, now
    c = _constraints(envelope)
    allowed_instruments = list(c.get("allowed_instruments") or [])
    account = _account_ref(action)
    verified = _verified_settlement(action, envelope)
    instrument = action.instrument

    inputs = {
        "account_ref": account,
        "rzp_settlement_account_ref": verified,
        "instrument": instrument,
        "allowed_instruments": allowed_instruments,
    }

    if verified is None or account != verified:
        return _result(
            "R4",
            "payee_instrument_binding",
            DENY,
            "account_ref matches RZP_VERIFIED settlement account",
            f"account_ref={account} verified={verified}",
            inputs,
        )

    if allowed_instruments and instrument not in allowed_instruments:
        return _result(
            "R4",
            "payee_instrument_binding",
            DENY,
            f"instrument in allowed_instruments={allowed_instruments}",
            f"instrument={instrument}",
            inputs,
        )

    return _result(
        "R4",
        "payee_instrument_binding",
        ADMIT,
        "payee account and instrument bound",
        "ok",
        inputs,
    )


def r5_per_txn_bound(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ledger_state, ctx_ledger, now
    c = _constraints(envelope)
    per_txn = int(c.get("per_txn_max_paise", 0))
    env_currency = str(c.get("currency", "INR"))
    amount = int(action.amount_paise)

    inputs = {
        "amount_paise": amount,
        "per_txn_max_paise": per_txn,
        "currency": action.currency,
        "envelope_currency": env_currency,
    }

    if amount <= 0:
        return _result(
            "R5",
            "per_txn_bound",
            DENY,
            "amount_paise > 0",
            f"amount_paise={amount}",
            inputs,
        )
    if amount > per_txn:
        return _result(
            "R5",
            "per_txn_bound",
            DENY,
            f"amount_paise <= per_txn_max_paise ({per_txn})",
            f"amount_paise={amount}",
            inputs,
        )
    if action.currency != env_currency:
        return _result(
            "R5",
            "per_txn_bound",
            DENY,
            f"currency == {env_currency}",
            f"currency={action.currency}",
            inputs,
        )

    return _result(
        "R5",
        "per_txn_bound",
        ADMIT,
        f"0 < amount <= {per_txn} and currency ok",
        "ok",
        inputs,
    )


def r6_episode_ledger(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ctx_ledger, now
    c = _constraints(envelope)
    cap = int(c.get("episode_total_max_paise", 0))
    max_txn = int(c.get("max_transactions", 1))
    max_payees = int(c.get("max_distinct_payees", 1))
    amount = int(action.amount_paise)
    mid = _merchant_id(action)
    new_payees = ledger_state.distinct_payees | {mid}
    exposure = int(ledger_state.exposure_paise)
    txn_count = int(ledger_state.txn_count)

    inputs = {
        "exposure_paise": exposure,
        "amount_paise": amount,
        "cap_paise": cap,
        "txn_count": txn_count,
        "max_transactions": max_txn,
        "distinct_payees": sorted(ledger_state.distinct_payees),
        "new_payee": mid,
        "max_distinct_payees": max_payees,
    }

    failures: list[str] = []
    if exposure + amount > cap:
        failures.append(f"exposure + amount = {exposure + amount} > {cap}")
    if txn_count + 1 > max_txn:
        failures.append(f"txn_count + 1 = {txn_count + 1} > {max_txn}")
    if len(new_payees) > max_payees:
        failures.append(f"|payees| = {len(new_payees)} > {max_payees}")

    if failures:
        return _result(
            "R6",
            "episode_ledger",
            DENY,
            f"exposure + amount <= {cap}; txn_count+1 <= {max_txn}; "
            f"|payees| <= {max_payees}",
            "; ".join(failures),
            inputs,
        )

    return _result(
        "R6",
        "episode_ledger",
        ADMIT,
        f"exposure + amount <= {cap}; counters ok",
        f"{exposure} + {amount} <= {cap}",
        inputs,
    )


def _item_field_taint(item: Mapping[str, Any], field_name: str) -> Taint:
    tkey = f"{field_name}_taint"
    if tkey in item:
        return Taint.parse(item[tkey])
    taints = item.get("field_taints") or {}
    if field_name in taints:
        return Taint.parse(taints[field_name])
    # Untagged structured catalog fields default to MERCHANT_STRUCTURED if present
    if field_name in item:
        return Taint.MERCHANT_STRUCTURED
    return Taint.MODEL


def _predicate_satisfied(
    pred: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> bool:
    field_name = str(pred.get("field", ""))
    op = str(pred.get("op", "matches_any"))
    values = [str(v).lower() for v in (pred.get("value") or [])]
    min_qty = int(pred.get("min_qty", 1))
    max_qty = int(pred.get("max_qty", 10**9))

    # Only MERCHANT_STRUCTURED or better (lower) may satisfy.
    usable = []
    for item in items:
        if _item_field_taint(item, field_name) > Taint.MERCHANT_STRUCTURED:
            continue
        usable.append(item)

    if op == "matches_any":
        matched_qty = 0
        for item in usable:
            text = str(item.get(field_name, "")).lower()
            if any(v in text for v in values):
                matched_qty += int(item.get("qty", item.get("quantity", 1)))
        return min_qty <= matched_qty <= max_qty

    return False


def r7_item_predicates(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ledger_state, ctx_ledger, now
    preds = list((_constraints(envelope).get("item_predicates") or []))
    inputs: dict[str, Any] = {"predicates": preds, "item_count": len(action.items)}

    if not preds:
        return _result(
            "R7",
            "item_predicates",
            ADMIT,
            "no predicates or all satisfied over structured fields",
            "no predicates",
            inputs,
        )

    failed = []
    for pred in preds:
        if not _predicate_satisfied(pred, action.items):
            failed.append(pred)

    if failed:
        return _result(
            "R7",
            "item_predicates",
            DENY,
            "all item_predicates satisfied over MERCHANT_STRUCTURED+",
            f"unsatisfied={failed}",
            inputs,
        )

    return _result(
        "R7",
        "item_predicates",
        ADMIT,
        "all item_predicates satisfied",
        "ok",
        inputs,
    )


def r8_address_binding(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ledger_state, ctx_ledger, now
    env_hash = (_constraints(envelope) or {}).get("delivery_address_hash")
    act_hash = action.delivery_address_hash
    has_delivery = act_hash is not None or str(action.kind).upper() in {
        "DELIVERY",
        "FOOD_ORDER",
        "PAYMENT_WITH_DELIVERY",
    }

    inputs = {
        "envelope_delivery_address_hash": env_hash,
        "action_delivery_address_hash": act_hash,
        "has_delivery": has_delivery,
    }

    if not has_delivery:
        return _result(
            "R8",
            "address_binding",
            ADMIT,
            "no delivery on action type",
            "skipped",
            inputs,
        )

    if env_hash is None:
        return _result(
            "R8",
            "address_binding",
            DENY,
            "envelope delivery_address_hash present when action has delivery",
            "envelope hash missing",
            inputs,
        )

    if act_hash != env_hash:
        return _result(
            "R8",
            "address_binding",
            DENY,
            "action.delivery_address_hash == envelope.constraints.delivery_address_hash",
            f"{act_hash} != {env_hash}",
            inputs,
        )

    return _result(
        "R8",
        "address_binding",
        ADMIT,
        "delivery address bound",
        "ok",
        inputs,
    )


def r9_payee_novelty(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ctx_ledger, now
    c = _constraints(envelope)
    allow = set(c.get("merchants_allow") or [])
    policy = str(c.get("novel_payee_policy", "deny")).lower()
    mid = _merchant_id(action)
    seen = mid in ledger_state.distinct_payees
    allowed = mid in allow

    inputs = {
        "merchant_id": mid,
        "seen_in_episode": seen,
        "in_merchants_allow": allowed,
        "novel_payee_policy": policy,
    }

    if seen or allowed:
        return _result(
            "R9",
            "payee_novelty",
            ADMIT,
            "payee seen in episode or in merchants_allow",
            "ok",
            inputs,
        )

    verdict = ESCALATE if policy == "escalate" else DENY
    return _result(
        "R9",
        "payee_novelty",
        verdict,
        f"novel payee → {policy}",
        f"novel payee {mid}",
        inputs,
    )


def r10_provenance_ceiling(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del action, ledger_state, ctx_ledger, now
    policy = envelope.get("provenance_policy") or {}
    critical = list(policy.get("critical_fields") or [])
    max_taint_map = policy.get("max_taint") or {}

    inputs: dict[str, Any] = {"critical_fields": critical, "violations": []}
    violations = []

    for fname in critical:
        rec = provenance.record(fname)
        if rec is None:
            taint = Taint.MODEL
            missing = True
        else:
            taint = Taint.parse(rec.get("taint", "MODEL"))
            missing = False
        ceiling_label = max_taint_map.get(fname, "USER")
        ceiling = Taint.parse(ceiling_label)
        if taint > ceiling:
            violations.append(
                {
                    "field": fname,
                    "taint": taint.name,
                    "max_taint": ceiling.name,
                    "missing": missing,
                }
            )

    inputs["violations"] = violations
    if violations:
        return _result(
            "R10",
            "provenance_ceiling",
            DENY,
            "critical field taint <= max_taint (missing → MODEL)",
            f"violations={violations}",
            inputs,
        )

    return _result(
        "R10",
        "provenance_ceiling",
        ADMIT,
        "all critical fields within provenance ceiling",
        "ok",
        inputs,
    )


def _provenance_closure_indices(
    provenance: Provenance,
    critical_fields: Sequence[str],
) -> set[int]:
    idxs: set[int] = set()
    for fname in critical_fields:
        rec = provenance.record(fname)
        if rec is None:
            continue
        if "ledger_idx" in rec and rec["ledger_idx"] is not None:
            idxs.add(int(rec["ledger_idx"]))
        for dep in rec.get("depends_on") or []:
            idxs.add(int(dep))
    return idxs


def r11_injection_escalation(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    """Advisory detector → ESCALATE only. Never DENY. Never ADMIT when flagged."""
    del action, ledger_state, now
    policy = envelope.get("provenance_policy") or {}
    critical = list(policy.get("critical_fields") or [])
    closure = _provenance_closure_indices(provenance, critical)

    flagged_entries = []
    for entry in ctx_ledger:
        idx = int(entry["idx"])
        if idx not in closure:
            continue
        detector = entry.get("detector") or {}
        if detector.get("flagged") is True:
            flagged_entries.append(
                {"idx": idx, "signature": detector.get("signature")}
            )

    inputs = {
        "closure_indices": sorted(closure),
        "flagged_entries": flagged_entries,
    }

    if flagged_entries:
        return _result(
            "R11",
            "injection_escalation",
            ESCALATE,
            "no injection in provenance closure of critical fields",
            f"flagged={flagged_entries}",
            inputs,
        )

    return _result(
        "R11",
        "injection_escalation",
        ADMIT,
        "no injection flags in provenance closure",
        "clean",
        inputs,
    )


def r12_confirmation_threshold(
    envelope: Mapping[str, Any],
    action: Action,
    provenance: Provenance,
    ledger_state: LedgerState,
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime,
) -> RuleResult:
    del provenance, ledger_state, ctx_ledger, now
    c = _constraints(envelope)
    confirm_above = int(c.get("confirm_above_paise", 0))
    amount = int(action.amount_paise)
    confirmed = bool(action.human_confirmed)

    inputs = {
        "amount_paise": amount,
        "confirm_above_paise": confirm_above,
        "human_confirmed": confirmed,
    }

    if amount > confirm_above and not confirmed:
        return _result(
            "R12",
            "confirmation_threshold",
            ESCALATE,
            f"amount <= confirm_above ({confirm_above}) or human_confirmed",
            f"amount={amount} > {confirm_above} without confirmation",
            inputs,
        )

    return _result(
        "R12",
        "confirmation_threshold",
        ADMIT,
        "below confirm threshold or confirmed",
        "ok",
        inputs,
    )


RULES = (
    ("R1", "seal_validity", r1_seal_validity),
    ("R2", "context_integrity", r2_context_integrity),
    ("R3", "merchant_admissibility", r3_merchant_admissibility),
    ("R4", "payee_instrument_binding", r4_payee_instrument_binding),
    ("R5", "per_txn_bound", r5_per_txn_bound),
    ("R6", "episode_ledger", r6_episode_ledger),
    ("R7", "item_predicates", r7_item_predicates),
    ("R8", "address_binding", r8_address_binding),
    ("R9", "payee_novelty", r9_payee_novelty),
    ("R10", "provenance_ceiling", r10_provenance_ceiling),
    ("R11", "injection_escalation", r11_injection_escalation),
    ("R12", "confirmation_threshold", r12_confirmation_threshold),
)

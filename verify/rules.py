"""Independent re-implementation of admission rules R1–R12 (MUST NOT import core)."""

from __future__ import annotations

from typing import Any

from verify.hash import CTX_GENESIS, head_at_index
from verify.sign import public_key_from_raw, verify_jcs

ORDER = {"ADMIT": 0, "ESCALATE": 1, "DENY": 2}

TAINT_RANK = {
    "USER": 0,
    "RZP_VERIFIED": 1,
    "MERCHANT_STRUCTURED": 2,
    "MERCHANT_FREETEXT": 3,
    "WEB": 4,
    "TOOL_META": 5,
    "MODEL": 6,
}

KNOWN_SIE_VERSIONS = {"1.0"}


def combine(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda v: ORDER[v])


def taint_rank(label: str | None) -> int:
    if label is None:
        return TAINT_RANK["MODEL"]
    return TAINT_RANK.get(label, TAINT_RANK["MODEL"])


def _trace(
    rule_id: str,
    name: str,
    verdict: str,
    expected: str,
    actual: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "name": name,
        "verdict": verdict,
        "expected": expected,
        "actual": actual,
        "inputs": inputs or {},
    }


def _prov_map(provenance: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rec in provenance or []:
        field = rec.get("field")
        if field:
            out[str(field)] = rec
    return out


def _field_taint(prov: dict[str, dict[str, Any]], field: str) -> str:
    rec = prov.get(field)
    if rec is None:
        return "MODEL"
    return str(rec.get("taint") or "MODEL")


def _parse_iso(ts: str) -> str:
    """Normalize comparable ISO-8601 strings (string compare works for Zulu form)."""
    return ts.replace("Z", "+00:00") if ts.endswith("Z") else ts


def evaluate(
    envelope: dict[str, Any],
    action: dict[str, Any],
    provenance: list[dict[str, Any]] | None,
    ledger_state: dict[str, Any],
    ctx_ledger: list[dict[str, Any]],
    now: str,
    *,
    seal_public_key_raw: bytes | None = None,
    merchant_records: dict[str, Any] | None = None,
    human_confirmation: dict[str, Any] | None = None,
    episode_id: str | None = None,
) -> dict[str, Any]:
    """
    Pure gate evaluation. Returns a Decision-shaped dict:

    ``{verdict, rule_id, rule_trace, violated_predicates, ruleset_version}``
    """
    traces: list[dict[str, Any]] = []
    merchant_records = merchant_records or {}
    prov = _prov_map(provenance)
    constraints = envelope.get("constraints") or {}
    payee = action.get("payee") or {}
    merchant_id = payee.get("merchant_id")
    amount = int(action.get("amount_paise") or 0)
    ep_id = episode_id or envelope.get("episode_id") or ""

    # --- R1 seal validity ---
    seal = envelope.get("seal") or {}
    sie_version = str(envelope.get("sie_version") or "")
    expires_at = envelope.get("expires_at") or ""
    time_window = (constraints.get("time_window") or {}) if constraints else {}
    r1 = "ADMIT"
    r1_actual_parts: list[str] = []
    if sie_version not in KNOWN_SIE_VERSIONS:
        r1 = "DENY"
        r1_actual_parts.append(f"unknown sie_version={sie_version}")
    if now and expires_at and _parse_iso(now) > _parse_iso(str(expires_at)):
        r1 = "DENY"
        r1_actual_parts.append(f"expired now={now} expires_at={expires_at}")
    tw_from, tw_to = time_window.get("from"), time_window.get("to")
    if now and tw_from and _parse_iso(now) < _parse_iso(str(tw_from)):
        r1 = "DENY"
        r1_actual_parts.append("before time_window")
    if now and tw_to and _parse_iso(now) > _parse_iso(str(tw_to)):
        r1 = "DENY"
        r1_actual_parts.append("after time_window")
    sig = seal.get("sig")
    if not sig:
        r1 = "DENY"
        r1_actual_parts.append("missing seal.sig")
    elif seal_public_key_raw is not None:
        env_body = {k: v for k, v in envelope.items() if k != "seal"}
        pk = public_key_from_raw(seal_public_key_raw)
        if not verify_jcs(env_body, str(sig), pk):
            r1 = "DENY"
            r1_actual_parts.append("invalid seal signature")
    traces.append(
        _trace(
            "R1",
            "seal_validity",
            r1,
            "valid sig, unexpired, known sie_version, inside time_window",
            "; ".join(r1_actual_parts) if r1_actual_parts else "ok",
            {"sie_version": sie_version, "kid": seal.get("kid"), "now": now},
        )
    )

    # --- R2 context integrity ---
    binding = envelope.get("context_binding") or {}
    seal_index = int(binding.get("seal_index", 0))
    r2 = "ADMIT"
    r2_actual = "ok"
    for entry in ctx_ledger:
        idx = int(entry.get("index", entry.get("ledger_idx", -1)))
        if idx < seal_index:
            taint = entry.get("taint")
            role = entry.get("role")
            if taint_rank(taint) > TAINT_RANK["USER"] and role != "system":
                r2 = "DENY"
                r2_actual = f"entry[{idx}] taint={taint} > USER"
                break
    if r2 == "ADMIT" and ep_id:
        try:
            recomputed = head_at_index(CTX_GENESIS, ep_id, ctx_ledger, seal_index)
            expected_head = binding.get("ledger_head")
            # Also verify full chain recomputes without error for all entries
            head_at_index(CTX_GENESIS, ep_id, ctx_ledger, 10**9)
            if expected_head and recomputed != expected_head:
                r2 = "DENY"
                r2_actual = f"ledger_head mismatch got={recomputed} want={expected_head}"
        except Exception as exc:  # noqa: BLE001
            r2 = "DENY"
            r2_actual = f"chain recompute failed: {exc}"
    traces.append(
        _trace(
            "R2",
            "context_integrity",
            r2,
            "pre-seal entries USER/system; ledger_head matches",
            r2_actual,
            {"seal_index": seal_index, "ledger_head": binding.get("ledger_head")},
        )
    )

    # --- R3 merchant admissibility ---
    allow = list(constraints.get("merchants_allow") or [])
    deny = list(constraints.get("merchants_deny") or [])
    cats_allow = list(constraints.get("categories_allow") or [])
    r3 = "ADMIT"
    r3_actual = "ok"
    if merchant_id in deny:
        r3 = "DENY"
        r3_actual = f"merchant_id {merchant_id} in merchants_deny"
    elif allow and merchant_id not in allow:
        r3 = "DENY"
        r3_actual = f"merchant_id {merchant_id} not in merchants_allow"
    else:
        rec = merchant_records.get(str(merchant_id)) or {}
        cat = rec.get("category") or action.get("category")
        if cats_allow and cat is not None and cat not in cats_allow:
            r3 = "DENY"
            r3_actual = f"category {cat} not in categories_allow"
    traces.append(
        _trace(
            "R3",
            "merchant_admissibility",
            r3,
            "payee in allow, not deny, category allowed",
            r3_actual,
            {"merchant_id": merchant_id, "merchants_allow": allow},
        )
    )

    # --- R4 payee & instrument binding ---
    r4 = "ADMIT"
    r4_actual = "ok"
    account_ref = payee.get("account_ref")
    instrument = action.get("instrument")
    allowed_instruments = list(constraints.get("allowed_instruments") or [])
    mrec = merchant_records.get(str(merchant_id)) or {}
    if mrec:
        settlement = mrec.get("settlement_account_ref") or mrec.get("account_ref")
        if settlement is not None and account_ref != settlement:
            r4 = "DENY"
            r4_actual = f"account_ref {account_ref} != settlement {settlement}"
    if allowed_instruments and instrument not in allowed_instruments:
        r4 = "DENY"
        r4_actual = f"instrument {instrument} not allowed"
    traces.append(
        _trace(
            "R4",
            "payee_instrument_binding",
            r4,
            "account_ref matches RZP_VERIFIED settlement; instrument allowed",
            r4_actual,
            {"account_ref": account_ref, "instrument": instrument},
        )
    )

    # --- R5 per-transaction bound ---
    per_txn = int(constraints.get("per_txn_max_paise") or 0)
    currency = action.get("currency")
    env_currency = constraints.get("currency")
    r5 = "ADMIT"
    r5_actual = "ok"
    if amount <= 0:
        r5 = "DENY"
        r5_actual = f"amount_paise={amount} <= 0"
    elif per_txn and amount > per_txn:
        r5 = "DENY"
        r5_actual = f"{amount} > per_txn_max {per_txn}"
    elif env_currency and currency != env_currency:
        r5 = "DENY"
        r5_actual = f"currency {currency} != {env_currency}"
    traces.append(
        _trace(
            "R5",
            "per_transaction_bound",
            r5,
            f"0 < amount <= {per_txn} and currency match",
            r5_actual,
            {"amount_paise": amount, "per_txn_max_paise": per_txn},
        )
    )

    # --- R6 episode ledger ---
    exposure = int(ledger_state.get("exposure_paise") or 0)
    txn_count = int(ledger_state.get("txn_count") or 0)
    distinct = int(ledger_state.get("distinct_payees") or 0)
    ep_cap = int(constraints.get("episode_total_max_paise") or 0)
    max_txn = int(constraints.get("max_transactions") or 0)
    max_payees = int(constraints.get("max_distinct_payees") or 0)
    seen = set(ledger_state.get("payee_ids") or [])
    new_distinct = distinct
    if merchant_id not in seen:
        new_distinct = distinct + 1
    r6 = "ADMIT"
    r6_parts: list[str] = []
    if ep_cap and exposure + amount > ep_cap:
        r6 = "DENY"
        r6_parts.append(f"{exposure} + {amount} = {exposure + amount} > {ep_cap}")
    if max_txn and txn_count + 1 > max_txn:
        r6 = "DENY"
        r6_parts.append(f"txn_count {txn_count}+1 > {max_txn}")
    if max_payees and new_distinct > max_payees:
        r6 = "DENY"
        r6_parts.append(f"distinct_payees {new_distinct} > {max_payees}")
    traces.append(
        _trace(
            "R6",
            "episode_ledger",
            r6,
            f"exposure + amount <= {ep_cap}; txn+1 <= {max_txn}; payees <= {max_payees}",
            "; ".join(r6_parts) if r6_parts else "ok",
            {
                "exposure_paise": exposure,
                "amount_paise": amount,
                "cap_paise": ep_cap,
                "txn_count": txn_count,
                "max_transactions": max_txn,
            },
        )
    )

    # --- R7 item predicates ---
    predicates = list(constraints.get("item_predicates") or [])
    items = list(action.get("items") or [])
    r7 = "ADMIT"
    r7_actual = "ok"
    for pred in predicates:
        field = pred.get("field", "title")
        op = pred.get("op", "matches_any")
        values = [str(v).lower() for v in (pred.get("value") or [])]
        min_qty = int(pred.get("min_qty") or 0)
        max_qty = pred.get("max_qty")
        matched_qty = 0
        for item in items:
            # Only MERCHANT_STRUCTURED-or-better fields
            item_taint = item.get("_taint") or item.get("taint") or "MERCHANT_STRUCTURED"
            if taint_rank(item_taint) > TAINT_RANK["MERCHANT_STRUCTURED"]:
                continue
            fv = str(item.get(field) or "").lower()
            if op == "matches_any" and any(v in fv for v in values):
                matched_qty += int(item.get("qty") or item.get("quantity") or 1)
        if matched_qty < min_qty or (max_qty is not None and matched_qty > int(max_qty)):
            r7 = "DENY"
            r7_actual = f"predicate {pred} unmatched qty={matched_qty}"
            break
    traces.append(
        _trace(
            "R7",
            "item_predicates",
            r7,
            "all item_predicates satisfied over structured fields",
            r7_actual,
            {"predicates": predicates},
        )
    )

    # --- R8 address binding ---
    r8 = "ADMIT"
    r8_actual = "ok"
    env_addr = constraints.get("delivery_address_hash")
    act_addr = action.get("delivery_address_hash")
    has_delivery = "delivery_address_hash" in action or action.get("kind") in {
        "PAYMENT",
        "DELIVERY_PAYMENT",
        "FOOD_ORDER",
    }
    if has_delivery and env_addr is not None:
        if act_addr != env_addr:
            r8 = "DENY"
            r8_actual = f"{act_addr} != {env_addr}"
    traces.append(
        _trace(
            "R8",
            "address_binding",
            r8,
            "delivery_address_hash matches envelope",
            r8_actual,
            {"envelope": env_addr, "action": act_addr},
        )
    )

    # --- R9 payee novelty ---
    policy = constraints.get("novel_payee_policy") or "deny"
    r9 = "ADMIT"
    r9_actual = "ok"
    novel = merchant_id not in seen and merchant_id not in allow
    if novel:
        if policy == "escalate":
            r9 = "ESCALATE"
            r9_actual = f"novel payee {merchant_id} -> escalate"
        else:
            r9 = "DENY"
            r9_actual = f"novel payee {merchant_id} -> deny"
    traces.append(
        _trace(
            "R9",
            "payee_novelty",
            r9,
            f"novel_payee_policy={policy}",
            r9_actual,
            {"merchant_id": merchant_id, "novel": novel},
        )
    )

    # --- R10 provenance ceiling ---
    pol = envelope.get("provenance_policy") or {}
    critical = list(pol.get("critical_fields") or [])
    max_taint = dict(pol.get("max_taint") or {})
    r10 = "ADMIT"
    r10_actual = "ok"
    for field in critical:
        actual_t = _field_taint(prov, field)
        ceiling = max_taint.get(field, "USER")
        if taint_rank(actual_t) > taint_rank(ceiling):
            r10 = "DENY"
            r10_actual = f"{field} taint={actual_t} > max={ceiling}"
            break
    traces.append(
        _trace(
            "R10",
            "provenance_ceiling",
            r10,
            "critical fields within max_taint (missing => MODEL)",
            r10_actual,
            {"critical_fields": critical},
        )
    )

    # --- R11 injection escalation ---
    r11 = "ADMIT"
    r11_actual = "ok"
    # Provenance closure of critical fields
    closure_idxs: set[int] = set()
    for field in critical:
        rec = prov.get(field)
        if rec and rec.get("ledger_idx") is not None:
            closure_idxs.add(int(rec["ledger_idx"]))
    for entry in ctx_ledger:
        idx = int(entry.get("index", entry.get("ledger_idx", -1)))
        if idx in closure_idxs:
            det = entry.get("detector") or {}
            if det.get("flagged") or entry.get("injection_flagged"):
                r11 = "ESCALATE"
                r11_actual = f"injection flagged at ledger_idx={idx}"
                break
    # Also honour detector on provenance records / causal hints
    if r11 == "ADMIT":
        for rec in provenance or []:
            if rec.get("field") in critical:
                det = rec.get("detector") or {}
                if det.get("flagged"):
                    r11 = "ESCALATE"
                    r11_actual = f"injection flagged on {rec.get('field')}"
                    break
    traces.append(
        _trace(
            "R11",
            "injection_escalation",
            r11,
            "no injection in provenance closure of critical fields",
            r11_actual,
            {"closure_idxs": sorted(closure_idxs)},
        )
    )

    # --- R12 confirmation threshold ---
    confirm_above = int(constraints.get("confirm_above_paise") or 0)
    r12 = "ADMIT"
    r12_actual = "ok"
    if amount > confirm_above:
        conf_ok = bool(human_confirmation and human_confirmation.get("valid"))
        if not conf_ok:
            r12 = "ESCALATE"
            r12_actual = f"amount {amount} > confirm_above {confirm_above}, no confirmation"
    traces.append(
        _trace(
            "R12",
            "confirmation_threshold",
            r12,
            f"amount <= {confirm_above} or valid human confirmation",
            r12_actual,
            {"amount_paise": amount, "confirm_above_paise": confirm_above},
        )
    )

    verdicts = [t["verdict"] for t in traces]
    verdict = combine(verdicts)
    rule_id = next(t["rule_id"] for t in traces if t["verdict"] == verdict)
    violated = [t for t in traces if t["verdict"] == verdict and verdict != "ADMIT"]
    # Prefer the first rule that produced the most-restrictive verdict
    first = next(t for t in traces if t["verdict"] == verdict)
    rule_id = first["rule_id"]
    if verdict != "ADMIT":
        violated = [first]

    return {
        "verdict": verdict,
        "rule_id": rule_id,
        "rule_trace": traces,
        "violated_predicates": violated,
        "ruleset_version": "1.0",
    }

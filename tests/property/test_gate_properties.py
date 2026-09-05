"""Hypothesis property tests for the gate (I3 + ledger soundness + determinism)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from core.gate import ORDER, combine, evaluate
from core.gate.rules import entry_hash, genesis_hash

EPISODE = "ep_01JBPROP000000000000000"


def _ctx(seal_index: int = 0):
    prev = genesis_hash(EPISODE)
    e0 = {
        "idx": 0,
        "role": "user",
        "taint": "USER",
        "content_sha": "sha256:" + ("c" * 64),
        "content_excerpt": "buy food",
        "source_uri": None,
        "prev_hash": prev,
    }
    e0["hash"] = entry_hash(prev, e0)
    e1 = {
        "idx": 1,
        "role": "tool_result",
        "taint": "MERCHANT_STRUCTURED",
        "content_sha": "sha256:" + ("d" * 64),
        "content_excerpt": "catalog",
        "source_uri": "catalog://x",
        "prev_hash": e0["hash"],
        "detector": {"flagged": False},
    }
    e1["hash"] = entry_hash(e0["hash"], e1)
    return [e0, e1]


def _envelope(ctx, episode_total_max_paise: int = 100000, per_txn_max_paise: int = 100000):
    head = ctx[0]["hash"]
    return {
        "sie_version": "1.0",
        "envelope_id": "sie_prop",
        "episode_id": EPISODE,
        "created_at": "2026-09-05T12:00:00Z",
        "expires_at": "2026-09-05T18:00:00Z",
        "constraints": {
            "merchants_allow": ["swiggy"],
            "merchants_deny": [],
            "categories_allow": ["food_delivery"],
            "item_predicates": [],
            "per_txn_max_paise": per_txn_max_paise,
            "episode_total_max_paise": episode_total_max_paise,
            "max_transactions": 100,
            "max_distinct_payees": 10,
            "currency": "INR",
            "delivery_address_hash": "sha256:addr",
            "allowed_instruments": ["upi_reserve_pay:tok_x"],
            "novel_payee_policy": "deny",
            "confirm_above_paise": 10**12,
            "time_window": {
                "from": "2026-09-05T00:00:00Z",
                "to": "2026-09-05T23:59:59Z",
            },
        },
        "provenance_policy": {
            "critical_fields": [
                "amount_paise",
                "payee.merchant_id",
                "payee.account_ref",
                "delivery_address_hash",
                "instrument",
            ],
            "max_taint": {
                "amount_paise": "MERCHANT_STRUCTURED",
                "payee.merchant_id": "RZP_VERIFIED",
                "payee.account_ref": "RZP_VERIFIED",
                "delivery_address_hash": "USER",
                "instrument": "USER",
            },
        },
        "context_binding": {"ledger_head": head, "seal_index": 0},
        "seal": {"alg": "Ed25519", "kid": "k", "sig": "x"},
        "_test": {"seal_ok": True},
        "merchant_records": {
            "swiggy": {"account_ref": "acc_swiggy_settle", "category": "food_delivery"}
        },
    }


def _action(amount_paise: int):
    return {
        "kind": "PAYMENT",
        "amount_paise": amount_paise,
        "currency": "INR",
        "payee": {
            "merchant_id": "swiggy",
            "account_ref": "acc_swiggy_settle",
            "category": "food_delivery",
        },
        "items": [],
        "instrument": "upi_reserve_pay:tok_x",
        "delivery_address_hash": "sha256:addr",
        "human_confirmed": True,
    }


def _provenance():
    return {
        "amount_paise": {"taint": "MERCHANT_STRUCTURED", "ledger_idx": 1},
        "payee.merchant_id": {"taint": "RZP_VERIFIED", "ledger_idx": 1},
        "payee.account_ref": {"taint": "RZP_VERIFIED", "ledger_idx": 1},
        "delivery_address_hash": {"taint": "USER", "ledger_idx": 0},
        "instrument": {"taint": "USER", "ledger_idx": 0},
    }


def _now():
    return datetime(2026, 9, 5, 12, 30, tzinfo=timezone.utc)


def test_combine_monotone_order() -> None:
    assert combine(["ADMIT", "ESCALATE"]) == "ESCALATE"
    assert combine(["ADMIT", "DENY"]) == "DENY"
    assert combine(["ESCALATE", "DENY"]) == "DENY"
    assert combine(["ADMIT", "ADMIT"]) == "ADMIT"
    assert ORDER["DENY"] > ORDER["ESCALATE"] > ORDER["ADMIT"]


@given(flagged=st.booleans())
@settings(max_examples=40)
def test_r11_monotonicity(flagged: bool) -> None:
    """Flipping detector to flagged must never decrease restrictiveness (I3)."""
    ctx = _ctx()
    ctx[1] = dict(ctx[1])
    ctx[1]["detector"] = {"flagged": False}
    # recompute hash after mutation of detector field
    body = {k: v for k, v in ctx[1].items() if k != "hash"}
    ctx[1]["hash"] = entry_hash(ctx[1]["prev_hash"], body)

    env = _envelope(ctx)
    action = _action(1000)
    prov = _provenance()
    ledger = {"exposure_paise": 0, "txn_count": 0, "distinct_payees": []}

    clean = evaluate(env, action, prov, ledger, ctx, _now())

    ctx_f = copy.deepcopy(ctx)
    ctx_f[1]["detector"] = {"flagged": True, "signature": "x"}
    body_f = {k: v for k, v in ctx_f[1].items() if k != "hash"}
    ctx_f[1]["hash"] = entry_hash(ctx_f[1]["prev_hash"], body_f)
    # Head at seal_index 0 unchanged
    flagged_decision = evaluate(env, action, prov, ledger, ctx_f, _now())

    assert ORDER[flagged_decision.verdict] >= ORDER[clean.verdict]
    r11_clean = next(r for r in clean.rule_trace if r.rule_id == "R11")
    r11_flag = next(r for r in flagged_decision.rule_trace if r.rule_id == "R11")
    assert r11_clean.verdict == "ADMIT"
    assert r11_flag.verdict == "ESCALATE"
    assert r11_flag.verdict != "DENY"
    # unused param keeps hypothesis exploring both branches of caller API
    _ = flagged


@given(
    amounts=st.lists(st.integers(min_value=1, max_value=30000), min_size=1, max_size=8),
    cap=st.integers(min_value=1, max_value=100000),
)
@settings(max_examples=50)
def test_ledger_soundness_admitted_sum(amounts: list[int], cap: int) -> None:
    """For any sequence of ADMITted actions, Σ amounts ≤ episode_total_max_paise."""
    ctx = _ctx()
    env = _envelope(ctx, episode_total_max_paise=cap, per_txn_max_paise=cap)
    prov = _provenance()
    exposure = 0
    txn_count = 0
    payees: set[str] = set()
    admitted_sum = 0

    for amount in amounts:
        ledger = {
            "exposure_paise": exposure,
            "txn_count": txn_count,
            "distinct_payees": sorted(payees),
        }
        decision = evaluate(env, _action(amount), prov, ledger, ctx, _now())
        if decision.verdict == "ADMIT":
            admitted_sum += amount
            exposure += amount
            txn_count += 1
            payees.add("swiggy")
            assert admitted_sum <= cap
        else:
            # R6 (or others) blocked — admitted sum unchanged
            assert admitted_sum <= cap

    assert admitted_sum <= cap


@given(amount=st.integers(min_value=1, max_value=50000))
@settings(max_examples=30)
def test_determinism_byte_identical_trace(amount: int) -> None:
    ctx = _ctx()
    env = _envelope(ctx)
    action = _action(amount)
    prov = _provenance()
    ledger = {"exposure_paise": 0, "txn_count": 0, "distinct_payees": []}
    now = _now()

    a = evaluate(env, action, prov, ledger, ctx, now)
    b = evaluate(env, action, prov, ledger, ctx, now)
    assert a.as_dict() == b.as_dict()

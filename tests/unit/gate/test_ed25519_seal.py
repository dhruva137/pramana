"""R1 Ed25519 seal verification (cryptography) — no ambient clock."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.gate import evaluate
from core.gate.rules import entry_hash, genesis_hash, jcs, _envelope_for_seal


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def test_r1_real_ed25519_seal_admits() -> None:
    episode = "ep_01JBED25519TEST00000000"
    prev = genesis_hash(episode)
    e0 = {
        "idx": 0,
        "role": "user",
        "taint": "USER",
        "content_sha": "sha256:" + ("e" * 64),
        "content_excerpt": "hi",
        "source_uri": None,
        "prev_hash": prev,
    }
    e0["hash"] = entry_hash(prev, e0)
    ctx = [e0]

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key().public_bytes_raw()

    envelope = {
        "sie_version": "1.0",
        "envelope_id": "sie_ed",
        "episode_id": episode,
        "created_at": "2026-09-05T12:00:00Z",
        "expires_at": "2026-09-05T13:00:00Z",
        "constraints": {
            "merchants_allow": ["swiggy"],
            "merchants_deny": [],
            "categories_allow": ["food_delivery"],
            "item_predicates": [],
            "per_txn_max_paise": 60000,
            "episode_total_max_paise": 60000,
            "max_transactions": 1,
            "max_distinct_payees": 1,
            "currency": "INR",
            "delivery_address_hash": "sha256:addr",
            "allowed_instruments": ["upi_reserve_pay:tok_x"],
            "novel_payee_policy": "deny",
            "confirm_above_paise": 10**9,
            "time_window": {
                "from": "2026-09-05T12:00:00Z",
                "to": "2026-09-05T13:00:00Z",
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
        "context_binding": {"ledger_head": e0["hash"], "seal_index": 0},
        "merchant_records": {
            "swiggy": {"account_ref": "acc_swiggy_settle", "category": "food_delivery"}
        },
        "_test_pub": _b64url(pk),
    }
    sig = sk.sign(jcs(_envelope_for_seal(envelope)))
    envelope["seal"] = {"alg": "Ed25519", "kid": "seal-test", "sig": _b64url(sig)}

    action = {
        "kind": "PAYMENT",
        "amount_paise": 1000,
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
    provenance = {
        "amount_paise": {"taint": "MERCHANT_STRUCTURED", "ledger_idx": 0},
        "payee.merchant_id": {"taint": "RZP_VERIFIED", "ledger_idx": 0},
        "payee.account_ref": {"taint": "RZP_VERIFIED", "ledger_idx": 0},
        "delivery_address_hash": {"taint": "USER", "ledger_idx": 0},
        "instrument": {"taint": "USER", "ledger_idx": 0},
    }
    ledger = {"exposure_paise": 0, "txn_count": 0, "distinct_payees": []}
    now = datetime(2026, 9, 5, 12, 30, tzinfo=timezone.utc)

    decision = evaluate(envelope, action, provenance, ledger, ctx, now)
    r1 = next(r for r in decision.rule_trace if r.rule_id == "R1")
    assert r1.verdict == "ADMIT"
    assert decision.verdict == "ADMIT"


def test_r1_bad_signature_denies() -> None:
    episode = "ep_01JBED25519BAD000000000"
    prev = genesis_hash(episode)
    e0 = {
        "idx": 0,
        "role": "user",
        "taint": "USER",
        "content_sha": "sha256:" + ("f" * 64),
        "content_excerpt": "hi",
        "source_uri": None,
        "prev_hash": prev,
    }
    e0["hash"] = entry_hash(prev, e0)
    sk = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    envelope = {
        "sie_version": "1.0",
        "episode_id": episode,
        "expires_at": "2026-09-05T13:00:00Z",
        "constraints": {
            "merchants_allow": ["swiggy"],
            "merchants_deny": [],
            "categories_allow": ["food_delivery"],
            "item_predicates": [],
            "per_txn_max_paise": 60000,
            "episode_total_max_paise": 60000,
            "max_transactions": 1,
            "max_distinct_payees": 1,
            "currency": "INR",
            "delivery_address_hash": "sha256:addr",
            "allowed_instruments": ["upi_reserve_pay:tok_x"],
            "novel_payee_policy": "deny",
            "confirm_above_paise": 10**9,
            "time_window": {
                "from": "2026-09-05T12:00:00Z",
                "to": "2026-09-05T13:00:00Z",
            },
        },
        "provenance_policy": {
            "critical_fields": ["amount_paise"],
            "max_taint": {"amount_paise": "MODEL"},
        },
        "context_binding": {"ledger_head": e0["hash"], "seal_index": 0},
        "merchant_records": {
            "swiggy": {"account_ref": "acc_swiggy_settle", "category": "food_delivery"}
        },
        "_test_pub": _b64url(sk.public_key().public_bytes_raw()),
        "seal": {
            "alg": "Ed25519",
            "kid": "k",
            "sig": _b64url(other.sign(b"not-the-envelope")),
        },
    }
    decision = evaluate(
        envelope,
        {
            "kind": "PAYMENT",
            "amount_paise": 1000,
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
        },
        {"amount_paise": {"taint": "USER", "ledger_idx": 0}},
        {"exposure_paise": 0, "txn_count": 0, "distinct_payees": []},
        [e0],
        datetime(2026, 9, 5, 12, 30, tzinfo=timezone.utc),
    )
    assert decision.verdict == "DENY"
    assert decision.rule_id == "R1"

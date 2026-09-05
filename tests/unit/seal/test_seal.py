"""Unit tests for core.seal — clamp, fallback, mock extract, no-tools client."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest
from core.seal._crypto import generate_sk
from core.seal.clamp import clamp_constraints, clamp_expires_at
from core.seal.extract import (
    build_anthropic_request,
    build_gemini_request,
    mock_extract,
)
from core.seal.fallback import restrictive_fallback
from core.seal.schema import (
    Constraints,
    ExtractionDraft,
    SealedIntentEnvelope,
    TimeWindow,
)
from core.seal.sealer import ContextTaintedError, SealRequest, seal
from agent.sealer import seal_utterance


def _demo_sk_b64() -> str:
    return base64.b64encode(generate_sk()).decode("ascii")


NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# No tools
# ---------------------------------------------------------------------------


def test_anthropic_request_has_no_tools_key():
    body = build_anthropic_request("Order biryani from Swiggy under 600")
    assert "tools" not in body
    assert "tool_choice" not in body
    assert body["messages"][0]["role"] == "user"


def test_gemini_request_has_no_tools_key():
    body = build_gemini_request("Swiggy se biryani order karo")
    assert "tools" not in body
    assert "toolConfig" not in body
    assert "tool_config" not in body


def test_agent_wrapper_request_builders_have_no_tools():
    from agent import sealer as agent_sealer

    a = agent_sealer.build_anthropic_request("hi")
    g = agent_sealer.build_gemini_request("hi")
    assert "tools" not in a
    assert "tools" not in g


# ---------------------------------------------------------------------------
# Clamp
# ---------------------------------------------------------------------------


def test_clamp_money_fields_to_consent_ceiling():
    c = Constraints(
        merchants_allow=["swiggy"],
        merchants_deny=[],
        categories_allow=["food_delivery"],
        item_predicates=[],
        per_txn_max_paise=500_000,
        episode_total_max_paise=400_000,
        max_transactions=1,
        max_distinct_payees=1,
        currency="INR",
        delivery_address_hash="sha256:x",
        allowed_instruments=["upi_reserve_pay:tok_x"],
        novel_payee_policy="deny",
        confirm_above_paise=300_000,
        time_window=TimeWindow.model_validate(
            {"from": NOW, "to": NOW + timedelta(minutes=15)}
        ),
    )
    out, fields = clamp_constraints(c, consent_cap_paise=200_000, now=NOW)
    assert out.per_txn_max_paise == 200_000
    assert out.episode_total_max_paise == 200_000
    assert out.confirm_above_paise == 200_000
    assert "per_txn_max_paise" in fields
    assert "episode_total_max_paise" in fields
    assert "confirm_above_paise" in fields


def test_clamp_max_transactions_to_10():
    c = Constraints(
        merchants_allow=[],
        merchants_deny=[],
        categories_allow=[],
        item_predicates=[],
        per_txn_max_paise=1000,
        episode_total_max_paise=1000,
        max_transactions=99,
        max_distinct_payees=1,
        currency="INR",
        delivery_address_hash="sha256:x",
        allowed_instruments=[],
        novel_payee_policy="deny",
        confirm_above_paise=0,
    )
    out, fields = clamp_constraints(c, consent_cap_paise=200_000, now=NOW)
    assert out.max_transactions == 10
    assert "max_transactions" in fields


def test_clamp_expires_at_to_15_minutes():
    far = NOW + timedelta(hours=2)
    clamped, was = clamp_expires_at(far, now=NOW)
    assert was is True
    assert clamped == NOW + timedelta(minutes=15)


def test_clamp_envelope_records_clamped_fields():
    sk = _demo_sk_b64()
    result = seal(
        SealRequest(
            utterance="Order from Swiggy under ₹5000",
            user_ref="usr_demo_1",
            consent_ref="rsv_test_abc",
            consent_cap_paise=50_000,  # ₹500 — model/mock may propose higher
            now=NOW,
            seal_sk_b64=sk,
            force_mock=True,
            _extract_override=lambda: {
                "merchants_allow": ["swiggy"],
                "per_txn_max_paise": 500_000,
                "episode_total_max_paise": 500_000,
                "max_transactions": 1,
                "confirm_above_paise": 100_000,
            },
        )
    )
    env = result.envelope
    assert env.constraints.per_txn_max_paise == 50_000
    assert "per_txn_max_paise" in env.extraction.clamped_fields


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def test_restrictive_fallback_shape():
    draft = restrictive_fallback(
        "Swiggy se biryani under ₹600",
        consent_cap_paise=200_000,
    )
    assert draft.max_transactions == 1
    assert draft.confirm_above_paise == 0
    assert draft.novel_payee_policy == "deny"
    assert draft.per_txn_max_paise == 60_000
    assert draft.episode_total_max_paise == 60_000
    assert draft.merchants_allow == ["swiggy"]


def test_fallback_on_bad_extractor_output():
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise ValueError("malformed JSON")

    result = seal(
        SealRequest(
            utterance="Zomato pe pizza under Rs 400",
            user_ref="usr_demo_1",
            consent_ref="rsv_test",
            consent_cap_paise=200_000,
            now=NOW,
            seal_sk_b64=_demo_sk_b64(),
            _extract_override=bad,
        )
    )
    assert calls["n"] == 2
    assert result.degraded is True
    assert result.envelope.extraction.degraded is True
    assert result.envelope.constraints.max_transactions == 1
    assert result.envelope.constraints.confirm_above_paise == 0
    assert result.envelope.constraints.novel_payee_policy == "deny"
    assert "zomato" in result.envelope.constraints.merchants_allow
    assert result.envelope.constraints.per_txn_max_paise == 40_000


def test_context_tainted_refuses_seal():
    with pytest.raises(ContextTaintedError) as ei:
        seal(
            SealRequest(
                utterance="Order dinner",
                user_ref="u",
                consent_ref="c",
                consent_cap_paise=10000,
                seal_index=1,
                ctx_entries=[
                    {"idx": 0, "role": "user", "taint": "USER"},
                    {"idx": 1, "role": "tool_result", "taint": "MERCHANT_FREETEXT"},
                ],
                seal_sk_b64=_demo_sk_b64(),
                force_mock=True,
            )
        )
    assert ei.value.code == "CONTEXT_TAINTED"


# ---------------------------------------------------------------------------
# Mock extraction — 10 utterances incl. Hinglish → schema-valid envelopes
# ---------------------------------------------------------------------------

MOCK_UTTERANCES = [
    "Order two chicken biryanis from Swiggy, under 600 total",
    "Get dinner from Swiggy under ₹600",
    "Buy headphones from Amazon under Rs 2000",
    "Blinkit se milk order karo max 300",
    "Zomato pe do pizza manga do under Rs 500",
    "Swiggy se chicken biryani order karo, 600 ke andar",
    "Bigbasket se groceries under ₹1500",
    "Flipkart pe earphone kharidna under 999",
    "Zepto se doodh mangwao 200 tak",
    "Order one thali from Zomato within INR 350",
]


@pytest.mark.parametrize("utterance", MOCK_UTTERANCES, ids=lambda u: u[:40])
def test_mock_extraction_produces_schema_valid_envelope(utterance: str):
    result = seal_utterance(
        utterance,
        user_ref="usr_demo_1",
        consent_ref="rsv_test_abc",
        consent_cap_paise=200_000,
        force_mock=True,
        seal_sk_b64=_demo_sk_b64(),
        **{"now": NOW},
    )
    env = result.envelope
    assert result.degraded is False
    # Full model validation
    SealedIntentEnvelope.model_validate(env.model_dump(mode="python", by_alias=True))
    assert env.sie_version == "1.0"
    assert env.utterance.channel == "USER"
    assert env.seal is not None
    assert env.seal.alg == "Ed25519"
    assert env.seal.sig
    assert env.constraints.currency == "INR"
    assert env.constraints.max_transactions <= 10
    assert env.constraints.per_txn_max_paise <= 200_000
    assert env.constraints.episode_total_max_paise <= 200_000
    # Mock should pick up at least one merchant for these fixtures
    draft = mock_extract(utterance, consent_cap_paise=200_000)
    ExtractionDraft.model_validate(draft.model_dump())
    assert draft.merchants_allow, f"expected merchant in: {utterance}"


def test_mock_biryani_swiggy_hinglish_amounts():
    draft = mock_extract(
        "Swiggy se do chicken biryani order karo, 600 ke andar",
        consent_cap_paise=200_000,
    )
    assert draft.merchants_allow == ["swiggy"]
    assert draft.per_txn_max_paise == 60_000
    assert draft.episode_total_max_paise == 60_000
    assert any("biryani" in p.value for p in draft.item_predicates)

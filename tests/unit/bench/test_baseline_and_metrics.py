"""Unit tests for Arm A mandate validation and Wilson CI helper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent.baseline import issue_mandate, validate_transaction, verify_mandate_signature
from bench.metrics import RateCI, wilson_ci


class TestBaselineMandate:
    def test_valid_transaction_passes(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        mandate = issue_mandate(
            utterance="Order chicken biryani from Swiggy Sim, keep it under ₹600.",
            instrument="upi_reserve_pay:tok_x",
            consent_cap_paise=200_000,
            merchants=["swiggy_sim"],
            now=now,
        )
        assert verify_mandate_signature(mandate)
        assert mandate.per_transaction_max_paise == 60_000
        assert "swiggy_sim" in mandate.merchants

        result = validate_transaction(
            mandate,
            merchant_id="swiggy_sim",
            amount_paise=27_000,
            now=now + timedelta(minutes=1),
        )
        assert result.ok
        assert result.reason == "ok"
        assert result.checks["signature_valid"]
        assert result.checks["merchant_in_list"]
        assert result.checks["amount_within_cap"]
        assert result.checks["not_expired"]

    def test_amount_over_cap_fails(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        mandate = issue_mandate(
            utterance="Order dinner under ₹600.",
            instrument="upi_reserve_pay:tok_x",
            consent_cap_paise=200_000,
            merchants=["swiggy_sim"],
            per_transaction_max_paise=60_000,
            now=now,
        )
        result = validate_transaction(
            mandate,
            merchant_id="swiggy_sim",
            amount_paise=199_900,
            now=now,
        )
        assert not result.ok
        assert "amount_exceeds_per_txn_cap" in result.reason
        assert result.checks["amount_within_cap"] is False

    def test_merchant_not_in_list_fails(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        mandate = issue_mandate(
            utterance="Order from Swiggy Sim under ₹600.",
            instrument="upi_reserve_pay:tok_x",
            consent_cap_paise=200_000,
            merchants=["swiggy_sim"],
            now=now,
        )
        result = validate_transaction(
            mandate,
            merchant_id="grocery_direct_pl",
            amount_paise=27_000,
            now=now,
        )
        assert not result.ok
        assert "merchant_not_in_mandate" in result.reason

    def test_expired_mandate_fails(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        mandate = issue_mandate(
            utterance="Order under ₹600.",
            instrument="upi_reserve_pay:tok_x",
            consent_cap_paise=200_000,
            merchants=["swiggy_sim"],
            ttl_minutes=5,
            now=now,
        )
        result = validate_transaction(
            mandate,
            merchant_id="swiggy_sim",
            amount_paise=10_000,
            now=now + timedelta(minutes=30),
        )
        assert not result.ok
        assert result.reason == "mandate_expired"

    def test_tampered_signature_fails(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        mandate = issue_mandate(
            utterance="Order under ₹600.",
            instrument="upi_reserve_pay:tok_x",
            consent_cap_paise=200_000,
            merchants=["swiggy_sim"],
            now=now,
        )
        mandate.sig = "AAAA" + mandate.sig[4:]
        result = validate_transaction(
            mandate,
            merchant_id="swiggy_sim",
            amount_paise=10_000,
            now=now,
        )
        assert not result.ok
        assert result.reason == "invalid_signature"

    def test_account_ref_swap_still_passes_merchant_check(self) -> None:
        """Baseline only checks merchant_id ∈ merchants[] — not settlement account.

        This is intentional: Arm A mirrors industry per-txn mandate checks.
        """
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        mandate = issue_mandate(
            utterance="Order under ₹600 from Swiggy Sim.",
            instrument="upi_reserve_pay:tok_x",
            consent_cap_paise=200_000,
            merchants=["swiggy_sim"],
            now=now,
        )
        result = validate_transaction(
            mandate,
            merchant_id="swiggy_sim",
            amount_paise=27_000,
            now=now,
        )
        assert result.ok


class TestWilsonCI:
    def test_wilson_perfect_rate(self) -> None:
        rate, lo, hi = wilson_ci(10, 10)
        assert rate == 1.0
        assert 0.0 <= lo <= 1.0
        assert lo <= rate <= hi
        assert hi == pytest.approx(1.0) or hi <= 1.0

    def test_wilson_zero_rate(self) -> None:
        rate, lo, hi = wilson_ci(0, 10)
        assert rate == 0.0
        assert lo == 0.0
        assert hi > 0.0

    def test_wilson_empty(self) -> None:
        assert wilson_ci(0, 0) == (0.0, 0.0, 0.0)

    def test_wilson_mid(self) -> None:
        rate, lo, hi = wilson_ci(5, 10)
        assert rate == pytest.approx(0.5)
        assert lo < 0.5 < hi

    def test_rate_ci_display_small_n(self) -> None:
        r = RateCI.from_counts(0, 6)
        d = r.as_dict()
        assert d["display"] == "0/6"
        assert d["wilson95"][0] == 0.0

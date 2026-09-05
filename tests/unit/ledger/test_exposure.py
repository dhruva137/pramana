"""Unit tests — episode budget ledger exposure math."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.ledger.state import LedgerState, compute_ledger_state


@dataclass
class E:
    kind: str
    amount_paise: int
    payee_id: str
    decision_id: str | None = None


def test_empty_ledger():
    s = compute_ledger_state([])
    assert s == LedgerState(0, 0, 0, 0, frozenset())
    assert s.exposure_paise == 0


def test_open_hold_counts_toward_exposure():
    s = compute_ledger_state(
        [E("HOLD", 45000, "swiggy", "dec_1")]
    )
    assert s.held_paise == 45000
    assert s.committed_paise == 0
    assert s.exposure_paise == 45000
    assert s.txn_count == 1
    assert s.distinct_payees == frozenset({"swiggy"})


def test_hold_then_capture_moves_to_committed_exposure_stable():
    s = compute_ledger_state(
        [
            E("HOLD", 45000, "swiggy", "dec_1"),
            E("CAPTURE", 45000, "swiggy", "dec_1"),
        ]
    )
    assert s.held_paise == 0
    assert s.committed_paise == 45000
    assert s.exposure_paise == 45000
    assert s.txn_count == 1
    assert s.distinct_payees == frozenset({"swiggy"})


def test_hold_then_release_frees_exposure():
    s = compute_ledger_state(
        [
            E("HOLD", 45000, "swiggy", "dec_1"),
            E("RELEASE", 45000, "swiggy", "dec_1"),
        ]
    )
    assert s.held_paise == 0
    assert s.committed_paise == 0
    assert s.exposure_paise == 0
    assert s.txn_count == 0
    assert s.distinct_payees == frozenset()


def test_fragmentation_second_hold_stacks_exposure():
    """Thesis case: after one capture, another open hold adds exposure."""
    s = compute_ledger_state(
        [
            E("HOLD", 45000, "swiggy", "dec_1"),
            E("CAPTURE", 45000, "swiggy", "dec_1"),
            E("HOLD", 45000, "swiggy", "dec_2"),
        ]
    )
    assert s.committed_paise == 45000
    assert s.held_paise == 45000
    assert s.exposure_paise == 90000
    assert s.txn_count == 2
    assert s.distinct_payees == frozenset({"swiggy"})


def test_refund_reduces_committed():
    s = compute_ledger_state(
        [
            E("HOLD", 60000, "swiggy", "dec_1"),
            E("CAPTURE", 60000, "swiggy", "dec_1"),
            E("REFUND", 20000, "swiggy", "dec_1"),
        ]
    )
    assert s.committed_paise == 40000
    assert s.held_paise == 0
    assert s.exposure_paise == 40000


def test_distinct_payees_across_open_hold_and_capture():
    s = compute_ledger_state(
        [
            E("HOLD", 10000, "swiggy", "dec_1"),
            E("CAPTURE", 10000, "swiggy", "dec_1"),
            E("HOLD", 15000, "zepto", "dec_2"),
        ]
    )
    assert s.distinct_payees == frozenset({"swiggy", "zepto"})
    assert s.txn_count == 2


def test_ambiguous_keeps_hold_in_exposure():
    """AMBIGUOUS path: HOLD only — no RELEASE — exposure stays reserved."""
    s = compute_ledger_state([E("HOLD", 54000, "swiggy", "dec_amb")])
    assert s.exposure_paise == 54000
    assert s.held_paise == 54000


def test_ledger_state_to_dict_serialisable():
    s = compute_ledger_state([E("HOLD", 1, "swiggy", "d")])
    d = s.to_dict()
    assert d["exposure_paise"] == 1
    assert d["distinct_payees"] == ["swiggy"]
    assert d["distinct_payee_count"] == 1


def test_frozen():
    s = compute_ledger_state([])
    with pytest.raises(Exception):
        s.exposure_paise = 99  # type: ignore[misc]

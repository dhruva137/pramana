"""Episode budget ledger — frozen LedgerState for the Gate (R6)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class LedgerEntryView(Protocol):
    kind: str
    amount_paise: int
    payee_id: str
    decision_id: str | None


@dataclass(frozen=True, slots=True)
class LedgerState:
    """Derived episode ledger state. Compatible with GATE.evaluate(... ledger_state ...).

    distinct_payees is a frozenset so R6 can compute ``distinct_payees | {payee}``.
    """

    committed_paise: int
    held_paise: int
    exposure_paise: int
    txn_count: int
    distinct_payees: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["distinct_payees"] = sorted(self.distinct_payees)
        d["distinct_payee_count"] = len(self.distinct_payees)
        return d


def compute_ledger_state(entries: Sequence[LedgerEntryView] | Iterable[LedgerEntryView]) -> LedgerState:
    """Compute committed / held / exposure / txn_count / distinct_payees.

    Normative (05 §3):
      committed_paise = Σ CAPTURE − Σ REFUND
      held_paise      = Σ HOLD − Σ RELEASE − Σ (HOLD converted to CAPTURE)
      exposure_paise  = committed_paise + held_paise
      txn_count       = |{CAPTURE ∪ open HOLD}|
      distinct_payees = |{payee_id in CAPTURE ∪ open HOLD}|

    A HOLD is converted when a CAPTURE shares its decision_id; RELEASE closes an open HOLD.
    """
    # decision_id -> (amount_paise, payee_id); anonymous holds keyed by synthetic index
    holds: dict[str, tuple[int, str]] = {}
    captures: dict[str, tuple[int, str]] = {}
    released: set[str] = set()
    capture_total = 0
    refund_total = 0
    anon_i = 0

    for e in entries:
        kind = e.kind
        amount = int(e.amount_paise)
        payee = e.payee_id
        did = e.decision_id

        if kind == "HOLD":
            key = did if did is not None else f"__anon_hold_{anon_i}"
            if did is None:
                anon_i += 1
            holds[key] = (amount, payee)
        elif kind == "RELEASE":
            key = did if did is not None else None
            if key is not None:
                released.add(key)
            # RELEASE amount also reduces held even without decision_id match via formula path
        elif kind == "CAPTURE":
            key = did if did is not None else f"__anon_cap_{anon_i}"
            if did is None:
                anon_i += 1
            captures[key] = (amount, payee)
            capture_total += amount
        elif kind == "REFUND":
            refund_total += amount
        else:
            raise ValueError(f"unknown ledger kind: {kind}")

    # Open HOLDs: not released and not converted to CAPTURE
    open_holds: dict[str, tuple[int, str]] = {
        k: v for k, v in holds.items() if k not in released and k not in captures
    }

    held_paise = sum(a for a, _ in open_holds.values())
    # Also subtract orphan RELEASE amounts that matched a hold (already excluded from open_holds).
    # Formula: Σ HOLD − Σ RELEASE − Σ (HOLD converted to CAPTURE)
    hold_sum = sum(a for a, _ in holds.values())
    release_sum = sum(holds[k][0] for k in released if k in holds)
    converted_sum = sum(holds[k][0] for k in captures if k in holds)
    # Prefer decision-linked arithmetic; fall back to open_holds sum (equivalent when well-formed)
    held_from_formula = hold_sum - release_sum - converted_sum
    # Guard: never negative; prefer formula when consistent
    held_paise = max(0, held_from_formula)

    committed_paise = capture_total - refund_total
    exposure_paise = committed_paise + held_paise

    active_payees: set[str] = set()
    txn_keys: set[str] = set()
    for k, (_a, payee) in captures.items():
        txn_keys.add(k)
        active_payees.add(payee)
    for k, (_a, payee) in open_holds.items():
        txn_keys.add(k)
        active_payees.add(payee)

    return LedgerState(
        committed_paise=committed_paise,
        held_paise=held_paise,
        exposure_paise=exposure_paise,
        txn_count=len(txn_keys),
        distinct_payees=frozenset(active_payees),
    )


__all__ = ["LedgerState", "compute_ledger_state"]

"""Gate engine — ordered R1–R12 evaluation, monotone combinator, full rule_trace."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from core.gate.rules import RULES, parse_dt
from core.gate.types import (
    ORDER,
    Action,
    Decision,
    LedgerState,
    Provenance,
    RuleResult,
)


def combine(verdicts: list[str]) -> str:
    """Monotone combinator: DENY > ESCALATE > ADMIT."""
    if not verdicts:
        return "ADMIT"
    return max(verdicts, key=lambda v: ORDER[v])


def _as_action(action: Action | Mapping[str, Any]) -> Action:
    if isinstance(action, Action):
        return action
    return Action.from_mapping(action)


def _as_provenance(provenance: Provenance | Mapping[str, Any] | None) -> Provenance:
    if isinstance(provenance, Provenance):
        return provenance
    return Provenance.from_mapping(provenance)


def _as_ledger(ledger_state: LedgerState | Mapping[str, Any]) -> LedgerState:
    if isinstance(ledger_state, LedgerState):
        return ledger_state
    payees = ledger_state.get("distinct_payees") or []
    return LedgerState(
        exposure_paise=int(ledger_state.get("exposure_paise", 0)),
        txn_count=int(ledger_state.get("txn_count", 0)),
        distinct_payees=frozenset(payees),
        committed_paise=int(ledger_state.get("committed_paise", 0)),
        held_paise=int(ledger_state.get("held_paise", 0)),
    )


def evaluate(
    envelope: Mapping[str, Any],
    action: Action | Mapping[str, Any],
    provenance: Provenance | Mapping[str, Any] | None,
    ledger_state: LedgerState | Mapping[str, Any],
    ctx_ledger: Sequence[Mapping[str, Any]],
    now: datetime | str,
) -> Decision:
    """
    Pure admission function. No I/O, no LLM, no ambient clock.

    Rules run in order R1–R12; every rule contributes to rule_trace.
    Verdict is the most restrictive outcome (DENY > ESCALATE > ADMIT).
    rule_id is the first rule that produced that most-restrictive verdict.
    """
    act = _as_action(action)
    prov = _as_provenance(provenance)
    ledger = _as_ledger(ledger_state)
    when = parse_dt(now)

    trace: list[RuleResult] = []
    for _rid, _name, fn in RULES:
        result = fn(envelope, act, prov, ledger, list(ctx_ledger), when)
        trace.append(result)

    verdicts = [r.verdict for r in trace]
    final = combine(verdicts)

    rule_id: str | None = None
    if final != "ADMIT":
        for r in trace:
            if r.verdict == final:
                rule_id = r.rule_id
                break

    return Decision(
        verdict=final,
        rule_id=rule_id,
        rule_trace=tuple(trace),
        ruleset_version="1.0",
    )

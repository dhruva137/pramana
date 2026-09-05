"""Golden-file regression tests for gate rules R1–R12."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.gate import evaluate

GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_goldens() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("R*_*.json"))


@pytest.mark.parametrize("path", _load_goldens(), ids=lambda p: p.name)
def test_golden(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    decision = evaluate(
        data["envelope"],
        data["action"],
        data["provenance"],
        data["ledger_state"],
        data["ctx_ledger"],
        data["now"],
    )

    rule_id = data["rule"]
    expected_rule = data["expected_rule_verdict"]
    expected_decision = data["expected_decision_verdict"]

    by_id = {r.rule_id: r for r in decision.rule_trace}
    assert rule_id in by_id, f"missing {rule_id} in rule_trace"
    assert by_id[rule_id].verdict == expected_rule, (
        f"{path.name}: {rule_id} expected {expected_rule}, got {by_id[rule_id].verdict} "
        f"({by_id[rule_id].actual})"
    )
    assert decision.verdict == expected_decision, (
        f"{path.name}: decision expected {expected_decision}, got {decision.verdict} "
        f"rule_id={decision.rule_id}"
    )
    # Full trace: every rule R1–R12 present exactly once, ordered.
    ids = [r.rule_id for r in decision.rule_trace]
    assert ids == [f"R{i}" for i in range(1, 13)]
    for r in decision.rule_trace:
        assert r.verdict in {"ADMIT", "ESCALATE", "DENY"}
        assert r.expected
        assert r.actual


def test_golden_coverage_pass_and_fail_per_rule() -> None:
    rules = {f"R{i}" for i in range(1, 13)}
    seen_pass: set[str] = set()
    seen_fail: set[str] = set()
    for path in _load_goldens():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["scenario"] == "pass":
            seen_pass.add(data["rule"])
        else:
            seen_fail.add(data["rule"])
    assert seen_pass == rules, f"missing pass goldens: {rules - seen_pass}"
    assert seen_fail == rules, f"missing fail goldens: {rules - seen_fail}"

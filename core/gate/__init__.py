"""Pramana Gate — pure admission control (R1–R12)."""

from core.gate.engine import combine, evaluate
from core.gate.types import (
    ADMIT,
    DENY,
    ESCALATE,
    ORDER,
    Action,
    Decision,
    LedgerState,
    Provenance,
    RuleResult,
    Taint,
)

__all__ = [
    "ADMIT",
    "DENY",
    "ESCALATE",
    "ORDER",
    "Action",
    "Decision",
    "LedgerState",
    "Provenance",
    "RuleResult",
    "Taint",
    "combine",
    "evaluate",
]

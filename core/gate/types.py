"""Gate types — taint lattice, ledger snapshot, decisions, monotone ORDER."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping


class Taint(IntEnum):
    """Total order over trust. Lower is more trusted. Combination is max."""

    USER = 0
    RZP_VERIFIED = 1
    MERCHANT_STRUCTURED = 2
    MERCHANT_FREETEXT = 3
    WEB = 4
    TOOL_META = 5
    MODEL = 6

    @classmethod
    def parse(cls, value: Any) -> Taint:
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        if value is None:
            return cls.MODEL
        key = str(value).strip().upper()
        try:
            return cls[key]
        except KeyError as exc:
            raise ValueError(f"unknown taint label: {value!r}") from exc


# Monotone combinator order: DENY > ESCALATE > ADMIT
ORDER: dict[str, int] = {"ADMIT": 0, "ESCALATE": 1, "DENY": 2}

ADMIT = "ADMIT"
ESCALATE = "ESCALATE"
DENY = "DENY"


@dataclass(frozen=True)
class LedgerState:
    """Derived episode budget ledger snapshot (A6 owns persistence; gate is pure)."""

    exposure_paise: int
    txn_count: int
    distinct_payees: frozenset[str]
    committed_paise: int = 0
    held_paise: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.distinct_payees, frozenset):
            object.__setattr__(self, "distinct_payees", frozenset(self.distinct_payees))


@dataclass(frozen=True)
class Action:
    """Proposed money action. All monetary fields are integer paise."""

    kind: str
    amount_paise: int
    currency: str
    payee: Mapping[str, Any]
    items: tuple[Mapping[str, Any], ...]
    instrument: str
    delivery_address_hash: str | None = None
    human_confirmed: bool = False

    @staticmethod
    def from_mapping(data: Mapping[str, Any]) -> Action:
        items_raw = data.get("items") or ()
        items = tuple(dict(x) for x in items_raw)
        payee = dict(data.get("payee") or {})
        if "amount_paise" not in data:
            raise ValueError("action.amount_paise is required (integer paise)")
        return Action(
            kind=str(data.get("kind", "PAYMENT")),
            amount_paise=int(data["amount_paise"]),
            currency=str(data.get("currency", "INR")),
            payee=payee,
            items=items,
            instrument=str(data.get("instrument", "")),
            delivery_address_hash=data.get("delivery_address_hash"),
            human_confirmed=bool(data.get("human_confirmed", False)),
        )


@dataclass(frozen=True)
class Provenance:
    """Per-field provenance. Missing critical fields default to MODEL (R10)."""

    records: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @staticmethod
    def from_mapping(data: Mapping[str, Any] | None) -> Provenance:
        if not data:
            return Provenance(records={})
        # Accept either {"records": {...}} or flat field->record map
        if "records" in data and isinstance(data["records"], Mapping):
            raw = data["records"]
        else:
            raw = data
        return Provenance(records={str(k): dict(v) for k, v in raw.items()})

    def taint_of(self, field_name: str) -> Taint:
        rec = self.records.get(field_name)
        if rec is None:
            return Taint.MODEL
        return Taint.parse(rec.get("taint", "MODEL"))

    def record(self, field_name: str) -> Mapping[str, Any] | None:
        return self.records.get(field_name)


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    verdict: str
    expected: str
    actual: str
    inputs: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "verdict": self.verdict,
            "expected": self.expected,
            "actual": self.actual,
            "inputs": dict(self.inputs),
        }


@dataclass(frozen=True)
class Decision:
    verdict: str
    rule_id: str | None
    rule_trace: tuple[RuleResult, ...]
    ruleset_version: str = "1.0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "rule_id": self.rule_id,
            "ruleset_version": self.ruleset_version,
            "rule_trace": [r.as_dict() for r in self.rule_trace],
        }

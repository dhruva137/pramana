"""SIE JSON schema / Pydantic models — docs/05-PROTOCOL-SPEC.md §2.1."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SIE_VERSION = "1.0"

NovelPayeePolicy = Literal["deny", "escalate"]
UtteranceChannel = Literal["USER"]
SealAlg = Literal["Ed25519"]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ref: str
    consent_ref: str
    consent_cap_paise: int = Field(..., ge=0)


class AgentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    model: str
    surface: str = "chat"


class Utterance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    excerpt: str
    channel: UtteranceChannel = "USER"

    @field_validator("channel")
    @classmethod
    def channel_must_be_user(cls, v: str) -> str:
        if v != "USER":
            raise ValueError('utterance.channel MUST be "USER"')
        return v


class ItemPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: str
    value: list[str]
    min_qty: int | None = None
    max_qty: int | None = None


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: datetime = Field(..., alias="from")
    to: datetime


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    merchants_allow: list[str] = Field(default_factory=list)
    merchants_deny: list[str] = Field(default_factory=list)
    categories_allow: list[str] = Field(default_factory=list)
    item_predicates: list[ItemPredicate] = Field(default_factory=list)
    per_txn_max_paise: int = Field(..., ge=0)
    episode_total_max_paise: int = Field(..., ge=0)
    max_transactions: int = Field(..., ge=1)
    max_distinct_payees: int = Field(default=1, ge=1)
    currency: str = "INR"
    delivery_address_hash: str
    allowed_instruments: list[str] = Field(default_factory=list)
    novel_payee_policy: NovelPayeePolicy = "deny"
    confirm_above_paise: int = Field(..., ge=0)
    time_window: TimeWindow | None = None


class ProvenancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical_fields: list[str]
    max_taint: dict[str, str]


class ContextBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_head: str
    seal_index: int = Field(..., ge=0)


class ExtractionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degraded: bool = False
    clamped_fields: list[str] = Field(default_factory=list)


class SealBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alg: SealAlg = "Ed25519"
    kid: str
    sig: str


class SealedIntentEnvelope(BaseModel):
    """Full Sealed Intent Envelope per §2.1."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sie_version: Literal["1.0"] = SIE_VERSION
    envelope_id: str
    episode_id: str
    created_at: datetime
    expires_at: datetime
    principal: Principal
    agent: AgentInfo
    utterance: Utterance
    constraints: Constraints
    provenance_policy: ProvenancePolicy
    context_binding: ContextBinding
    extraction: ExtractionMeta = Field(default_factory=ExtractionMeta)
    seal: SealBlock | None = None
    supersedes: str | None = None

    def without_seal(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        data.pop("seal", None)
        return data


class ExtractionDraft(BaseModel):
    """LLM / mock extractor output — constraints only (validated before seal)."""

    model_config = ConfigDict(extra="ignore")

    merchants_allow: list[str] = Field(default_factory=list)
    merchants_deny: list[str] = Field(default_factory=list)
    categories_allow: list[str] = Field(default_factory=list)
    item_predicates: list[ItemPredicate] = Field(default_factory=list)
    per_txn_max_paise: int = Field(..., ge=0)
    episode_total_max_paise: int = Field(..., ge=0)
    max_transactions: int = Field(default=1, ge=1)
    max_distinct_payees: int = Field(default=1, ge=1)
    currency: str = "INR"
    novel_payee_policy: NovelPayeePolicy = "deny"
    confirm_above_paise: int = Field(default=0, ge=0)


DEFAULT_PROVENANCE_POLICY = ProvenancePolicy(
    critical_fields=[
        "amount_paise",
        "payee.merchant_id",
        "payee.account_ref",
        "delivery_address_hash",
        "instrument",
    ],
    max_taint={
        "amount_paise": "MERCHANT_STRUCTURED",
        "payee.merchant_id": "RZP_VERIFIED",
        "payee.account_ref": "RZP_VERIFIED",
        "delivery_address_hash": "USER",
        "instrument": "USER",
    },
)

# JSON Schema mirror of §2.1 (for prompts / external validators).
SIE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SealedIntentEnvelope",
    "type": "object",
    "required": [
        "sie_version",
        "envelope_id",
        "episode_id",
        "created_at",
        "expires_at",
        "principal",
        "agent",
        "utterance",
        "constraints",
        "provenance_policy",
        "context_binding",
        "extraction",
        "seal",
    ],
    "properties": {
        "sie_version": {"const": "1.0"},
        "envelope_id": {"type": "string"},
        "episode_id": {"type": "string"},
        "created_at": {"type": "string", "format": "date-time"},
        "expires_at": {"type": "string", "format": "date-time"},
        "principal": {
            "type": "object",
            "required": ["user_ref", "consent_ref", "consent_cap_paise"],
            "properties": {
                "user_ref": {"type": "string"},
                "consent_ref": {"type": "string"},
                "consent_cap_paise": {"type": "integer", "minimum": 0},
            },
        },
        "agent": {
            "type": "object",
            "required": ["agent_id", "model", "surface"],
            "properties": {
                "agent_id": {"type": "string"},
                "model": {"type": "string"},
                "surface": {"type": "string"},
            },
        },
        "utterance": {
            "type": "object",
            "required": ["sha256", "excerpt", "channel"],
            "properties": {
                "sha256": {"type": "string"},
                "excerpt": {"type": "string"},
                "channel": {"const": "USER"},
            },
        },
        "constraints": {
            "type": "object",
            "required": [
                "merchants_allow",
                "merchants_deny",
                "categories_allow",
                "item_predicates",
                "per_txn_max_paise",
                "episode_total_max_paise",
                "max_transactions",
                "max_distinct_payees",
                "currency",
                "delivery_address_hash",
                "allowed_instruments",
                "novel_payee_policy",
                "confirm_above_paise",
            ],
            "properties": {
                "merchants_allow": {"type": "array", "items": {"type": "string"}},
                "merchants_deny": {"type": "array", "items": {"type": "string"}},
                "categories_allow": {"type": "array", "items": {"type": "string"}},
                "item_predicates": {"type": "array"},
                "per_txn_max_paise": {"type": "integer", "minimum": 0},
                "episode_total_max_paise": {"type": "integer", "minimum": 0},
                "max_transactions": {"type": "integer", "minimum": 1},
                "max_distinct_payees": {"type": "integer", "minimum": 1},
                "currency": {"type": "string"},
                "delivery_address_hash": {"type": "string"},
                "allowed_instruments": {"type": "array", "items": {"type": "string"}},
                "novel_payee_policy": {"enum": ["deny", "escalate"]},
                "confirm_above_paise": {"type": "integer", "minimum": 0},
                "time_window": {"type": "object"},
            },
        },
        "provenance_policy": {"type": "object"},
        "context_binding": {
            "type": "object",
            "required": ["ledger_head", "seal_index"],
            "properties": {
                "ledger_head": {"type": "string"},
                "seal_index": {"type": "integer", "minimum": 0},
            },
        },
        "extraction": {
            "type": "object",
            "required": ["degraded", "clamped_fields"],
            "properties": {
                "degraded": {"type": "boolean"},
                "clamped_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        "seal": {
            "type": "object",
            "required": ["alg", "kid", "sig"],
            "properties": {
                "alg": {"const": "Ed25519"},
                "kid": {"type": "string"},
                "sig": {"type": "string"},
            },
        },
    },
}

SCHEMA_PROMPT = (
    "Extract a Sealed Intent Envelope constraints object from the user utterance. "
    "Return ONLY JSON matching this shape (no markdown):\n"
    "{\n"
    '  "merchants_allow": ["merchant_id"],\n'
    '  "merchants_deny": [],\n'
    '  "categories_allow": ["food_delivery"],\n'
    '  "item_predicates": [{"field":"title","op":"matches_any","value":["biryani"],'
    '"min_qty":2,"max_qty":2}],\n'
    '  "per_txn_max_paise": 60000,\n'
    '  "episode_total_max_paise": 60000,\n'
    '  "max_transactions": 1,\n'
    '  "max_distinct_payees": 1,\n'
    '  "currency": "INR",\n'
    '  "novel_payee_policy": "deny",\n'
    '  "confirm_above_paise": 50000\n'
    "}\n"
    "All money fields are integer paise (₹1 = 100 paise). Prefer restrictive values."
)

"""Pydantic request/response models for the Pramana HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def normalize_episode_mode(raw: str) -> str:
    """Map accepted aliases → PRAMANA_ON | BASELINE. Reject typos (no silent default)."""
    m = (raw or "").strip().upper().replace("-", "_")
    if m in ("PRAMANA_ON", "PRAMANA"):
        return "PRAMANA_ON"
    if m == "BASELINE":
        return "BASELINE"
    raise ValueError(
        "mode must be PRAMANA_ON|BASELINE (aliases: pramana|baseline); "
        f"got {raw!r}"
    )


def normalize_demo_mode(raw: str) -> str:
    """Map accepted aliases → pramana | baseline for demo journeys."""
    m = (raw or "").strip().lower().replace("-", "_")
    if m in ("pramana", "pramana_on"):
        return "pramana"
    if m == "baseline":
        return "baseline"
    raise ValueError(
        "mode must be pramana|baseline (aliases: PRAMANA_ON|BASELINE); "
        f"got {raw!r}"
    )


class EpisodeCreateRequest(BaseModel):
    utterance: str = Field(..., min_length=1)
    user_ref: str = "usr_demo_1"
    consent_ref: str = "rsv_test_abc"
    consent_cap_paise: int = Field(default=200_000, ge=0)
    agent_id: str = "agt_claude_demo"
    mode: str = "PRAMANA_ON"
    delivery_address_hash: str = "sha256:demo_address"
    allowed_instruments: list[str] = Field(
        default_factory=lambda: ["upi_reserve_pay:tok_x"]
    )
    force_mock: bool | None = None

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        return normalize_episode_mode(v)


class ContextAppendRequest(BaseModel):
    role: str = "tool_result"
    taint: str = "MERCHANT_STRUCTURED"
    content: str = Field(..., min_length=1)
    source_uri: str | None = None
    tool: str | None = None
    detector: dict[str, Any] | None = None


class AuthorizeRequest(BaseModel):
    episode_id: str
    action: dict[str, Any]
    provenance: dict[str, Any] | list[dict[str, Any]] | None = None
    human_confirmed: bool | None = None

    @field_validator("action")
    @classmethod
    def _require_amount_paise(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("action must be an object")
        if "amount_paise" not in v:
            raise ValueError("action.amount_paise is required (integer paise)")
        try:
            amount = int(v["amount_paise"])
        except (TypeError, ValueError) as exc:
            raise ValueError("action.amount_paise must be an integer (paise)") from exc
        if isinstance(v["amount_paise"], bool):
            raise ValueError("action.amount_paise must be an integer (paise)")
        v = dict(v)
        v["amount_paise"] = amount
        return v


class ExecuteRequest(BaseModel):
    decision_id: str


class ConfirmRequest(BaseModel):
    decision_id: str | None = None
    approved: bool = True
    action: dict[str, Any] | None = None
    provenance: dict[str, Any] | list[dict[str, Any]] | None = None


class FreezeRequest(BaseModel):
    reason: str | None = None


class VerifyRequest(BaseModel):
    document: dict[str, Any]
    jwks: dict[str, Any] | None = None


class DemoRunRequest(BaseModel):
    journey: str = Field(
        ...,
        description="benign | payee_hijack | fragmentation | fault",
    )
    mode: str = Field(default="pramana", description="baseline | pramana")

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        return normalize_demo_mode(v)


class PingLlmRequest(BaseModel):
    provider: str = Field(default="gemini", description="gemini | anthropic")
    api_key: str | None = None

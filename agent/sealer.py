"""Privileged sealer surface for the agent process.

Thin wrapper over ``core.seal`` — tools MUST remain absent (enforced in core.seal.extract).
"""

from __future__ import annotations

from typing import Any, Sequence

from core.seal.extract import (
    build_anthropic_request,
    build_gemini_request,
    last_llm_request,
)
from core.seal.sealer import ContextTaintedError, SealRequest, SealResult, seal

__all__ = [
    "ContextTaintedError",
    "SealRequest",
    "SealResult",
    "seal",
    "seal_utterance",
    "build_anthropic_request",
    "build_gemini_request",
    "last_llm_request",
]


def seal_utterance(
    utterance: str,
    *,
    user_ref: str,
    consent_ref: str,
    consent_cap_paise: int,
    agent_id: str = "agt_claude_demo",
    model: str = "mock-extractor",
    surface: str = "chat",
    episode_id: str | None = None,
    delivery_address_hash: str = "sha256:demo_address",
    allowed_instruments: list[str] | None = None,
    ledger_head: str | None = None,
    seal_index: int = 0,
    ctx_entries: Sequence[dict[str, Any]] | None = None,
    force_mock: bool | None = None,
    **kwargs: Any,
) -> SealResult:
    """Seal a trusted-channel utterance into an SIE."""
    req = SealRequest(
        utterance=utterance,
        user_ref=user_ref,
        consent_ref=consent_ref,
        consent_cap_paise=consent_cap_paise,
        agent_id=agent_id,
        model=model,
        surface=surface,
        episode_id=episode_id,
        delivery_address_hash=delivery_address_hash,
        allowed_instruments=allowed_instruments
        or ["upi_reserve_pay:tok_x"],
        ledger_head=ledger_head or ("sha256:" + ("0" * 64)),
        seal_index=seal_index,
        ctx_entries=ctx_entries,
        force_mock=force_mock,
        **kwargs,
    )
    return seal(req)

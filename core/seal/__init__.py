"""Sealed Intent Envelope (SIE) — schema, extraction, clamp, fallback, seal."""

from core.seal.clamp import clamp_envelope
from core.seal.fallback import restrictive_fallback
from core.seal.schema import (
    DEFAULT_PROVENANCE_POLICY,
    SIE_VERSION,
    SealedIntentEnvelope,
)
from core.seal.sealer import ContextTaintedError, SealRequest, SealResult, seal

__all__ = [
    "SIE_VERSION",
    "DEFAULT_PROVENANCE_POLICY",
    "SealedIntentEnvelope",
    "clamp_envelope",
    "restrictive_fallback",
    "SealRequest",
    "SealResult",
    "ContextTaintedError",
    "seal",
]

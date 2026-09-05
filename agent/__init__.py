"""Pramana agent surfaces: sealer (privileged), shopper (quarantined), baseline (Arm A)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "MandateValidationResult",
    "Proposal",
    "QuarantinedShopper",
    "SignedMandate",
    "issue_mandate",
    "validate_transaction",
    "wrap_untrusted",
]


def __getattr__(name: str) -> Any:
    if name in {
        "MandateValidationResult",
        "SignedMandate",
        "issue_mandate",
        "validate_transaction",
    }:
        from agent import baseline as _baseline

        return getattr(_baseline, name)
    if name in {"Proposal", "QuarantinedShopper", "wrap_untrusted"}:
        from agent import shopper as _shopper

        return getattr(_shopper, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

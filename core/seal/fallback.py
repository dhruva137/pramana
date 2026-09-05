"""Restrictive fallback when extraction fails — §2.3.

Failure mode is friction, never permission.
"""

from __future__ import annotations

import re
from typing import Iterable

from core.seal.schema import ExtractionDraft

# Amounts: ₹600, Rs 600, Rs.600, INR 600, under 600, 600 ke andar / tak / max
_AMOUNT_RE = re.compile(
    r"(?:"
    r"(?:₹|rs\.?|inr)\s*(\d{1,7}(?:\.\d{1,2})?)"
    r"|"
    r"(?:under|within|max|upto|up\s*to|below|ke\s+andar|tak)\s+(?:₹|rs\.?|inr)?\s*(\d{1,7})"
    r"|"
    r"(\d{1,7})\s*(?:ke\s+andar|tak|rupees?|rs\.?)"
    r")",
    re.IGNORECASE,
)

_MERCHANT_ALIASES: dict[str, str] = {
    "swiggy": "swiggy",
    "zomato": "zomato",
    "blinkit": "blinkit",
    "bigbasket": "bigbasket",
    "big basket": "bigbasket",
    "amazon": "amazon",
    "flipkart": "flipkart",
    "zepto": "zepto",
    "instamart": "instamart",
}


def parse_stated_amounts_paise(utterance: str) -> list[int]:
    """Collect user-stated amounts as integer paise (treat bare figures as rupees)."""
    found: list[int] = []
    for m in _AMOUNT_RE.finditer(utterance):
        raw = next(g for g in m.groups() if g is not None)
        rupees = float(raw)
        found.append(int(round(rupees * 100)))
    return found


def merchants_named_in_utterance(utterance: str) -> list[str]:
    lower = utterance.lower()
    out: list[str] = []
    for alias, mid in sorted(_MERCHANT_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in lower and mid not in out:
            out.append(mid)
    return out


def restrictive_fallback(
    utterance: str,
    *,
    consent_cap_paise: int,
    stated_amounts_paise: Iterable[int] | None = None,
) -> ExtractionDraft:
    """§2.3 restrictive envelope draft.

    - max_transactions = 1
    - episode_total_max_paise = per_txn_max_paise = min(any user-stated amount, consent_cap)
    - confirm_above_paise = 0 (always confirm)
    - novel_payee_policy = deny
    - merchants_allow = merchants explicitly named (empty ⇒ nothing admissible)
    """
    amounts = list(stated_amounts_paise) if stated_amounts_paise is not None else parse_stated_amounts_paise(
        utterance
    )
    if amounts:
        cap = min(min(amounts), consent_cap_paise)
    else:
        # No stated amount → tightest money bound: zero spend without confirmation path;
        # still bound by consent so clamp stays well-defined. Prefer friction: 0 paise.
        cap = 0

    merchants = merchants_named_in_utterance(utterance)

    return ExtractionDraft(
        merchants_allow=merchants,
        merchants_deny=[],
        categories_allow=[],
        item_predicates=[],
        per_txn_max_paise=cap,
        episode_total_max_paise=cap,
        max_transactions=1,
        max_distinct_payees=1,
        currency="INR",
        novel_payee_policy="deny",
        confirm_above_paise=0,
    )

"""Sealer extraction — MOCK heuristics or optional Gemini / Anthropic.

The privileged sealer client is constructed **without tools**. Tests assert
that request payloads never contain a ``tools`` key.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from core.seal.fallback import merchants_named_in_utterance, parse_stated_amounts_paise
from core.seal.schema import SCHEMA_PROMPT, ExtractionDraft, ItemPredicate

# Last outbound LLM request body (for unit tests). Never includes tools.
_LAST_REQUEST: dict[str, Any] | None = None

_WORD_QTY = {
    "one": 1,
    "ek": 1,
    "a": 1,
    "an": 1,
    "two": 2,
    "do": 2,
    "don": 2,
    "three": 3,
    "teen": 3,
    "four": 4,
    "char": 4,
    "five": 5,
    "panch": 5,
}

_ITEM_TERMS = (
    "biryani",
    "biriyani",
    "pizza",
    "burger",
    "pasta",
    "thali",
    "dosa",
    "idli",
    "milk",
    "headphones",
    "earphone",
    "grocer",
    "dinner",
    "lunch",
    "breakfast",
)

_CATEGORY_BY_MERCHANT = {
    "swiggy": "food_delivery",
    "zomato": "food_delivery",
    "blinkit": "grocery",
    "zepto": "grocery",
    "instamart": "grocery",
    "bigbasket": "grocery",
    "amazon": "retail",
    "flipkart": "retail",
}


def last_llm_request() -> dict[str, Any] | None:
    """Return the most recent LLM request body (test hook)."""
    return _LAST_REQUEST


def clear_last_llm_request() -> None:
    global _LAST_REQUEST
    _LAST_REQUEST = None


def _mock_mode() -> bool:
    flag = os.environ.get("MOCK_MODE", "true").strip().lower()
    if flag in ("0", "false", "no", "off"):
        # Still mock if no API keys
        return not (
            os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        )
    return True


def build_anthropic_request(utterance: str, *, model: str | None = None) -> dict[str, Any]:
    """Anthropic Messages body — **no tools key**."""
    body = {
        "model": model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        "max_tokens": 2048,
        "system": SCHEMA_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": f"User utterance:\n{utterance}",
            }
        ],
    }
    assert "tools" not in body
    return body


def build_gemini_request(utterance: str) -> dict[str, Any]:
    """Generative Language API body — **no tools / toolConfig**."""
    body = {
        "system_instruction": {"parts": [{"text": SCHEMA_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"User utterance:\n{utterance}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    assert "tools" not in body
    assert "toolConfig" not in body
    return body


def _qty_from_utterance(utterance: str) -> int | None:
    lower = utterance.lower()
    m = re.search(
        r"\b(\d+|one|two|three|four|five|ek|do|don|teen|char|panch)\b"
        r".{0,24}\b(biryani|biriyani|pizza|burger|dosa|idli|thali|headphones?)\b",
        lower,
    )
    if not m:
        m = re.search(
            r"\b(biryani|biriyani|pizza|burger).{0,12}\b"
            r"(\d+|do|don|two|teen|three)\b",
            lower,
        )
        if m:
            token = m.group(2)
            return int(token) if token.isdigit() else _WORD_QTY.get(token)
        return None
    token = m.group(1)
    return int(token) if token.isdigit() else _WORD_QTY.get(token)


def _items_from_utterance(utterance: str) -> list[str]:
    lower = utterance.lower()
    found: list[str] = []
    for term in _ITEM_TERMS:
        if term in lower and term not in found:
            # normalize biriyani → biryani
            norm = "biryani" if term in ("biryani", "biriyani") else term
            if norm not in found:
                found.append(norm)
    return found


def mock_extract(utterance: str, *, consent_cap_paise: int) -> ExtractionDraft:
    """Deterministic regex / heuristic extractor — no network."""
    merchants = merchants_named_in_utterance(utterance)
    amounts = parse_stated_amounts_paise(utterance)
    if amounts:
        cap = min(min(amounts), consent_cap_paise)
    else:
        # Default demo ceiling when user omits amount: still under consent.
        cap = min(consent_cap_paise, 100_000)

    items = _items_from_utterance(utterance)
    qty = _qty_from_utterance(utterance)
    predicates: list[ItemPredicate] = []
    for item in items:
        if item in ("dinner", "lunch", "breakfast", "grocer"):
            continue
        pred: dict[str, Any] = {
            "field": "title",
            "op": "matches_any",
            "value": [item],
        }
        if qty is not None:
            pred["min_qty"] = qty
            pred["max_qty"] = qty
        predicates.append(ItemPredicate.model_validate(pred))

    categories: list[str] = []
    for m in merchants:
        cat = _CATEGORY_BY_MERCHANT.get(m)
        if cat and cat not in categories:
            categories.append(cat)
    if not categories and items:
        categories = ["food_delivery"]

    confirm = min(cap, 50_000) if cap > 0 else 0

    return ExtractionDraft(
        merchants_allow=merchants,
        merchants_deny=[],
        categories_allow=categories,
        item_predicates=predicates,
        per_txn_max_paise=cap,
        episode_total_max_paise=cap,
        max_transactions=1,
        max_distinct_payees=1,
        currency="INR",
        novel_payee_policy="deny",
        confirm_above_paise=confirm,
    )


def _parse_json_content(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _anthropic_extract(utterance: str) -> ExtractionDraft:
    global _LAST_REQUEST
    api_key = os.environ["ANTHROPIC_API_KEY"]
    body = build_anthropic_request(utterance)
    _LAST_REQUEST = body
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return ExtractionDraft.model_validate(_parse_json_content(text))


def _gemini_extract(utterance: str) -> ExtractionDraft:
    global _LAST_REQUEST
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    body = build_gemini_request(utterance)
    _LAST_REQUEST = body
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, params={"key": api_key}, json=body)
        resp.raise_for_status()
        data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    return ExtractionDraft.model_validate(_parse_json_content(text))


def _try_google_generativeai(utterance: str) -> ExtractionDraft | None:
    """Optional google-generativeai SDK path (still no tools)."""
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # Construct without tools — do not pass tools=
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SCHEMA_PROMPT,
    )
    global _LAST_REQUEST
    _LAST_REQUEST = {
        "provider": "google-generativeai",
        "model": model_name,
        "system_instruction": SCHEMA_PROMPT,
        "contents": utterance,
        # intentionally no "tools"
    }
    assert "tools" not in _LAST_REQUEST
    result = model.generate_content(
        f"User utterance:\n{utterance}",
        generation_config={"temperature": 0, "response_mime_type": "application/json"},
    )
    return ExtractionDraft.model_validate(_parse_json_content(result.text or ""))


def extract_constraints(
    utterance: str,
    *,
    consent_cap_paise: int,
    force_mock: bool | None = None,
) -> ExtractionDraft:
    """Extract constraints. Prefer MOCK; else Anthropic / Gemini. Raises on hard failure."""
    use_mock = _mock_mode() if force_mock is None else force_mock
    if use_mock:
        return mock_extract(utterance, consent_cap_paise=consent_cap_paise)

    if os.environ.get("ANTHROPIC_API_KEY"):
        return _anthropic_extract(utterance)

    if os.environ.get("GEMINI_API_KEY"):
        sdk = _try_google_generativeai(utterance)
        if sdk is not None:
            return sdk
        return _gemini_extract(utterance)

    return mock_extract(utterance, consent_cap_paise=consent_cap_paise)

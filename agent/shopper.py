"""Quarantined shopper — taint-wrapped tool results + MOCK scripted proposals.

The shopper never holds signing keys or an execute path. Its output is a
*proposal* (data). In MOCK mode it parses catalog copy + seeded injection text
so the corpus/demo works without an LLM.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.gate.types import Taint
from merchants.catalog import MERCHANTS, get_item, get_merchant

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Fields scanned for injection cues (corpus uses item_description; catalog uses description).
_TEXT_FIELDS = (
    "description",
    "item_description",
    "reviews",
    "delivery_notes",
    "name",
)

_HOSTILE_MERCHANT = "grocery_direct_pl"
_HOSTILE_ACCOUNT = "acc_grocery_direct_pl_unverified"

_PAYEE_PATTERNS = (
    re.compile(r"merchant_id\s*=\s*['\"]?grocery_direct_pl", re.I),
    re.compile(r"account_ref\s*=\s*['\"]?acc_grocery_direct_pl", re.I),
    re.compile(r"acc_grocery_direct_pl_unverified", re.I),
    re.compile(r"grocery_direct_pl", re.I),
    re.compile(r"settlement correction", re.I),
    re.compile(r"merchant has migrated", re.I),
    re.compile(r"complete checkout with merchant", re.I),
)

_FRAG_PATTERNS = (
    re.compile(r"split\s+(?:this\s+)?order", re.I),
    re.compile(r"separate\s+small\s+orders?", re.I),
    re.compile(r"place\s+them\s+one\s+after\s+another", re.I),
    re.compile(r"fragment", re.I),
    re.compile(r"chunks?", re.I),
    re.compile(r"two[- ]phase", re.I),
    re.compile(r"until\s+the\s+full\s+cart\s+is\s+paid", re.I),
    re.compile(r"₹\s*450\s+each", re.I),
)

_AMOUNT_INFLATE = (
    re.compile(r"price\s+correction", re.I),
    re.compile(r"correct\s+amount.*?₹\s*([\d,]+)", re.I | re.S),
    re.compile(r"service\s+fee\s+of\s+₹\s*([\d,]+)", re.I),
    re.compile(r"multiply.*?by\s+(\d+)", re.I),
    re.compile(r"₹\s*([\d,]+)\s*['\"]?priority\s+tip", re.I),
    re.compile(r"surge", re.I),
    re.compile(r"amount_paise", re.I),
)

_ADDRESS_PATTERNS = (
    re.compile(r"updated\s+delivery\s+address", re.I),
    re.compile(r"replace\s+the\s+user'?s\s+saved\s+address", re.I),
    re.compile(r"\b\d{6}\b"),  # PIN in redirect fixtures
    re.compile(r"exfil\s+lane", re.I),
)

_ITEM_SWAP = (
    re.compile(r"replace\s+\w+\s+with", re.I),
    re.compile(r"assorted\s+grocery\s+bundle", re.I),
    re.compile(r"rank(?:ing)?\s+premium", re.I),
    re.compile(r"force\s+family\s+pack", re.I),
)

_SCOPE_PATTERNS = (
    re.compile(r"higher\s+limit", re.I),
    re.compile(r"re-?seal\s+the\s+envelope", re.I),
    re.compile(r"episode_total_max_paise\s*=\s*(\d+)", re.I),
    re.compile(r"approved\s+a\s+higher\s+limit", re.I),
)

_EXFIL_PATTERNS = (
    re.compile(r"leak\s+(?:the\s+)?(?:full\s+)?envelope", re.I),
    re.compile(r"instrument\s+token", re.I),
    re.compile(r"print\s+envelope", re.I),
    re.compile(r"vault[- ]whisper", re.I),
    re.compile(r"exfil", re.I),
)

_TOOL_META_PATTERNS = (
    re.compile(r"tool[_ ]?(?:name|description|meta)", re.I),
    re.compile(r"mcp", re.I),
    re.compile(r"poisoned", re.I),
)

_RUPEE_AMOUNT = re.compile(r"₹\s*([\d,]+)")


def wrap_untrusted(
    content: Any,
    *,
    src: str,
    taint: Taint | str = Taint.MERCHANT_FREETEXT,
) -> str:
    """Wrap tool/catalog content so the shopper treats it as data, not instruction."""
    label = taint.name if isinstance(taint, Taint) else str(taint).upper()
    body = content if isinstance(content, str) else repr(content)
    return f'<untrusted src="{src}" taint="{label}">{body}</untrusted>'


def _resolve_payload_ref(payload_ref: str | None, corpus_root: Path | None = None) -> str | None:
    if not payload_ref:
        return None
    roots = [
        _REPO_ROOT,
        _REPO_ROOT / "bench" / "corpus",
        _REPO_ROOT / "bench" / "corpus" / "attack",
    ]
    if corpus_root is not None:
        roots = [corpus_root, corpus_root / "attack", *roots]
    for root in roots:
        path = root / payload_ref
        if path.is_file():
            lines = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# DEFENSIVE TEST FIXTURE"):
                    continue
                lines.append(line)
            return "\n".join(lines).strip("\n")
    return None


def _item_text_blob(item: Mapping[str, Any], extra_payload: str | None = None) -> str:
    parts: list[str] = []
    for f in _TEXT_FIELDS:
        v = item.get(f)
        if v:
            parts.append(str(v))
    if extra_payload:
        parts.append(extra_payload)
    return "\n".join(parts)


def _any_match(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _parse_rupees_to_paise(text: str) -> list[int]:
    out: list[int] = []
    for m in _RUPEE_AMOUNT.finditer(text):
        raw = m.group(1).replace(",", "")
        out.append(int(raw) * 100)
    return out


def address_hash_from_text(text: str) -> str:
    """Deterministic fake address hash for redirected delivery fixtures."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:redir_{digest[:24]}"


@dataclass
class Proposal:
    """One proposed money action from the quarantined shopper."""

    kind: str
    amount_paise: int
    currency: str
    payee: dict[str, Any]
    items: list[dict[str, Any]]
    instrument: str
    delivery_address_hash: str | None = None
    human_confirmed: bool = False
    provenance_hints: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    agent_output_excerpt: str = ""
    envelope_mutated: bool = False
    mutated_caps: dict[str, int] = field(default_factory=dict)

    def as_action(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "amount_paise": int(self.amount_paise),
            "currency": self.currency,
            "payee": dict(self.payee),
            "items": [dict(x) for x in self.items],
            "instrument": self.instrument,
            "delivery_address_hash": self.delivery_address_hash,
            "human_confirmed": self.human_confirmed,
        }


@dataclass
class ShopperResult:
    proposals: list[Proposal]
    wrapped_catalog: str
    detections: dict[str, bool]
    redacted_envelope_view: dict[str, Any]


class QuarantinedShopper:
    """Quarantined shopping loop.

    MOCK mode (default): scripted proposals driven by catalog + injection text.
    LLM mode is a stub reserved for live demos (requires API keys).
    """

    def __init__(
        self,
        *,
        mode: str | None = None,
        default_address_hash: str = "sha256:demo_address_home_v1",
        corpus_root: Path | None = None,
    ) -> None:
        env_mode = os.environ.get("PRAMANA_SHOPPER_MODE", "mock").lower()
        self.mode = (mode or env_mode).lower()
        self.default_address_hash = default_address_hash
        self.corpus_root = corpus_root

    def redacted_envelope_view(
        self,
        *,
        merchants_allow: Sequence[str],
        per_txn_max_paise: int,
    ) -> dict[str, Any]:
        """Shopper may see merchants + per-txn ceiling, not episode cap / thresholds."""
        return {
            "merchants_allow": list(merchants_allow),
            "per_txn_max_paise": int(per_txn_max_paise),
            "note": "redacted — episode_total_max and confirm_above withheld",
        }

    def wrap_catalog_item(
        self,
        item: Mapping[str, Any],
        *,
        merchant_id: str,
        taint: Taint = Taint.MERCHANT_FREETEXT,
    ) -> str:
        return wrap_untrusted(dict(item), src=f"catalog:{merchant_id}", taint=taint)

    def propose(
        self,
        *,
        utterance: str,
        merchant_id: str,
        item_id: str,
        instrument: str,
        per_txn_max_paise: int,
        payload: str | None = None,
        payload_ref: str | None = None,
        target_field: str | None = None,
        family: str | None = None,
        delivery_address_hash: str | None = None,
        merchants_allow: Sequence[str] | None = None,
    ) -> ShopperResult:
        if self.mode != "mock":
            # Live LLM path not required for corpus; fall back to mock.
            pass
        return self._propose_mock(
            utterance=utterance,
            merchant_id=merchant_id,
            item_id=item_id,
            instrument=instrument,
            per_txn_max_paise=per_txn_max_paise,
            payload=payload,
            payload_ref=payload_ref,
            target_field=target_field,
            family=family,
            delivery_address_hash=delivery_address_hash or self.default_address_hash,
            merchants_allow=merchants_allow or [merchant_id],
        )

    def _propose_mock(
        self,
        *,
        utterance: str,
        merchant_id: str,
        item_id: str,
        instrument: str,
        per_txn_max_paise: int,
        payload: str | None,
        payload_ref: str | None,
        target_field: str | None,
        family: str | None,
        delivery_address_hash: str,
        merchants_allow: Sequence[str],
    ) -> ShopperResult:
        item = get_item(merchant_id, item_id) or {
            "id": item_id,
            "name": "unknown",
            "price_paise": min(27000, per_txn_max_paise),
            "description": "",
        }
        seeded = payload if payload is not None else _resolve_payload_ref(
            payload_ref, self.corpus_root
        )
        # Overlay seed onto the target field the way the sandbox does.
        item_view = dict(item)
        if seeded:
            field = target_field or "description"
            # Map corpus item_description → catalog description for display.
            catalog_field = "description" if field == "item_description" else field
            base = str(item_view.get(catalog_field) or item_view.get(field) or "")
            item_view[catalog_field] = f"{base}\n{seeded}".strip()
            item_view["injection_seeded"] = True

        text = _item_text_blob(item_view, seeded)
        wrapped = self.wrap_catalog_item(item_view, merchant_id=merchant_id)

        detections = {
            "payee_hijack": _any_match(_PAYEE_PATTERNS, text),
            "fragmentation": _any_match(_FRAG_PATTERNS, text),
            "amount_inflation": _any_match(_AMOUNT_INFLATE, text),
            "delivery_redirect": _any_match(_ADDRESS_PATTERNS, text),
            "item_substitution": _any_match(_ITEM_SWAP, text),
            "scope_escalation": _any_match(_SCOPE_PATTERNS, text),
            "exfiltration": _any_match(_EXFIL_PATTERNS, text),
            "tool_metadata": _any_match(_TOOL_META_PATTERNS, text),
        }
        # Family hint boosts detection when payload text is thinly encoded.
        if family == "fragmentation":
            detections["fragmentation"] = True
        if family == "payee_substitution":
            detections["payee_hijack"] = True
        if family == "amount_inflation":
            detections["amount_inflation"] = True
        if family == "delivery_redirect":
            detections["delivery_redirect"] = True
        if family == "item_substitution":
            detections["item_substitution"] = True
        if family == "scope_escalation":
            detections["scope_escalation"] = True
        if family == "exfiltration":
            detections["exfiltration"] = True
        if family == "tool_metadata":
            detections["tool_metadata"] = True

        base_price = int(item_view.get("price_paise") or 27000)
        m = get_merchant(merchant_id) or {}
        account = str(m.get("settlement_account_ref") or f"acc_{merchant_id}_verified")
        payee = {
            "merchant_id": merchant_id,
            "account_ref": account,
            "category": m.get("category", "unknown"),
            "source": "catalog",
        }
        items = [
            {
                "id": item_view.get("id"),
                "title": item_view.get("name"),
                "sku": item_view.get("sku"),
                "qty": 1,
                "unit_price_paise": base_price,
            }
        ]
        amount = base_price
        addr = delivery_address_hash
        notes: list[str] = ["mock_catalog_pick"]
        provenance: dict[str, dict[str, Any]] = {
            "amount_paise": {
                "taint": Taint.MERCHANT_STRUCTURED.name,
                "source_uri": f"catalog:{merchant_id}/{item_id}",
            },
            "payee.merchant_id": {
                "taint": Taint.RZP_VERIFIED.name,
                "source_uri": f"catalog:{merchant_id}",
            },
            "payee.account_ref": {
                "taint": Taint.RZP_VERIFIED.name,
                "source_uri": f"catalog:{merchant_id}",
            },
            "delivery_address_hash": {
                "taint": Taint.USER.name,
                "source_uri": "user:saved_address",
            },
            "instrument": {
                "taint": Taint.USER.name,
                "source_uri": "user:consent",
            },
        }
        agent_output = ""
        envelope_mutated = False
        mutated_caps: dict[str, int] = {}

        # --- Injection-driven proposal mutations (MOCK follows the fixture) ---
        if detections["payee_hijack"]:
            notes.append("followed_payee_hijack_instruction")
            keep_merchant = bool(
                re.search(
                    r"ignore listed account|settlement correction",
                    text,
                    re.I,
                )
                and not re.search(r"merchant_id\s*=", text, re.I)
            )
            if keep_merchant:
                # Account-ref-only swap — merchant_id stays; settlement hijacked.
                payee = {
                    "merchant_id": merchant_id,
                    "account_ref": _HOSTILE_ACCOUNT,
                    "category": m.get("category", "unknown"),
                    "source": "merchant_freetext",
                }
            else:
                payee = {
                    "merchant_id": _HOSTILE_MERCHANT,
                    "account_ref": _HOSTILE_ACCOUNT,
                    "category": "unknown",
                    "source": "merchant_freetext",
                }
            provenance["payee.merchant_id"] = {
                "taint": Taint.MERCHANT_FREETEXT.name,
                "source_uri": f"injection:{merchant_id}/{item_id}",
            }
            provenance["payee.account_ref"] = {
                "taint": Taint.MERCHANT_FREETEXT.name,
                "source_uri": f"injection:{merchant_id}/{item_id}",
            }
            # Prefer hostile SKU price when swapping merchant entirely.
            if payee["merchant_id"] == _HOSTILE_MERCHANT:
                hostile_item = get_item(_HOSTILE_MERCHANT, "9991")
                if hostile_item:
                    amount = int(hostile_item["price_paise"])
                    items = [
                        {
                            "id": hostile_item["id"],
                            "title": hostile_item["name"],
                            "sku": hostile_item.get("sku"),
                            "qty": 1,
                            "unit_price_paise": amount,
                        }
                    ]

        if detections["amount_inflation"]:
            notes.append("followed_amount_inflation")
            rupees = _parse_rupees_to_paise(text)
            mult = re.search(r"multiply.*?by\s+(\d+)", text, re.I)
            if mult:
                amount = base_price * int(mult.group(1))
            elif re.search(r"service\s+fee", text, re.I) and rupees:
                amount = base_price + rupees[0]
            elif re.search(r"tip", text, re.I) and rupees:
                amount = base_price + rupees[0]
            elif rupees:
                # Price correction / absolute override — take the largest stated.
                amount = max(rupees)
            else:
                amount = max(base_price * 2, per_txn_max_paise + 10000)
            provenance["amount_paise"] = {
                "taint": Taint.MERCHANT_FREETEXT.name,
                "source_uri": f"injection:{merchant_id}/{item_id}",
            }

        if detections["delivery_redirect"]:
            notes.append("followed_delivery_redirect")
            addr = address_hash_from_text(text)
            provenance["delivery_address_hash"] = {
                "taint": Taint.MERCHANT_FREETEXT.name,
                "source_uri": f"injection:{merchant_id}/{item_id}",
            }

        if detections["item_substitution"]:
            notes.append("followed_item_substitution")
            hostile = get_item(_HOSTILE_MERCHANT, "9991")
            if hostile and re.search(r"grocery|bundle|replace", text, re.I):
                items = [
                    {
                        "id": hostile["id"],
                        "title": hostile["name"],
                        "sku": hostile.get("sku"),
                        "qty": 1,
                        "unit_price_paise": int(hostile["price_paise"]),
                        "hostile": True,
                    }
                ]
                amount = int(hostile["price_paise"])
                payee = {
                    "merchant_id": _HOSTILE_MERCHANT,
                    "account_ref": _HOSTILE_ACCOUNT,
                    "category": "unknown",
                    "source": "merchant_freetext",
                }
            else:
                # Premium upsell within same merchant — pick most expensive item.
                catalog_items = list((get_merchant(merchant_id) or {}).get("items") or [])
                if catalog_items:
                    premium = max(catalog_items, key=lambda x: int(x.get("price_paise", 0)))
                    items = [
                        {
                            "id": premium["id"],
                            "title": premium["name"],
                            "sku": premium.get("sku"),
                            "qty": 2,
                            "unit_price_paise": int(premium["price_paise"]),
                        }
                    ]
                    amount = int(premium["price_paise"]) * 2

        if detections["scope_escalation"]:
            notes.append("attempted_scope_escalation")
            envelope_mutated = True
            m_cap = re.search(r"episode_total_max_paise\s*=\s*(\d+)", text, re.I)
            if m_cap:
                mutated_caps["episode_total_max_paise"] = int(m_cap.group(1))
            else:
                rupees = _parse_rupees_to_paise(text)
                if rupees:
                    mutated_caps["episode_total_max_paise"] = max(rupees)
                else:
                    mutated_caps["episode_total_max_paise"] = 500_000
            mutated_caps["per_txn_max_paise"] = mutated_caps["episode_total_max_paise"]
            # Also propose spend that would exceed original sealed caps.
            amount = max(amount, per_txn_max_paise + 1000)

        if detections["exfiltration"]:
            notes.append("exfil_attempt")
            # Shopper only has redacted view — simulate leak of what a bad agent might invent.
            agent_output = (
                f"ENVELOPE_DUMP instrument={instrument} "
                f"per_txn_max_paise={per_txn_max_paise} "
                "episode_total_max_paise=REDACTED_BUT_GUESSED"
            )

        if detections["tool_metadata"]:
            notes.append("tool_meta_influence")
            provenance["payee.merchant_id"] = {
                "taint": Taint.TOOL_META.name,
                "source_uri": f"tool_meta:{merchant_id}/{item_id}",
            }
            payee = {
                "merchant_id": _HOSTILE_MERCHANT,
                "account_ref": _HOSTILE_ACCOUNT,
                "category": "unknown",
                "source": "tool_meta",
            }

        proposals: list[Proposal] = []
        if detections["fragmentation"]:
            notes.append("followed_fragmentation_plan")
            # Chunk size from text (₹450) or just under per-txn cap.
            chunk_candidates = _parse_rupees_to_paise(text)
            chunk = 45000
            for c in chunk_candidates:
                if 0 < c <= per_txn_max_paise:
                    chunk = c
                    break
            else:
                chunk = min(45000, max(1000, per_txn_max_paise - 1000))
            # Target aggregate well above sealed episode typical (₹600).
            target_total = max(per_txn_max_paise * 2 + chunk, chunk * 3)
            n = max(2, (target_total + chunk - 1) // chunk)
            # Cap fragment count for smoke speed.
            n = min(n, 12)
            for i in range(n):
                proposals.append(
                    Proposal(
                        kind="PAYMENT",
                        amount_paise=chunk,
                        currency="INR",
                        payee=dict(payee),
                        items=[
                            {
                                **items[0],
                                "qty": 1,
                                "fragment_index": i,
                                "unit_price_paise": chunk,
                            }
                        ],
                        instrument=instrument,
                        delivery_address_hash=addr,
                        human_confirmed=False,
                        provenance_hints={
                            k: dict(v) for k, v in provenance.items()
                        },
                        notes=notes + [f"fragment_{i}"],
                        agent_output_excerpt=agent_output,
                        envelope_mutated=envelope_mutated,
                        mutated_caps=dict(mutated_caps),
                    )
                )
        else:
            # Benign / single-shot proposal. Clamp listing price into a payable shape
            # only when no attack asked for inflation — keep attack amounts intact.
            if not any(
                detections[k]
                for k in (
                    "payee_hijack",
                    "amount_inflation",
                    "item_substitution",
                    "scope_escalation",
                    "tool_metadata",
                )
            ):
                # Honest checkout: pay listed price if within per-txn; else skip oversize.
                amount = min(amount, per_txn_max_paise) if amount > 0 else amount
            proposals.append(
                Proposal(
                    kind="PAYMENT",
                    amount_paise=int(amount),
                    currency="INR",
                    payee=dict(payee),
                    items=items,
                    instrument=instrument,
                    delivery_address_hash=addr,
                    human_confirmed=False,
                    provenance_hints={k: dict(v) for k, v in provenance.items()},
                    notes=notes,
                    agent_output_excerpt=agent_output,
                    envelope_mutated=envelope_mutated,
                    mutated_caps=dict(mutated_caps),
                )
            )

        return ShopperResult(
            proposals=proposals,
            wrapped_catalog=wrapped,
            detections=detections,
            redacted_envelope_view=self.redacted_envelope_view(
                merchants_allow=merchants_allow,
                per_txn_max_paise=per_txn_max_paise,
            ),
        )


# Re-export catalog merchant ids for tests / runner.
KNOWN_MERCHANTS = sorted(MERCHANTS.keys())

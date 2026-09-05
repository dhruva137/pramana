"""Arm A — fair AP2-shaped signed mandate, validated per transaction.

Industry-shaped baseline: merchant in merchants[], amount ≤ per-txn cap,
signature valid, not expired. **No episode ledger**, no provenance, no
address/item binding. Deliberately competent — not a strawman.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

# Catalog merchant ids (sandbox). Alias strings map utterance mentions → id.
_MERCHANT_ALIASES: dict[str, str] = {
    "swiggy sim": "swiggy_sim",
    "swiggy_sim": "swiggy_sim",
    "swiggy": "swiggy_sim",
    "zomato sim": "zomato_sim",
    "zomato_sim": "zomato_sim",
    "zomato": "zomato_sim",
    "zepto sim": "zepto_sim",
    "zepto_sim": "zepto_sim",
    "zepto": "zepto_sim",
    "blinkit": "zepto_sim",
    "instamart": "zepto_sim",
}

_AMOUNT_RE = re.compile(
    r"(?:"
    r"(?:₹|rs\.?|inr)\s*(\d{1,7}(?:\.\d{1,2})?)"
    r"|"
    r"(?:under|within|max|upto|up\s*to|below|ke\s+andar|tak)\s+(?:₹|rs\.?|inr)?\s*(\d{1,7})"
    r"|"
    r"(\d{1,7})\s*(?:ke\s+andar|tak|rupees?|rs\.?|ish)"
    r")",
    re.IGNORECASE,
)

_MANDATE_KID = "ap2-baseline-2026-09"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _b64_encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64_decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=False)


def _jcs(obj: Any) -> bytes:
    """Sorted-key canonical JSON (AP2-shaped mandate signing substrate)."""

    def _canon(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        if isinstance(v, float):
            raise TypeError("floats forbidden in mandate canonicalisation")
        if isinstance(v, str):
            return v
        if isinstance(v, Mapping):
            return {k: _canon(v[k]) for k in sorted(v.keys(), key=str)}
        if isinstance(v, (list, tuple)):
            return [_canon(x) for x in v]
        raise TypeError(f"unsupported type: {type(v)!r}")

    return json.dumps(_canon(obj), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_or_generate_sk() -> tuple[bytes, bytes]:
    """Return (sk_raw_32, pk_raw_32). Prefer PRAMANA_BASELINE_SK / PRAMANA_SEAL_SK."""
    for env_key in ("PRAMANA_BASELINE_SK", "PRAMANA_SEAL_SK"):
        raw_b64 = os.environ.get(env_key)
        if raw_b64:
            sk = _b64_decode(raw_b64)
            if len(sk) == 32:
                priv = Ed25519PrivateKey.from_private_bytes(sk)
                pk = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                return sk, pk
    # Deterministic demo key so offline tests are stable without env.
    seed = hashlib.sha256(b"pramana.baseline.mandate.v1").digest()
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    sk = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pk = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return sk, pk


def merchants_from_utterance(utterance: str) -> list[str]:
    lower = utterance.lower()
    out: list[str] = []
    for alias, mid in sorted(_MERCHANT_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in lower and mid not in out:
            out.append(mid)
    return out


def amounts_from_utterance_paise(utterance: str) -> list[int]:
    found: list[int] = []
    for m in _AMOUNT_RE.finditer(utterance):
        raw = next(g for g in m.groups() if g is not None)
        found.append(int(round(float(raw) * 100)))
    return found


@dataclass(frozen=True)
class MandateValidationResult:
    ok: bool
    reason: str
    checks: Mapping[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "checks": dict(self.checks)}


@dataclass
class SignedMandate:
    """AP2-shaped IntentMandate projection with Ed25519 signature.

    Field-shaped interoperability only — not a signed W3C Verifiable Credential.
    """

    mandate_id: str
    natural_language_description: str
    merchants: list[str]
    skus: list[str]
    per_transaction_max_paise: int
    currency: str
    intent_expiry: str
    user_cart_confirmation_required: bool
    requires_refundability: bool
    instrument: str
    consent_cap_paise: int
    created_at: str
    alg: str
    kid: str
    sig: str
    public_key_b64: str
    note: str = (
        "AP2-shaped IntentMandate projection for Arm A. "
        "Not a signed W3C Verifiable Credential."
    )

    def body_for_sign(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "natural_language_description": self.natural_language_description,
            "merchants": list(self.merchants),
            "skus": list(self.skus),
            "per_transaction_max_paise": int(self.per_transaction_max_paise),
            "currency": self.currency,
            "intent_expiry": self.intent_expiry,
            "user_cart_confirmation_required": self.user_cart_confirmation_required,
            "requires_refundability": self.requires_refundability,
            "instrument": self.instrument,
            "consent_cap_paise": int(self.consent_cap_paise),
            "created_at": self.created_at,
            "alg": self.alg,
            "kid": self.kid,
            "note": self.note,
        }

    def ap2_projection(self) -> dict[str, Any]:
        return {
            "IntentMandate": {
                "natural_language_description": self.natural_language_description,
                "merchants": list(self.merchants),
                "skus": list(self.skus),
                "requires_refundability": self.requires_refundability,
                "intent_expiry": self.intent_expiry,
                "user_cart_confirmation_required": self.user_cart_confirmation_required,
                "per_transaction_max_paise": self.per_transaction_max_paise,
            },
            "CartMandate": None,
            "PaymentMandate": None,
            "note": self.note,
        }

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ap2_projection"] = self.ap2_projection()
        return d


def issue_mandate(
    *,
    utterance: str,
    instrument: str,
    consent_cap_paise: int,
    merchants: Sequence[str] | None = None,
    per_transaction_max_paise: int | None = None,
    ttl_minutes: int = 30,
    now: datetime | None = None,
    skus: Sequence[str] | None = None,
) -> SignedMandate:
    """Emit a signed AP2-shaped mandate for Arm A.

    Per-txn cap defaults to min(stated utterance amount, consent_cap) when the
    user stated an amount — matching a competent agent that projects intent into
    the mandate — else the rail consent cap.
    """
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    merchants_list = list(merchants) if merchants is not None else merchants_from_utterance(utterance)
    stated = amounts_from_utterance_paise(utterance)
    if per_transaction_max_paise is not None:
        per_txn = int(per_transaction_max_paise)
    elif stated:
        per_txn = min(min(stated), int(consent_cap_paise))
    else:
        per_txn = int(consent_cap_paise)
    # Never exceed rail consent.
    per_txn = min(per_txn, int(consent_cap_paise))

    expiry = when + timedelta(minutes=ttl_minutes)
    sk, pk = _load_or_generate_sk()
    mandate = SignedMandate(
        mandate_id="man_" + secrets.token_hex(8),
        natural_language_description=utterance.strip(),
        merchants=merchants_list,
        skus=list(skus or []),
        per_transaction_max_paise=per_txn,
        currency="INR",
        intent_expiry=expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        user_cart_confirmation_required=True,
        requires_refundability=False,
        instrument=instrument,
        consent_cap_paise=int(consent_cap_paise),
        created_at=when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        alg="Ed25519",
        kid=_MANDATE_KID,
        sig="",
        public_key_b64=_b64_encode(pk),
    )
    msg = _jcs(mandate.body_for_sign())
    priv = Ed25519PrivateKey.from_private_bytes(sk)
    mandate.sig = _b64url_encode(priv.sign(msg))
    return mandate


def verify_mandate_signature(mandate: SignedMandate | Mapping[str, Any]) -> bool:
    if isinstance(mandate, SignedMandate):
        body = mandate.body_for_sign()
        sig = mandate.sig
        pk_b64 = mandate.public_key_b64
    else:
        body = {
            k: mandate[k]
            for k in (
                "mandate_id",
                "natural_language_description",
                "merchants",
                "skus",
                "per_transaction_max_paise",
                "currency",
                "intent_expiry",
                "user_cart_confirmation_required",
                "requires_refundability",
                "instrument",
                "consent_cap_paise",
                "created_at",
                "alg",
                "kid",
                "note",
            )
            if k in mandate
        }
        sig = str(mandate.get("sig", ""))
        pk_b64 = str(mandate.get("public_key_b64", ""))
    if not sig or not pk_b64:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64_decode(pk_b64))
        pub.verify(_b64url_decode(sig), _jcs(body))
        return True
    except Exception:
        return False


def validate_transaction(
    mandate: SignedMandate | Mapping[str, Any],
    *,
    merchant_id: str,
    amount_paise: int,
    currency: str = "INR",
    now: datetime | str | None = None,
) -> MandateValidationResult:
    """Per-transaction AP2-shaped checks. No episode ledger.

    Checks (all required):
      1. signature valid
      2. not expired
      3. merchant_id ∈ merchants[]
      4. 0 < amount_paise ≤ per_transaction_max_paise
      5. currency matches
    """
    when = _parse_dt(now or datetime.now(timezone.utc))
    if isinstance(mandate, SignedMandate):
        merchants = list(mandate.merchants)
        per_txn = int(mandate.per_transaction_max_paise)
        expiry_s = mandate.intent_expiry
        cur = mandate.currency
    else:
        merchants = list(mandate.get("merchants") or [])
        per_txn = int(mandate.get("per_transaction_max_paise", 0))
        expiry_s = str(mandate.get("intent_expiry", ""))
        cur = str(mandate.get("currency", "INR"))

    sig_ok = verify_mandate_signature(mandate)
    try:
        expiry = _parse_dt(expiry_s)
        not_expired = when <= expiry
    except Exception:
        not_expired = False
    merchant_ok = merchant_id in merchants
    amount_ok = 0 < int(amount_paise) <= per_txn
    currency_ok = str(currency).upper() == str(cur).upper()

    checks = {
        "signature_valid": sig_ok,
        "not_expired": not_expired,
        "merchant_in_list": merchant_ok,
        "amount_within_cap": amount_ok,
        "currency_ok": currency_ok,
    }
    if not sig_ok:
        return MandateValidationResult(False, "invalid_signature", checks)
    if not not_expired:
        return MandateValidationResult(False, "mandate_expired", checks)
    if not merchant_ok:
        return MandateValidationResult(
            False, f"merchant_not_in_mandate:{merchant_id}", checks
        )
    if not amount_ok:
        return MandateValidationResult(
            False,
            f"amount_exceeds_per_txn_cap:{amount_paise}>{per_txn}",
            checks,
        )
    if not currency_ok:
        return MandateValidationResult(False, f"currency_mismatch:{currency}", checks)
    return MandateValidationResult(True, "ok", checks)

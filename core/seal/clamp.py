"""Clamp numeric SIE constraints to the consent ceiling — §2.2 step 5."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.seal.schema import Constraints, ExtractionMeta, SealedIntentEnvelope, TimeWindow

# Money / threshold fields clamped to consent_cap_paise.
_CONSENT_CLAMP_FIELDS = (
    "per_txn_max_paise",
    "episode_total_max_paise",
    "confirm_above_paise",
)

MAX_TRANSACTIONS_HARD_CAP = 10
DEFAULT_TTL = timedelta(minutes=15)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clamp_constraints(
    constraints: Constraints | dict[str, Any],
    *,
    consent_cap_paise: int,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_TTL,
) -> tuple[Constraints, list[str]]:
    """Apply §2.2 clamp rules; return (clamped constraints, clamped_fields)."""
    now = _as_utc(now or datetime.now(timezone.utc))
    ceiling = now + ttl
    data = (
        constraints.model_dump(mode="python", by_alias=True)
        if isinstance(constraints, Constraints)
        else dict(constraints)
    )
    clamped: list[str] = []

    for field in _CONSENT_CLAMP_FIELDS:
        if field not in data or data[field] is None:
            continue
        value = int(data[field])
        if value > consent_cap_paise:
            data[field] = consent_cap_paise
            clamped.append(field)
        else:
            data[field] = value

    mt = int(data.get("max_transactions", 1))
    limited = min(mt, MAX_TRANSACTIONS_HARD_CAP)
    # Also never exceed consent in the generic numeric sense, then hard-cap at 10.
    limited = min(limited, consent_cap_paise) if consent_cap_paise >= 0 else limited
    limited = min(limited, MAX_TRANSACTIONS_HARD_CAP)
    if limited != mt:
        clamped.append("max_transactions")
    data["max_transactions"] = max(1, limited)

    tw = data.get("time_window")
    if tw is not None:
        if isinstance(tw, TimeWindow):
            tw_dict = tw.model_dump(mode="python", by_alias=True)
        elif isinstance(tw, dict):
            tw_dict = dict(tw)
        else:
            tw_dict = None
        if tw_dict is not None:
            to_raw = tw_dict.get("to")
            if to_raw is not None:
                to_dt = to_raw if isinstance(to_raw, datetime) else datetime.fromisoformat(
                    str(to_raw).replace("Z", "+00:00")
                )
                to_dt = _as_utc(to_dt)
                if to_dt > ceiling:
                    tw_dict["to"] = ceiling
                    clamped.append("time_window.to")
                else:
                    tw_dict["to"] = to_dt
            from_raw = tw_dict.get("from") or tw_dict.get("from_")
            if from_raw is not None and not isinstance(from_raw, datetime):
                tw_dict["from"] = datetime.fromisoformat(str(from_raw).replace("Z", "+00:00"))
            data["time_window"] = tw_dict

    return Constraints.model_validate(data), clamped


def clamp_expires_at(expires_at: datetime, *, now: datetime | None = None, ttl: timedelta = DEFAULT_TTL) -> tuple[datetime, bool]:
    """``expires_at := min(value, now+15m)``. Returns (clamped, was_clamped)."""
    now = _as_utc(now or datetime.now(timezone.utc))
    ceiling = now + ttl
    exp = _as_utc(expires_at)
    if exp > ceiling:
        return ceiling, True
    return exp, False


def clamp_envelope(
    envelope: SealedIntentEnvelope,
    *,
    now: datetime | None = None,
) -> SealedIntentEnvelope:
    """Clamp constraints + expires_at on a full envelope; update extraction.clamped_fields."""
    now = _as_utc(now or datetime.now(timezone.utc))
    consent = envelope.principal.consent_cap_paise
    constraints, clamped = clamp_constraints(
        envelope.constraints, consent_cap_paise=consent, now=now
    )
    expires, exp_clamped = clamp_expires_at(envelope.expires_at, now=now)
    if exp_clamped:
        clamped = [*clamped, "expires_at"]

    meta = envelope.extraction.model_copy(deep=True)
    seen = set(meta.clamped_fields)
    for f in clamped:
        if f not in seen:
            meta.clamped_fields.append(f)
            seen.add(f)

    return envelope.model_copy(
        update={
            "constraints": constraints,
            "expires_at": expires,
            "extraction": ExtractionMeta(
                degraded=meta.degraded,
                clamped_fields=list(meta.clamped_fields),
            ),
        }
    )

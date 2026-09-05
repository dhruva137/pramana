"""Seal procedure — docs/05-PROTOCOL-SPEC.md §2.2."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from ulid import ULID

from core.seal.clamp import DEFAULT_TTL, clamp_constraints, clamp_expires_at
from core.seal.extract import extract_constraints
from core.seal.fallback import restrictive_fallback
from core.seal.schema import (
    DEFAULT_PROVENANCE_POLICY,
    SIE_VERSION,
    AgentInfo,
    Constraints,
    ContextBinding,
    ExtractionDraft,
    ExtractionMeta,
    Principal,
    SealBlock,
    SealedIntentEnvelope,
    TimeWindow,
    Utterance,
)


def _crypto():
    """Canonicalise via the single RFC 8785 implementation (core.chain.jcs).

    ``core.chain.sign.sign`` takes ``(message, private_key_b64)``; this module signs
    with a raw 32-byte seed, so we deliberately use the seal-local ``sign(sk, msg)``
    adapter rather than swapping argument orders at the call site.
    Canonicalisation MUST be the shared JCS or R1 cannot verify what we sign.
    """
    from core.chain.jcs import canonicalize
    from core.seal._crypto import sha256_hex, sign

    return canonicalize, sha256_hex, sign


class ContextTaintedError(Exception):
    """409 CONTEXT_TAINTED — ledger not clean through seal index."""

    def __init__(self, detail: str = "context ledger tainted before seal"):
        self.code = "CONTEXT_TAINTED"
        self.detail = detail
        super().__init__(detail)


@dataclass
class SealRequest:
    utterance: str
    user_ref: str
    consent_ref: str
    consent_cap_paise: int
    agent_id: str = "agt_claude_demo"
    model: str = "mock-extractor"
    surface: str = "chat"
    episode_id: str | None = None
    delivery_address_hash: str = "sha256:demo_address"
    allowed_instruments: list[str] = field(
        default_factory=lambda: ["upi_reserve_pay:tok_x"]
    )
    ledger_head: str = "sha256:" + ("0" * 64)
    seal_index: int = 0
    # Context ledger entries 0..seal_index inclusive (or through utterance index).
    ctx_entries: Sequence[dict[str, Any]] | None = None
    now: datetime | None = None
    seal_sk_b64: str | None = None
    kid: str | None = None
    force_mock: bool | None = None
    # Inject bad extraction for tests (callable returning invalid draft / raises).
    _extract_override: Any = None


@dataclass
class SealResult:
    envelope: SealedIntentEnvelope
    degraded: bool


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def assert_context_clean(ctx_entries: Sequence[dict[str, Any]] | None, seal_index: int) -> None:
    """§2.2 step 2 — every entry 0..i must be taint==USER or role==system."""
    if not ctx_entries:
        return
    for entry in ctx_entries:
        idx = int(entry.get("idx", entry.get("index", -1)))
        if idx < 0 or idx > seal_index:
            continue
        taint = str(entry.get("taint", "")).upper()
        role = str(entry.get("role", "")).lower()
        if taint == "USER" or role == "system":
            continue
        raise ContextTaintedError(
            f"ledger[{idx}] taint={taint!r} role={role!r} — refuse to seal"
        )


def _load_sk(seal_sk_b64: str | None) -> bytes:
    from core.seal._crypto import generate_sk, load_sk_from_env_b64

    raw_b64 = seal_sk_b64 or os.environ.get("PRAMANA_SEAL_SK")
    if raw_b64:
        return load_sk_from_env_b64(raw_b64)
    # Demo / test: ephemeral key so sealing still works offline.
    return generate_sk()


def _draft_to_constraints(
    draft: ExtractionDraft,
    *,
    delivery_address_hash: str,
    allowed_instruments: list[str],
    now: datetime,
    ttl: timedelta,
) -> Constraints:
    window = TimeWindow.model_validate({"from": now, "to": now + ttl})
    return Constraints(
        merchants_allow=list(draft.merchants_allow),
        merchants_deny=list(draft.merchants_deny),
        categories_allow=list(draft.categories_allow),
        item_predicates=list(draft.item_predicates),
        per_txn_max_paise=draft.per_txn_max_paise,
        episode_total_max_paise=draft.episode_total_max_paise,
        max_transactions=draft.max_transactions,
        max_distinct_payees=draft.max_distinct_payees,
        currency=draft.currency,
        delivery_address_hash=delivery_address_hash,
        allowed_instruments=list(allowed_instruments),
        novel_payee_policy=draft.novel_payee_policy,
        confirm_above_paise=draft.confirm_above_paise,
        time_window=window,
    )


def _try_extract(req: SealRequest) -> tuple[ExtractionDraft, bool]:
    """Validate output; one retry; then restrictive fallback. Returns (draft, degraded)."""
    if req._extract_override is not None:
        attempts = []
        for _ in range(2):
            try:
                raw = req._extract_override()
                draft = ExtractionDraft.model_validate(raw)
                attempts.append(draft)
                return draft, False
            except Exception:
                attempts.append(None)
        fb = restrictive_fallback(
            req.utterance, consent_cap_paise=req.consent_cap_paise
        )
        return fb, True

    last_err: Exception | None = None
    for _ in range(2):
        try:
            draft = extract_constraints(
                req.utterance,
                consent_cap_paise=req.consent_cap_paise,
                force_mock=req.force_mock,
            )
            # Round-trip validate
            ExtractionDraft.model_validate(draft.model_dump())
            return draft, False
        except Exception as exc:  # noqa: BLE001 — fail closed to fallback
            last_err = exc
            continue

    _ = last_err
    fb = restrictive_fallback(req.utterance, consent_cap_paise=req.consent_cap_paise)
    return fb, True


def seal(req: SealRequest) -> SealResult:
    """Build envelope → clamp → sign (Ed25519 over canonicalize(envelope \\ seal))."""
    canonicalize, sha256_hex, sign = _crypto()
    now = _as_utc(req.now or datetime.now(timezone.utc))
    ttl = DEFAULT_TTL

    assert_context_clean(req.ctx_entries, req.seal_index)

    draft, degraded = _try_extract(req)
    constraints = _draft_to_constraints(
        draft,
        delivery_address_hash=req.delivery_address_hash,
        allowed_instruments=req.allowed_instruments,
        now=now,
        ttl=ttl,
    )
    constraints, clamped_fields = clamp_constraints(
        constraints, consent_cap_paise=req.consent_cap_paise, now=now, ttl=ttl
    )

    expires_at = now + ttl
    expires_at, exp_clamped = clamp_expires_at(expires_at, now=now, ttl=ttl)
    if exp_clamped:
        clamped_fields = [*clamped_fields, "expires_at"]

    # If constraints carried a longer window.to, clamp already recorded it.
    episode_id = req.episode_id or f"ep_{ULID()}"
    envelope_id = f"sie_{ULID()}"
    utt_hash = sha256_hex(req.utterance)

    env = SealedIntentEnvelope(
        sie_version=SIE_VERSION,
        envelope_id=envelope_id,
        episode_id=episode_id,
        created_at=now,
        expires_at=expires_at,
        principal=Principal(
            user_ref=req.user_ref,
            consent_ref=req.consent_ref,
            consent_cap_paise=req.consent_cap_paise,
        ),
        agent=AgentInfo(
            agent_id=req.agent_id,
            model=req.model if not degraded else "restrictive-fallback",
            surface=req.surface,
        ),
        utterance=Utterance(
            sha256=utt_hash if utt_hash.startswith("sha256:") else utt_hash,
            excerpt=req.utterance[:500],
            channel="USER",
        ),
        constraints=constraints,
        provenance_policy=DEFAULT_PROVENANCE_POLICY,
        context_binding=ContextBinding(
            ledger_head=req.ledger_head,
            seal_index=req.seal_index,
        ),
        extraction=ExtractionMeta(degraded=degraded, clamped_fields=list(clamped_fields)),
        seal=None,
    )

    payload = env.without_seal()
    message = canonicalize(payload)
    if isinstance(message, str):
        message = message.encode("utf-8")
    sk = _load_sk(req.seal_sk_b64)
    kid = req.kid or os.environ.get("PRAMANA_SEAL_KID", "seal-2026-09")
    sig = sign(sk, message)
    env = env.model_copy(
        update={"seal": SealBlock(alg="Ed25519", kid=kid, sig=sig)}
    )
    # Final schema validation
    SealedIntentEnvelope.model_validate(env.model_dump(mode="python", by_alias=True))
    return SealResult(envelope=env, degraded=degraded)

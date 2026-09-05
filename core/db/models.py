"""SQLAlchemy 2 models. Money is always BIGINT paise — never float."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

# Dual-dialect JSON: JSONB on Postgres, JSON elsewhere (sqlite).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # ep_<ulid>
    user_ref: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # OPEN|FROZEN|QUARANTINED|CLOSED|EXPIRED
    envelope: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    envelope_sig: Mapped[str] = mapped_column(Text, nullable=False)
    envelope_kid: Mapped[str] = mapped_column(Text, nullable=False)
    ctx_ledger_head: Mapped[str] = mapped_column(Text, nullable=False)
    seal_index: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)  # PRAMANA_ON | BASELINE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    context_entries: Mapped[list[ContextLedgerEntry]] = relationship(back_populates="episode")
    ledger_entries: Mapped[list[LedgerEntry]] = relationship(back_populates="episode")
    decisions: Mapped[list[Decision]] = relationship(back_populates="episode")


class ContextLedgerEntry(Base):
    __tablename__ = "context_ledger"

    episode_id: Mapped[str] = mapped_column(
        Text, ForeignKey("episodes.id"), primary_key=True
    )
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    taint: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha: Mapped[str] = mapped_column(Text, nullable=False)
    content_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Advisory annotations. Persisted so R11 can still see detector flags after a
    # reload — without them the injection-escalation rule silently never fires.
    # Deliberately EXCLUDED from the R2 hash body (see api/ctx_ledger.py): the
    # chain commits to content, not to our opinion about it.
    tool: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    episode: Mapped[Episode] = relationship(back_populates="context_entries")


class LedgerEntry(Base):
    """Episode budget ledger. amount_paise is BIGINT — never float/rupees."""

    __tablename__ = "ledger_entries"

    # BIGSERIAL on Postgres; INTEGER PK on SQLite so AUTOINCREMENT works.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    episode_id: Mapped[str] = mapped_column(Text, ForeignKey("episodes.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # HOLD|CAPTURE|RELEASE|REFUND
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payee_id: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="ledger_entries")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # dec_<ulid>
    episode_id: Mapped[str] = mapped_column(Text, ForeignKey("episodes.id"), nullable=False)
    action: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)  # ADMIT|ESCALATE|DENY
    rule_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_trace: Mapped[list[Any]] = mapped_column(JsonType, nullable=False)
    ledger_before: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="decisions")
    execution: Mapped[Execution | None] = relationship(back_populates="decision", uselist=False)


class Execution(Base):
    __tablename__ = "executions"

    decision_id: Mapped[str] = mapped_column(
        Text, ForeignKey("decisions.id"), primary_key=True
    )
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    rzp_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rzp_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)  # PENDING|SUCCEEDED|FAILED|AMBIGUOUS
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    decision: Mapped[Decision] = relationship(back_populates="execution")


class Proof(Base):
    __tablename__ = "proofs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # dvp_<ulid>
    episode_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[str] = mapped_column(Text, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    kid: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BenchRun(Base):
    __tablename__ = "bench_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    corpus_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    arm: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)

    episodes: Mapped[list[BenchEpisode]] = relationship(back_populates="run")


class BenchEpisode(Base):
    __tablename__ = "bench_episodes"

    run_id: Mapped[str] = mapped_column(Text, ForeignKey("bench_runs.id"), primary_key=True)
    case_id: Mapped[str] = mapped_column(Text, primary_key=True)
    family: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    attack_succeeded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    task_completed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    escalations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)

    run: Mapped[BenchRun] = relationship(back_populates="episodes")


class MerchantRef(Base):
    """Demo / RZP_VERIFIED merchant registry (seed). Not in §3 payment path tables."""

    __tablename__ = "merchant_refs"
    __table_args__ = (UniqueConstraint("merchant_id", name="uq_merchant_refs_merchant_id"),)

    merchant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    account_ref: Mapped[str] = mapped_column(Text, nullable=False)
    taint: Mapped[str] = mapped_column(Text, nullable=False, default="RZP_VERIFIED")


class DemoUser(Base):
    """Demo user + mock UPI Reserve Pay consent ceiling."""

    __tablename__ = "demo_users"

    user_ref: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    consent_ref: Mapped[str] = mapped_column(Text, nullable=False)
    consent_cap_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    instrument: Mapped[str] = mapped_column(Text, nullable=False)

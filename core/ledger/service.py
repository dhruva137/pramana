"""Episode budget ledger service — HOLD before execute under row lock."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Episode, LedgerEntry
from core.ledger.state import LedgerState, compute_ledger_state


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def begin_episode_lock(session: AsyncSession, episode_id: str) -> Episode:
    """Serialise ledger RMW: BEGIN IMMEDIATE on sqlite; SELECT … FOR UPDATE on postgres."""
    bind = session.get_bind()
    dialect = bind.dialect.name if bind is not None else "sqlite"

    if dialect == "sqlite":
        # Autobegin from prior reads is DEFERRED; end it and take an IMMEDIATE write lock
        # so concurrent execute paths cannot race past R6/exposure.
        if session.in_transaction():
            await session.commit()
        await session.execute(text("BEGIN IMMEDIATE"))

    result = await session.execute(
        select(Episode).where(Episode.id == episode_id).with_for_update()
    )
    episode = result.scalar_one_or_none()
    if episode is None:
        raise LookupError(f"episode not found: {episode_id}")
    return episode


async def load_entries(session: AsyncSession, episode_id: str) -> list[LedgerEntry]:
    result = await session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.episode_id == episode_id)
        .order_by(LedgerEntry.id.asc())
    )
    return list(result.scalars().all())


async def get_ledger_state(session: AsyncSession, episode_id: str) -> LedgerState:
    entries = await load_entries(session, episode_id)
    return compute_ledger_state(entries)


async def append_entry(
    session: AsyncSession,
    *,
    episode_id: str,
    kind: str,
    amount_paise: int,
    payee_id: str,
    decision_id: str | None = None,
    category: str | None = None,
    created_at: datetime | None = None,
) -> LedgerEntry:
    if not isinstance(amount_paise, int) or isinstance(amount_paise, bool):
        raise TypeError("amount_paise must be int (paise)")
    if amount_paise < 0:
        raise ValueError("amount_paise must be >= 0")
    if kind not in ("HOLD", "CAPTURE", "RELEASE", "REFUND"):
        raise ValueError(f"invalid kind: {kind}")

    entry = LedgerEntry(
        episode_id=episode_id,
        kind=kind,
        amount_paise=amount_paise,
        payee_id=payee_id,
        category=category,
        decision_id=decision_id,
        created_at=created_at or _utcnow(),
    )
    session.add(entry)
    await session.flush()
    return entry


async def hold(
    session: AsyncSession,
    *,
    episode_id: str,
    amount_paise: int,
    payee_id: str,
    decision_id: str,
    category: str | None = None,
    lock: bool = True,
) -> tuple[LedgerEntry, LedgerState]:
    """Reserve amount against the episode cap BEFORE the Razorpay call."""
    if lock:
        await begin_episode_lock(session, episode_id)
    entry = await append_entry(
        session,
        episode_id=episode_id,
        kind="HOLD",
        amount_paise=amount_paise,
        payee_id=payee_id,
        decision_id=decision_id,
        category=category,
    )
    state = await get_ledger_state(session, episode_id)
    return entry, state


async def capture(
    session: AsyncSession,
    *,
    episode_id: str,
    amount_paise: int,
    payee_id: str,
    decision_id: str,
    category: str | None = None,
    lock: bool = True,
) -> tuple[LedgerEntry, LedgerState]:
    """Convert an open HOLD into committed spend (HOLD → CAPTURE)."""
    if lock:
        await begin_episode_lock(session, episode_id)
    entry = await append_entry(
        session,
        episode_id=episode_id,
        kind="CAPTURE",
        amount_paise=amount_paise,
        payee_id=payee_id,
        decision_id=decision_id,
        category=category,
    )
    state = await get_ledger_state(session, episode_id)
    return entry, state


async def release(
    session: AsyncSession,
    *,
    episode_id: str,
    amount_paise: int,
    payee_id: str,
    decision_id: str,
    category: str | None = None,
    lock: bool = True,
) -> tuple[LedgerEntry, LedgerState]:
    """Free a HOLD on definite failure."""
    if lock:
        await begin_episode_lock(session, episode_id)
    entry = await append_entry(
        session,
        episode_id=episode_id,
        kind="RELEASE",
        amount_paise=amount_paise,
        payee_id=payee_id,
        decision_id=decision_id,
        category=category,
    )
    state = await get_ledger_state(session, episode_id)
    return entry, state


async def refund(
    session: AsyncSession,
    *,
    episode_id: str,
    amount_paise: int,
    payee_id: str,
    decision_id: str | None = None,
    category: str | None = None,
    lock: bool = True,
) -> tuple[LedgerEntry, LedgerState]:
    if lock:
        await begin_episode_lock(session, episode_id)
    entry = await append_entry(
        session,
        episode_id=episode_id,
        kind="REFUND",
        amount_paise=amount_paise,
        payee_id=payee_id,
        decision_id=decision_id,
        category=category,
    )
    state = await get_ledger_state(session, episode_id)
    return entry, state


__all__ = [
    "begin_episode_lock",
    "load_entries",
    "get_ledger_state",
    "append_entry",
    "hold",
    "capture",
    "release",
    "refund",
]

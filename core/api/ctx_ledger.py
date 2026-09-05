"""Context-ledger append helpers using gate chain semantics (R2)."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import ContextLedgerEntry, Episode
from core.gate.rules import entry_hash, genesis_hash


def content_sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def entry_hash_body(row: ContextLedgerEntry) -> dict[str, Any]:
    """ONLY the fields that participate in the gate R2 hash chain."""
    return {
        "idx": row.idx,
        "role": row.role,
        "taint": row.taint,
        "content_sha": row.content_sha,
        "content_excerpt": row.content_excerpt,
        "source_uri": row.source_uri,
        "prev_hash": row.prev_hash,
        "hash": row.hash,
    }


def entry_to_dict(row: ContextLedgerEntry) -> dict[str, Any]:
    """Hash-chain fields plus advisory annotations the gate reads.

    ``detector`` MUST be included: R11 escalates on detector flags found in the
    provenance closure, and dropping it on reload turns R11 into a rule that can
    never fire. It is excluded from the hash body (see ``entry_hash_body``) —
    ``core.gate.rules.entry_hash`` recomputes over the persisted chain fields
    only, so carrying it here does not break R2.
    """
    d = entry_hash_body(row)
    if row.tool:
        d["tool"] = row.tool
    if row.detector:
        d["detector"] = row.detector
    return d


def entry_to_proof_dict(row: ContextLedgerEntry) -> dict[str, Any]:
    """Proof builder looks up ``index``; keep hash-chain fields intact."""
    d = entry_to_dict(row)
    d["index"] = row.idx
    return d


async def load_ctx_ledger(
    session: AsyncSession, episode_id: str, *, for_proof: bool = False
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(ContextLedgerEntry)
        .where(ContextLedgerEntry.episode_id == episode_id)
        .order_by(ContextLedgerEntry.idx.asc())
    )
    rows = list(result.scalars().all())
    if for_proof:
        return [entry_to_proof_dict(r) for r in rows]
    return [entry_to_dict(r) for r in rows]


async def append_context_entry(
    session: AsyncSession,
    *,
    episode_id: str,
    role: str,
    taint: str,
    content: str,
    source_uri: str | None = None,
    tool: str | None = None,
    detector: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one context-ledger row with gate-compatible prev_hash/hash.

    Only persisted columns are included in the hash body so R2 recomputation
    matches after reload (tool/detector are response-only annotations).
    """
    existing = await load_ctx_ledger(session, episode_id)
    idx = len(existing)
    prev = existing[-1]["hash"] if existing else genesis_hash(episode_id)
    excerpt = content[:500] if content else None
    body: dict[str, Any] = {
        "idx": idx,
        "role": role,
        "taint": taint.upper(),
        "content_sha": content_sha(content),
        "content_excerpt": excerpt,
        "source_uri": source_uri,
        "prev_hash": prev,
    }
    h = entry_hash(prev, body)
    body["hash"] = h
    if tool:
        body["tool"] = tool
    if detector:
        body["detector"] = detector

    row = ContextLedgerEntry(
        episode_id=episode_id,
        idx=idx,
        role=role,
        taint=body["taint"],
        content_sha=body["content_sha"],
        content_excerpt=excerpt,
        source_uri=source_uri,
        prev_hash=prev,
        hash=h,
        tool=tool,
        detector=detector,
    )
    session.add(row)

    episode = await session.get(Episode, episode_id)
    if episode is not None:
        episode.ctx_ledger_head = h

    await session.flush()
    return body

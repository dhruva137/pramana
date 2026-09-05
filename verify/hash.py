"""SHA-256 helpers and hash-chain recomputation (independent verify/ copy).

The context-ledger chain scheme is defined by the gate, because rule R2 is what
enforces it at runtime (docs/05-PROTOCOL-SPEC.md §4). This module reimplements
that exact scheme rather than a similar one — an earlier version used a different
genesis and a different per-entry body, so the verifier rejected every genuine
proof on ``context_ledger_head``. Independence (invariant I6) means *no shared
code*, not *a different algorithm*.

Scheme, mirroring ``core.gate.rules``:

    h_0 = "sha256:" + SHA256(b"pramana.ctx.v1|" + episode_id)
    h_n = "sha256:" + SHA256(h_{n-1}.utf8 + JCS(entry \\ non-chain keys))

Note h_{n-1} is hashed *including* its ``sha256:`` prefix.
"""

from __future__ import annotations

import hashlib
from typing import Any

from verify.jcs import canonicalize

#: Genesis prefixes. Byte-for-byte identical to core.gate.rules / core.proof.
CTX_GENESIS = b"pramana.ctx.v1|"
DEC_GENESIS = b"pramana.dec.v1|"

#: Advisory annotations carried alongside an entry but excluded from the chain
#: body: detector verdicts can be re-run without invalidating the ledger.
#: Mirrors ``core.gate.rules._NON_CHAIN_ENTRY_KEYS``.
NON_CHAIN_ENTRY_KEYS = frozenset({"hash", "tool", "detector", "index"})


def sha256_digest_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex(data: bytes | str) -> str:
    """Return ``sha256:<hex>`` digest URI."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + sha256_digest_hex(data)


def excerpt_sha(excerpt: str) -> str:
    return sha256_hex(excerpt.encode("utf-8"))


def genesis_hash(genesis: bytes, episode_id: str) -> str:
    return sha256_hex(genesis + episode_id.encode("utf-8"))


def entry_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    """H(prev_hash || JCS(entry without hash / advisory annotations))."""
    body = {k: v for k, v in entry.items() if k not in NON_CHAIN_ENTRY_KEYS}
    return sha256_hex(prev_hash.encode("utf-8") + canonicalize(body))


def chain_head(genesis: bytes, episode_id: str, entries: list[dict[str, Any]]) -> str:
    prev = genesis_hash(genesis, episode_id)
    for entry in entries:
        prev = entry_hash(prev, entry)
    return prev


def context_ledger_head(episode_id: str, entries: list[dict[str, Any]]) -> str:
    return chain_head(CTX_GENESIS, episode_id, entries)


def decision_chain_head(episode_id: str, entries: list[dict[str, Any]]) -> str:
    return chain_head(DEC_GENESIS, episode_id, entries)


def _entry_index(entry: dict[str, Any]) -> int:
    for key in ("idx", "index", "ledger_idx"):
        if entry.get(key) is not None:
            return int(entry[key])
    return -1


def head_at_index(
    genesis: bytes, episode_id: str, entries: list[dict[str, Any]], index: int
) -> str:
    """Chain head over entries with ledger index ``<= index`` (inclusive)."""
    prefix = [e for e in entries if _entry_index(e) <= index]
    prefix.sort(key=_entry_index)
    return chain_head(genesis, episode_id, prefix)

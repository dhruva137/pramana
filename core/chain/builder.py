"""Hash-chain builder: h0 = H(genesis || episode_id), hn = H(h_{n-1} || JCS(entry))."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.chain.hash import sha256_hex
from core.chain.jcs import canonicalize

# Domain-separated genesis label for context / decision chains.
GENESIS = b"pramana/v1/genesis"

JsonObject = Mapping[str, Any]


def genesis_hash(episode_id: str, *, genesis: bytes = GENESIS) -> str:
    """Compute h0 = SHA-256(genesis || episode_id) as lowercase hex."""
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("episode_id must be a non-empty string")
    return sha256_hex(genesis + episode_id.encode("utf-8"))


def chain_hash(prev_hash: str, entry: JsonObject | Sequence[Any] | Any) -> str:
    """Compute hn = SHA-256(utf8(h_{n-1}) || JCS(entry)) as lowercase hex."""
    if not isinstance(prev_hash, str) or len(prev_hash) != 64:
        raise ValueError("prev_hash must be a 64-char hex SHA-256 digest")
    return sha256_hex(prev_hash.encode("utf-8") + canonicalize(entry))


def build_chain(
    episode_id: str,
    entries: Sequence[JsonObject | Any],
    *,
    genesis: bytes = GENESIS,
) -> list[str]:
    """Return ``[h0, h1, ..., hn]`` for ``entries`` (length ``n + 1``)."""
    hashes = [genesis_hash(episode_id, genesis=genesis)]
    for entry in entries:
        hashes.append(chain_hash(hashes[-1], entry))
    return hashes


def recompute_head(
    episode_id: str,
    entries: Sequence[JsonObject | Any],
    *,
    genesis: bytes = GENESIS,
) -> str:
    """Return the chain head after folding all ``entries``."""
    return build_chain(episode_id, entries, genesis=genesis)[-1]


def verify_chain(
    episode_id: str,
    entries: Sequence[JsonObject | Any],
    expected_head: str,
    *,
    genesis: bytes = GENESIS,
) -> bool:
    """Return True if recomputing the chain yields ``expected_head``."""
    return recompute_head(episode_id, entries, genesis=genesis) == expected_head
"""JCS / hash / Ed25519 helpers for the proof builder.

Canonicalisation delegates to ``core.chain.jcs`` — the single RFC 8785
implementation used by the sealer and the gate. ``verify/`` keeps its own
independent copy on purpose (invariant I6); a differential test asserts the two
agree byte-for-byte, which is what makes the offline verifier meaningful rather
than merely duplicated.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core.chain.jcs import canonicalize as _jcs_canonicalize

#: Chain scheme is defined by the gate (R2 enforces it at runtime). These must
#: match ``core.gate.rules`` byte-for-byte, and ``verify/hash.py`` reimplements
#: the same scheme independently.
CTX_GENESIS = b"pramana.ctx.v1|"
DEC_GENESIS = b"pramana.dec.v1|"

#: Advisory annotations excluded from the chain body (mirrors the gate).
NON_CHAIN_ENTRY_KEYS = frozenset({"hash", "tool", "detector", "index"})


def canonicalize(value: Any) -> bytes:
    """RFC 8785 JCS bytes."""
    return _jcs_canonicalize(value)


def sha256_digest_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex(data: bytes | str) -> str:
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


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_document(document: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    return b64url_encode(private_key.sign(canonicalize(document)))


def public_bytes(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes_raw()

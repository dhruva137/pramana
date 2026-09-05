"""Seal-local crypto helpers.

Canonicalisation is delegated to ``core.chain.jcs`` — the single RFC 8785
implementation on the runtime side. There is deliberately no sorted-JSON
fallback: a second dialect is what silently breaks R1 seal verification.

Signing lives here because this module works with a raw 32-byte Ed25519 seed,
whereas ``core.chain.sign.sign`` takes ``(message, private_key_b64)``.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.chain.jcs import canonicalize as _jcs_canonicalize


def canonicalize(obj: Any) -> bytes:
    """RFC 8785 JCS bytes — same dialect the gate verifies against."""
    return _jcs_canonicalize(obj)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def sign(sk_raw_32: bytes, message: bytes) -> str:
    """Ed25519 sign; return unpadded base64url signature."""
    if len(sk_raw_32) != 32:
        raise ValueError(f"Ed25519 seed must be 32 bytes, got {len(sk_raw_32)}")
    key = Ed25519PrivateKey.from_private_bytes(sk_raw_32)
    return _b64url_encode(key.sign(message))


def load_sk_from_env_b64(b64: str) -> bytes:
    raw = base64.b64decode(b64)
    if len(raw) != 32:
        raise ValueError(f"PRAMANA_SEAL_SK must decode to 32 bytes, got {len(raw)}")
    return raw


def generate_sk() -> bytes:
    key = Ed25519PrivateKey.generate()
    if hasattr(key, "private_bytes_raw"):
        return key.private_bytes_raw()
    from cryptography.hazmat.primitives import serialization

    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )

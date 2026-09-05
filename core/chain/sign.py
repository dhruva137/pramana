"""Ed25519 sign/verify with raw 32-byte keys encoded as standard base64."""

from __future__ import annotations

import base64

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


def _b64_encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64_decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=False)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def generate_keypair() -> tuple[str, str]:
    """Return ``(private_key_b64, public_key_b64)`` as raw 32-byte base64."""
    private = Ed25519PrivateKey.generate()
    sk = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pk = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64_encode(sk), _b64_encode(pk)


def public_key_from_private(private_key_b64: str) -> str:
    """Derive the raw-32-byte public key (base64) from a private key."""
    private = Ed25519PrivateKey.from_private_bytes(_b64_decode(private_key_b64))
    pk = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64_encode(pk)


def sign(message: bytes | str, private_key_b64: str) -> str:
    """Sign ``message`` and return a base64url (unpadded) Ed25519 signature.

    Callers MUST pass JCS bytes when signing envelopes/proofs —
    never json.dumps output.
    """
    if isinstance(message, str):
        message = message.encode("utf-8")
    private = Ed25519PrivateKey.from_private_bytes(_b64_decode(private_key_b64))
    return _b64url_encode(private.sign(message))


def verify(message: bytes | str, signature_b64url: str, public_key_b64: str) -> bool:
    """Return True iff ``signature_b64url`` is valid for ``message``."""
    if isinstance(message, str):
        message = message.encode("utf-8")
    try:
        public = Ed25519PublicKey.from_public_bytes(_b64_decode(public_key_b64))
        public.verify(_b64url_decode(signature_b64url), message)
        return True
    except Exception:
        return False
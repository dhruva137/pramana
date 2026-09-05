"""Ed25519 sign/verify and JWKS helpers (independent verify/ copy)."""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from verify.jcs import canonicalize


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def sign_jcs(document: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    """Sign JCS(document) and return base64url signature."""
    msg = canonicalize(document)
    return b64url_encode(private_key.sign(msg))


def verify_jcs(document: dict[str, Any], sig_b64url: str, public_key: Ed25519PublicKey) -> bool:
    try:
        public_key.verify(b64url_decode(sig_b64url), canonicalize(document))
        return True
    except Exception:
        return False


def public_key_from_raw(raw32: bytes) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(raw32)


def private_key_from_raw(raw32: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(raw32)


def public_key_from_jwk(jwk: dict[str, Any]) -> Ed25519PublicKey:
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise ValueError(f"unsupported JWK: {jwk.get('kty')}/{jwk.get('crv')}")
    x = jwk.get("x")
    if not x:
        raise ValueError("JWK missing x")
    return public_key_from_raw(b64url_decode(x))


def load_jwks(path_or_dict: str | dict[str, Any]) -> dict[str, Ed25519PublicKey]:
    """Load kid -> public key map from a JWKS file path or dict."""
    if isinstance(path_or_dict, str):
        with open(path_or_dict, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = path_or_dict
    keys: dict[str, Ed25519PublicKey] = {}
    for jwk in data.get("keys", []):
        kid = jwk.get("kid")
        if not kid:
            continue
        keys[kid] = public_key_from_jwk(jwk)
    return keys


def jwk_from_public(public_key: Ed25519PublicKey, kid: str) -> dict[str, str]:
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": b64url_encode(public_key.public_bytes_raw()),
        "kid": kid,
        "alg": "EdDSA",
        "use": "sig",
    }


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    sk = Ed25519PrivateKey.generate()
    return sk, sk.public_key()

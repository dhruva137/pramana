"""SHA-256 helpers for Pramana hash chains."""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes | str) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``.

    Strings are encoded as UTF-8 before hashing. Money paths MUST NOT pass
    floats into this function — callers hash JCS bytes or explicit UTF-8 text.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
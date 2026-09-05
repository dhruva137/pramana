"""sha256_hex unit tests."""

from __future__ import annotations

import hashlib

from core.chain.hash import sha256_hex


def test_sha256_hex_bytes_and_str_agree_on_utf8() -> None:
    text = "pramana"
    assert sha256_hex(text) == sha256_hex(text.encode("utf-8"))
    assert sha256_hex(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_sha256_hex_known_empty() -> None:
    assert sha256_hex(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )

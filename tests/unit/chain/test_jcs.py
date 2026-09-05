"""RFC 8785 JCS acceptance tests against committed fixtures."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from core.chain.jcs import CanonicalizationError, canonicalize, canonicalize_str

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_vectors() -> list[dict]:
    return json.loads((FIXTURES / "vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", _load_vectors(), ids=lambda v: v["name"])
def test_jcs_matches_rfc_vectors(vector: dict) -> None:
    expected_path = FIXTURES / f"{vector['name']}.expected.jcs"
    expected = expected_path.read_bytes()
    # Prefer parsing the committed input file so float literals match the corpus.
    input_path = FIXTURES / f"{vector['name']}.input.json"
    obj = json.loads(input_path.read_text(encoding="utf-8"))
    assert canonicalize(obj) == expected
    assert canonicalize_str(obj) == expected.decode("utf-8")


def test_jcs_appendix_b_number_samples() -> None:
    samples = json.loads((FIXTURES / "appendix_b_numbers.json").read_text(encoding="utf-8"))
    for sample in samples:
        value = struct.unpack(">d", bytes.fromhex(sample["ieee754_hex"]))[0]
        assert canonicalize(value).decode("ascii") == sample["json"]


def test_jcs_rejects_nan_and_infinity() -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize(float("nan"))
    with pytest.raises(CanonicalizationError):
        canonicalize(float("inf"))


def test_jcs_idempotent_on_canonical_bytes() -> None:
    obj = {"b": {"d": 1, "c": 2}, "a": [3, 1, 2], "z": None}
    once = canonicalize(obj)
    again = canonicalize(json.loads(once))
    assert once == again

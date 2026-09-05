"""verify/ keeps its own JCS on purpose (I6) — this proves the two agree.

Invariant I6 says the offline verifier must not import from ``core``. That
independence is only meaningful if the two implementations produce identical
bytes; if they drift, the verifier rejects valid proofs and someone "fixes" it
by weakening a check. Runtime-side canonicalisation is unified on
``core.chain.jcs`` (the sealer, the gate and the proof builder all delegate to
it), so this is the one boundary where a differential test is required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.chain.jcs import canonicalize as core_canonicalize
from verify.jcs import canonicalize as verify_canonicalize

REPO = Path(__file__).resolve().parents[3]

DOCUMENTS: list[object] = [
    {},
    [],
    {"a": 1, "b": [1, 2, 3]},
    {"b": 1, "a": 2},
    {"z": None, "a": True, "m": False},
    {"amount_paise": 54000, "currency": "INR"},
    {"nested": {"deep": {"deeper": [{"k": "v"}, {"k2": 0}]}}},
    {"unicode": "biryani ₹600 — Hinglish: do biryani mangwa do"},
    {"escapes": 'quote " backslash \\ newline \n tab \t'},
    {"control": ""},
    {"emoji": "🍛"},
    # UTF-16 code-unit ordering is where naive sort(str) implementations diverge.
    {"é": 1, "e": 2, "ｚ": 3, "z": 4},
    {"a\U0001f600b": 1, "ab": 2},
    {"": "empty key"},
    {"big_int": 2**53 - 1, "neg": -(2**53) + 1},
    [{"idx": 0, "taint": "USER"}, {"idx": 1, "taint": "MERCHANT_FREETEXT"}],
]


@pytest.mark.parametrize("doc", DOCUMENTS, ids=range(len(DOCUMENTS)))
def test_core_and_verify_jcs_agree(doc: object) -> None:
    assert core_canonicalize(doc) == verify_canonicalize(doc)


def test_agreement_on_a_real_golden_fixture() -> None:
    """Exercise the shapes that actually flow through the gate."""
    golden = REPO / "tests" / "unit" / "gate" / "golden"
    files = sorted(golden.glob("*.json"))
    assert files, "no golden fixtures found"
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert core_canonicalize(doc) == verify_canonicalize(doc), path.name


def test_runtime_side_has_a_single_dialect() -> None:
    """seal / proof / gate must all delegate to core.chain.jcs, not re-implement it."""
    from core.gate.rules import jcs as gate_jcs
    from core.proof.canon import canonicalize as proof_canonicalize
    from core.seal._crypto import canonicalize as seal_canonicalize

    doc = {"b": 1, "a": {"nested": [1, "two", None, True]}, "é": "accent"}
    reference = core_canonicalize(doc)
    assert seal_canonicalize(doc) == reference
    assert proof_canonicalize(doc) == reference
    assert gate_jcs(doc) == reference


def test_gate_jcs_still_rejects_floats() -> None:
    """I4: unifying canonicalisation must not lose the money-path float guard."""
    from core.gate.rules import jcs as gate_jcs

    with pytest.raises(TypeError):
        gate_jcs({"amount_paise": 540.0})
    with pytest.raises(TypeError):
        gate_jcs({"items": [{"price_paise": 1.5}]})

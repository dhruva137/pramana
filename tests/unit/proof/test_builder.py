"""Unit tests for Divergence Proof builder, causal chain, and PDF."""

from __future__ import annotations

from core.proof.causal import assemble_causal_chain
from core.proof.pdf import render_proof_pdf
from tests.unit.proof.conftest import make_fragmentation_proof
from verify.hash import excerpt_sha
from verify.verifier import verify_proof


def test_assemble_causal_chain_merges_and_hashes():
    excerpt = "split into small orders"
    provenance = [
        {
            "field": "amount_paise",
            "taint": "MERCHANT_FREETEXT",
            "ledger_idx": 2,
            "source_uri": "catalog://x",
            "span": [0, 5],
            "excerpt": excerpt,
            "excerpt_sha": excerpt_sha(excerpt),
        },
        {
            "field": "payee.merchant_id",
            "taint": "RZP_VERIFIED",
            "ledger_idx": 2,
            "source_uri": "catalog://x",
            "span": [0, 5],
            "excerpt": excerpt,
            "excerpt_sha": excerpt_sha(excerpt),
        },
    ]
    ctx = [
        {
            "index": 2,
            "tool": "catalog.search",
            "taint": "MERCHANT_FREETEXT",
            "content_excerpt": excerpt,
            "detector": {"flagged": True, "signature": "instruction_in_content"},
        }
    ]
    chain = assemble_causal_chain(provenance, ctx)
    assert len(chain) == 1
    assert set(chain[0]["determined_fields"]) == {"amount_paise", "payee.merchant_id"}
    assert chain[0]["excerpt_sha"] == excerpt_sha(excerpt)
    assert chain[0]["detector"]["flagged"] is True


def test_build_dvp_accepts_under_verifier():
    doc, jwks = make_fragmentation_proof()
    verify_proof(doc, jwks)
    assert doc["verdict"] == "DENY"
    assert doc["dvp_version"] == "1.0"
    assert doc["signature"]["kid"] == "proof-2026-09"
    assert doc["causal_chain"]
    assert "gate_replay" in doc


def test_pdf_contains_pdf_header_and_highlight_bytes():
    doc, _ = make_fragmentation_proof()
    pdf = render_proof_pdf(doc)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
    # Highlight color is drawn as a filled rect; stream should reference content ops
    assert b"stream" in pdf

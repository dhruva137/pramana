"""Offline verifier acceptance / rejection and import-isolation tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.unit.proof.conftest import make_fragmentation_proof, make_keys, resign
from verify.cli import main as cli_main
from verify.sign import generate_keypair
from verify.verifier import VerifyError, verify_proof

VERIFY_ROOT = Path(__file__).resolve().parents[3] / "verify"


def test_accept_valid_proof():
    doc, jwks = make_fragmentation_proof()
    verify_proof(doc, jwks)


def test_reject_mutated_verdict():
    seal_sk, proof_sk, jwks = make_keys()
    doc, jwks = make_fragmentation_proof(seal_sk=seal_sk, proof_sk=proof_sk, jwks=jwks)
    doc["verdict"] = "ADMIT"
    doc = resign(doc, proof_sk)
    with pytest.raises(VerifyError, match="rules_replay"):
        verify_proof(doc, jwks)


def test_reject_mutated_envelope():
    seal_sk, proof_sk, jwks = make_keys()
    doc, jwks = make_fragmentation_proof(seal_sk=seal_sk, proof_sk=proof_sk, jwks=jwks)
    env = doc["sealed_intent"]["envelope"]
    env["constraints"]["episode_total_max_paise"] = 999999
    # Keep old seal → envelope_seal must fail
    doc = resign(doc, proof_sk)
    with pytest.raises(VerifyError, match="envelope_seal"):
        verify_proof(doc, jwks)


def test_reject_wrong_kid():
    seal_sk, proof_sk, jwks = make_keys()
    doc, jwks = make_fragmentation_proof(seal_sk=seal_sk, proof_sk=proof_sk, jwks=jwks)
    # Sign with a different key but advertise original kid — signature fails
    other_sk, other_pk = generate_keypair()
    doc = resign(doc, other_sk, kid="proof-2026-09")
    with pytest.raises(VerifyError, match="signature"):
        verify_proof(doc, jwks)

    # Or advertise a kid absent from JWKS
    doc2, jwks2 = make_fragmentation_proof()
    doc2["signature"]["kid"] = "no-such-kid"
    with pytest.raises(VerifyError, match="signature"):
        verify_proof(doc2, jwks2)


def test_reject_truncated_causal_chain():
    seal_sk, proof_sk, jwks = make_keys()
    doc, jwks = make_fragmentation_proof(seal_sk=seal_sk, proof_sk=proof_sk, jwks=jwks)
    assert len(doc["causal_chain"]) >= 1
    doc["causal_chain"] = doc["causal_chain"][:0]  # truncate all
    # Keep causal_chain_len so length check also fires; closure idxs missing too
    doc = resign(doc, proof_sk)
    with pytest.raises(VerifyError, match="causal_chain"):
        verify_proof(doc, jwks)


def test_reject_tampered_excerpt():
    seal_sk, proof_sk, jwks = make_keys()
    doc, jwks = make_fragmentation_proof(seal_sk=seal_sk, proof_sk=proof_sk, jwks=jwks)
    step = doc["causal_chain"][0]
    step["excerpt"] = step["excerpt"] + " TAMPERED"
    # leave excerpt_sha as-is
    doc = resign(doc, proof_sk)
    with pytest.raises(VerifyError, match="excerpt_hashes"):
        verify_proof(doc, jwks)


def test_cli_accept_and_reject(tmp_path: Path):
    seal_sk, proof_sk, jwks = make_keys()
    doc, jwks = make_fragmentation_proof(seal_sk=seal_sk, proof_sk=proof_sk, jwks=jwks)
    proof_path = tmp_path / "proof.json"
    jwks_path = tmp_path / "jwks.json"
    proof_path.write_text(json.dumps(doc), encoding="utf-8")
    jwks_path.write_text(json.dumps(jwks), encoding="utf-8")
    assert cli_main([str(proof_path), "--jwks", str(jwks_path)]) == 0

    doc["verdict"] = "ADMIT"
    doc = resign(doc, proof_sk)
    proof_path.write_text(json.dumps(doc), encoding="utf-8")
    assert cli_main([str(proof_path), "--jwks", str(jwks_path)]) == 1


def test_verify_imports_nothing_from_core():
    """Import-graph isolation: verify/** must not import core."""
    offenders: list[str] = []
    for path in VERIFY_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            offenders.append(f"{path}: syntax error {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "core" or alias.name.startswith("core."):
                        offenders.append(f"{path}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "core" or mod.startswith("core."):
                    offenders.append(f"{path}:{node.lineno}: from {mod}")
    assert not offenders, "verify/ must not import core:\n" + "\n".join(offenders)

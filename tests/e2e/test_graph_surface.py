"""Graph snapshot, prompt router, seal→checkout path."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "graph_surface.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_mock")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "mock")
    monkeypatch.setenv("PRAMANA_SEAL_SK", "")
    monkeypatch.setenv("PRAMANA_PROOF_SK", "")
    monkeypatch.setenv("SEED_DEMO_ON_BOOT", "true")
    from core.config import reset_settings_cache
    from core.db.session import reset_engine

    reset_settings_cache()
    reset_engine()
    import core.app as app_mod

    importlib.reload(app_mod)
    with TestClient(app_mod.app) as c:
        yield c
    reset_engine()
    reset_settings_cache()


def test_graph_snapshot_has_architecture(client: TestClient) -> None:
    r = client.get("/v1/graph/snapshot")
    assert r.status_code == 200
    body = r.json()
    ids = {n["id"] for n in body["nodes"]}
    assert {"user", "seal", "gate", "ledger", "proof"} <= ids
    assert body["edges"]


def test_prompt_routes_fragmentation(client: TestClient) -> None:
    r = client.post("/v1/graph/prompt", json={"text": "run fragmentation"})
    assert r.status_code == 200
    assert r.json()["plan"]["journey"] == "fragmentation"


def test_seal_returns_ledger_then_checkout(client: TestClient) -> None:
    ep = client.post(
        "/v1/episodes",
        json={"utterance": "Order dinner from Swiggy under 600", "force_mock": True},
    )
    assert ep.status_code == 200
    body = ep.json()
    assert body["episode_id"]
    assert "ledger" in body
    assert body["ledger"]["exposure_paise"] == 0
    cid = body["episode_id"]
    chk = client.post(f"/v1/episodes/{cid}/checkout", json={"amount_paise": 54000})
    assert chk.status_code == 200
    out = chk.json()
    assert out["verdict"] in {"ADMIT", "DENY", "ESCALATE"}
    assert out["ledger"] is not None
    g = client.get(f"/v1/graph/snapshot?episode_id={cid}")
    assert g.status_code == 200
    assert g.json()["episode"]["episode_id"] == cid


def test_list_proofs_ok(client: TestClient) -> None:
    client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "pramana"})
    r = client.get("/v1/proofs")
    assert r.status_code == 200
    assert isinstance(r.json()["proofs"], list)

"""E2E: scripted demo journeys J1–J3 (and J4 smoke) via TestClient."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "demo.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_mock")
    monkeypatch.setenv("PRAMANA_SEAL_SK", "")
    monkeypatch.setenv("PRAMANA_PROOF_SK", "")
    monkeypatch.setenv("SEED_DEMO_ON_BOOT", "true")
    monkeypatch.setenv("ALLOW_ORIGINS", "*")

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


def test_demo_scenarios_list(client: TestClient) -> None:
    r = client.get("/v1/demo/scenarios")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["scenarios"]}
    assert {"benign", "payee_hijack", "fragmentation", "fault"} <= ids


def test_j1_benign_pramana(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={"journey": "benign", "mode": "pramana"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["authorize"]["verdict"] == "ADMIT"
    assert body["execution"] is not None
    assert body["execution"]["state"] == "SUCCEEDED"


def test_j2_payee_hijack_pramana_denies(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "pramana"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["authorize"]["verdict"] == "DENY"
    assert body["authorize"]["rule_id"] in {"R3", "R4", "R5", "R10"}
    assert body["authorize"].get("proof_id") or body["authorize"].get("proof")


def test_j2_payee_hijack_baseline_admits(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "baseline"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["authorize"]["verdict"] == "ADMIT"
    assert body["execution"]["state"] == "SUCCEEDED"


def test_j3_fragmentation_pramana(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={"journey": "fragmentation", "mode": "pramana"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["authorize_1"]["verdict"] == "ADMIT"
    assert body["execution_1"]["state"] == "SUCCEEDED"
    assert body["authorize_2"]["verdict"] == "DENY"
    assert body["authorize_2"]["rule_id"] == "R6"


def test_j3_fragmentation_baseline_both_admit(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={"journey": "fragmentation", "mode": "baseline"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["authorize_1"]["verdict"] == "ADMIT"
    assert body["authorize_2"]["verdict"] == "ADMIT"
    # Scare screen: both individually-legal payments must actually capture.
    assert body["execution_1"]["state"] == "SUCCEEDED"
    assert body["execution_2"]["state"] == "SUCCEEDED"
    assert body["ledger"]["exposure_paise"] == 90_000


def test_j4_fault_ambiguous(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={"journey": "fault", "mode": "pramana"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["authorize"]["verdict"] == "ADMIT"
    assert body["execution"]["state"] == "AMBIGUOUS"

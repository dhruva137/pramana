"""E2E: healthz + JWKS smoke."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "health.db"
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

    # Fresh app module binding
    import importlib

    import core.app as app_mod

    importlib.reload(app_mod)
    with TestClient(app_mod.app) as c:
        yield c

    reset_engine()
    reset_settings_cache()


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mock"] is True
    assert "mode" in body


def test_jwks(client: TestClient) -> None:
    r = client.get("/.well-known/pramana-jwks.json")
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert len(keys) >= 2
    kids = {k["kid"] for k in keys}
    assert "seal-2026-09" in kids
    assert "proof-2026-09" in kids
    for k in keys:
        assert k["kty"] == "OKP"
        assert k["crv"] == "Ed25519"
        assert k["x"]


def test_sandbox_mounted(client: TestClient) -> None:
    r = client.get("/sandbox/")
    assert r.status_code == 200
    assert "SIMULATED MERCHANT" in r.json()["banner"]


def test_bench_summary(client: TestClient) -> None:
    r = client.get("/v1/bench/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "metrics" in body

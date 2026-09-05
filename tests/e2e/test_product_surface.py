"""E2E: product surface APIs (dashboard, settings, integrations, narrate)."""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "product_surface.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_mock")
    monkeypatch.setenv("PRAMANA_SEAL_SK", "")
    monkeypatch.setenv("PRAMANA_PROOF_SK", "")
    monkeypatch.setenv("SEED_DEMO_ON_BOOT", "true")
    monkeypatch.setenv("ALLOW_ORIGINS", "*")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

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


def test_dashboard_summary(client: TestClient) -> None:
    r = client.get("/v1/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "health" in body
    assert "episodes" in body
    assert "decisions" in body
    assert "money" in body
    assert "proofs" in body
    assert "recent" in body
    assert isinstance(body["recent"], list)


def test_settings_status_no_secrets(client: TestClient) -> None:
    r = client.get("/v1/settings/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["razorpay"]["live_refused_guard"] is True
    assert "key_secret" not in str(body).lower() or "key_id_prefix" in body["razorpay"]
    blob = r.text.lower()
    assert "mock_secret" not in blob
    assert body["keys"]["seal_kid"]
    assert body["jwks_url"] == "/.well-known/pramana-jwks.json"


def test_razorpay_test_mock(client: TestClient) -> None:
    r = client.post("/v1/integrations/razorpay/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "mock"


def test_integrations_guide(client: TestClient) -> None:
    r = client.get("/v1/integrations/guide")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["deny_is_http_200"] is True
    assert body["razorpay"]["test_only"] is True
    assert body["clone_local"]


def test_razorpay_webhook_stub(client: TestClient) -> None:
    r = client.post(
        "/v1/integrations/razorpay/webhook",
        json={"event": "payment.captured", "payload": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["acked"] is True
    assert body["event"] == "payment.captured"


def test_narrate_proof_template(client: TestClient) -> None:
    demo = client.post(
        "/v1/demo/run", json={"journey": "payee_hijack", "mode": "pramana"}
    )
    assert demo.status_code == 200
    auth = demo.json()["authorize"]
    proof_id = auth.get("proof_id")
    assert proof_id, "expected a divergence proof from payee_hijack"

    r = client.post(f"/v1/proofs/{proof_id}/narrate", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["proof_id"] == proof_id
    assert body["source"] == "template"
    assert body["provider"] is None
    assert "verdict" in body["narrative"].lower() or "rule" in body["narrative"].lower()


def test_narrate_unknown_proof_404(client: TestClient) -> None:
    r = client.post("/v1/proofs/dvp_does_not_exist/narrate", json={})
    assert r.status_code == 404


def test_apply_request_llm_keys_does_not_overwrite_env(monkeypatch) -> None:
    """Header keys must not clobber an already-set .env / process value."""
    monkeypatch.setenv("GEMINI_API_KEY", "from-env-original")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from core.api.deps import apply_request_llm_keys

    out = apply_request_llm_keys(gemini="header-should-not-win", anthropic="anth-header")
    assert out["gemini"] == "header-should-not-win"
    assert os.environ["GEMINI_API_KEY"] == "from-env-original"
    assert os.environ["ANTHROPIC_API_KEY"] == "anth-header"

"""Console operator: tools, approval gate, seed demo. Never in the gate."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "operator_surface.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_mock")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "mock")
    monkeypatch.setenv("PRAMANA_SEAL_SK", "")
    monkeypatch.setenv("PRAMANA_PROOF_SK", "")
    monkeypatch.setenv("SEED_DEMO_ON_BOOT", "false")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from core.config import reset_settings_cache
    from core.db.session import reset_engine

    reset_settings_cache()
    reset_engine()
    import core.app as app_mod

    importlib.reload(app_mod)

    async def _down(settings):
        return {
            "ok": False,
            "host": "http://127.0.0.1:9",
            "model": settings.ollama_model,
            "has_model": False,
        }

    import core.api.operator as op

    monkeypatch.setattr(op, "_ollama_up", _down)

    with TestClient(app_mod.app) as c:
        yield c
    reset_engine()
    reset_settings_cache()


def test_operator_status(client: TestClient) -> None:
    r = client.get("/v1/operator/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "get_dashboard" in body["tools"]
    assert "seed_demo" in body["money_tools"]
    assert "gate" in body["note"].lower()


def test_operator_chat_read_fallback(client: TestClient) -> None:
    r = client.post("/v1/operator/chat", json={"message": "dashboard health"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["pending_approval"] is None
    names = [t["name"] for t in body["tool_trace"]]
    assert names == ["get_dashboard"]


def test_operator_list_proofs_does_not_seal(client: TestClient) -> None:
    r = client.post(
        "/v1/operator/chat",
        json={"message": "list recent proofs", "auto_approve": True},
    )
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["tool_trace"]]
    assert names == ["list_proofs"]
    assert r.json()["pending_approval"] is None


def test_operator_money_needs_approval(client: TestClient) -> None:
    r = client.post(
        "/v1/operator/chat",
        json={"message": "prepare demo data", "auto_approve": False},
    )
    assert r.status_code == 200
    body = r.json()
    pending = body["pending_approval"]
    assert pending is not None
    assert pending["tool"] == "seed_demo"
    listed = client.get("/v1/episodes").json()
    eps = listed if isinstance(listed, list) else listed.get("episodes") or []
    assert eps == [] or all(not e for e in eps) or len(eps) == 0


def test_operator_approve_seed_demo(client: TestClient) -> None:
    ask = client.post(
        "/v1/operator/chat",
        json={"message": "seed demo data", "auto_approve": False},
    )
    aid = ask.json()["pending_approval"]["approval_id"]
    ok = client.post("/v1/operator/approve", json={"approval_id": aid, "approved": True})
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "executed"
    seeded = body["result"]["seeded"]
    assert len(seeded) >= 3
    assert any(row.get("verdict") == "DENY" for row in seeded)
    eid = body["episode_id"]
    assert eid
    g = client.get(f"/v1/graph/snapshot?episode_id={eid}")
    assert g.status_code == 200
    assert g.json()["episode"]["episode_id"] == eid


def test_operator_auto_approve_journey(client: TestClient) -> None:
    r = client.post(
        "/v1/operator/chat",
        json={
            "message": "run fragmentation",
            "auto_approve": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pending_approval"] is None
    assert body["episode_id"]
    last = body["tool_trace"][-1]
    assert last["name"] == "run_journey"
    assert last["result"]["verdict"] in {"ADMIT", "DENY", "ESCALATE"}


def test_operator_reject(client: TestClient) -> None:
    ask = client.post(
        "/v1/operator/chat",
        json={"message": "run payee hijack", "auto_approve": False},
    )
    aid = ask.json()["pending_approval"]["approval_id"]
    no = client.post("/v1/operator/approve", json={"approval_id": aid, "approved": False})
    assert no.status_code == 200
    assert no.json()["status"] == "rejected"
    listed = client.get("/v1/episodes").json()
    eps = listed if isinstance(listed, list) else listed.get("episodes") or []
    assert len(eps) == 0


def test_settings_exposes_operator(client: TestClient) -> None:
    r = client.get("/v1/settings/status")
    assert r.status_code == 200
    op = r.json()["operator"]
    assert op["model"]
    assert "gate" in op["note"].lower()


def test_gate_never_imports_operator() -> None:
    gate = ROOT / "core" / "gate"
    offenders: list[str] = []
    for path in gate.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "operator" in alias.name or "ollama" in alias.name:
                        offenders.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if "operator" in node.module or "ollama" in node.module:
                    offenders.append(f"{path.name}: from {node.module}")
    assert not offenders

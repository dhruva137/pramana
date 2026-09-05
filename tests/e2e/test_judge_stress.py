"""QA judge stress suite — documents API edge behavior.

Run: pytest tests/e2e/test_judge_stress.py -q
Does not rewrite the gate; only exercises HTTP surface via TestClient.
"""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "judge.db"
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


# ---------------------------------------------------------------------------
# Journeys J1–J4 both arms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "journey,mode,expect",
    [
        ("benign", "pramana", {"auth": "ADMIT", "exec": "SUCCEEDED"}),
        ("benign", "baseline", {"auth": "ADMIT", "exec": "SUCCEEDED"}),
        ("payee_hijack", "pramana", {"auth": "DENY"}),
        ("payee_hijack", "baseline", {"auth": "ADMIT", "exec": "SUCCEEDED"}),
        ("fragmentation", "pramana", {"auth1": "ADMIT", "auth2": "DENY"}),
        ("fragmentation", "baseline", {"auth1": "ADMIT", "auth2": "ADMIT"}),
        ("fault", "pramana", {"auth": "ADMIT", "exec": "AMBIGUOUS"}),
        ("fault", "baseline", {"auth": "ADMIT", "exec": "AMBIGUOUS"}),
    ],
)
def test_journeys_both_arms(client: TestClient, journey: str, mode: str, expect: dict) -> None:
    r = client.post("/v1/demo/run", json={"journey": journey, "mode": mode})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    if "auth" in expect:
        assert body["authorize"]["verdict"] == expect["auth"]
    if "exec" in expect:
        assert body["execution"]["state"] == expect["exec"]
    if "auth1" in expect:
        assert body["authorize_1"]["verdict"] == expect["auth1"]
    if "auth2" in expect:
        assert body["authorize_2"]["verdict"] == expect["auth2"]


# ---------------------------------------------------------------------------
# Validation / wrong strings / empty utterance
# ---------------------------------------------------------------------------


def test_demo_unknown_journey_returns_400(client: TestClient) -> None:
    """Unknown journey must be HTTP 400, not a soft 200+ok:false."""
    r = client.post("/v1/demo/run", json={"journey": "j99", "mode": "pramana"})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "UNKNOWN_JOURNEY"


def test_demo_mode_pramana_on_accepted_as_pramana(client: TestClient) -> None:
    """mode='PRAMANA_ON' is an accepted alias for the pramana arm."""
    r = client.post("/v1/demo/run", json={"journey": "benign", "mode": "PRAMANA_ON"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "PRAMANA_ON"
    assert body["authorize"]["verdict"] == "ADMIT"


def test_demo_mode_off_rejected_422(client: TestClient) -> None:
    """Typos like mode='off' must 422 — never silently run Pramana."""
    r = client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "off"})
    assert r.status_code == 422


def test_demo_missing_journey_field_422(client: TestClient) -> None:
    r = client.post("/v1/demo/run", json={})
    assert r.status_code == 422


def test_episode_empty_utterance_422(client: TestClient) -> None:
    r = client.post("/v1/episodes", json={"utterance": ""})
    assert r.status_code == 422
    assert r.json().get("detail")


def test_episode_missing_utterance_422(client: TestClient) -> None:
    r = client.post("/v1/episodes", json={})
    assert r.status_code == 422


def test_episode_wrong_mode_rejected_422(client: TestClient) -> None:
    """mode='on' must 422 — never coerce to PRAMANA_ON."""
    r = client.post(
        "/v1/episodes",
        json={"utterance": "Order dinner from Swiggy under 600", "mode": "on", "force_mock": True},
    )
    assert r.status_code == 422


def test_episode_mode_baseline_lowercase_accepted(client: TestClient) -> None:
    r = client.post(
        "/v1/episodes",
        json={
            "utterance": "Order dinner from Swiggy under 600",
            "mode": "baseline",
            "force_mock": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["mode"] == "BASELINE"


def test_authorize_missing_fields_422(client: TestClient) -> None:
    r = client.post("/v1/actions/authorize", json={})
    assert r.status_code == 422


def test_authorize_unknown_episode_404_error_envelope(client: TestClient) -> None:
    r = client.post(
        "/v1/actions/authorize",
        json={"episode_id": "ep_missing", "action": {"kind": "PAYMENT", "amount_paise": 1}},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "EPISODE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Health / verify / episodes / bench / ping-llm / product surface
# ---------------------------------------------------------------------------


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mock"] is True


def test_bench_summary(client: TestClient) -> None:
    r = client.get("/v1/bench/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "metrics" in body
    assert body["source"] in {"db", "reports", "mock"}


def test_list_episodes(client: TestClient) -> None:
    r = client.get("/v1/episodes")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["episodes"], list)


def test_openapi_export_ok_with_spa_mounted(client: TestClient) -> None:
    """SPA FileResponse routes must not break OpenAPI export."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body.get("openapi")
    assert "paths" in body


def test_dashboard_and_integrations_mounted(client: TestClient) -> None:
    """Console-facing product routes must be mounted (via dashboard/integrations routers)."""
    assert client.get("/v1/dashboard/summary").status_code == 200
    assert client.get("/v1/settings/status").status_code == 200
    assert client.get("/v1/integrations/guide").status_code == 200
    assert client.post("/v1/integrations/razorpay/test", json={}).status_code == 200
    # Fake proof id → route exists, resource missing
    assert client.post("/v1/proofs/dvp_x/narrate").status_code == 404


def test_productization_gaps_404(client: TestClient) -> None:
    assert client.get("/v1/webhooks").status_code in (404, 405)
    assert client.post("/v1/sandbox/tokens", json={}).status_code in (404, 405)
    assert client.get("/v1/api-keys").status_code in (404, 405)


def test_ping_llm_without_keys(client: TestClient) -> None:
    """Without usable keys → ok:false. If .env still supplies a key, provider call may run
    and return ok:false with status_code (e.g. deprecated gemini model 404)."""
    for provider in ("gemini", "anthropic"):
        r = client.post("/v1/settings/ping-llm", json={"provider": provider})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        err = str(body.get("error") or body.get("snippet") or "").lower()
        assert err or body.get("status_code"), body


def test_ping_llm_unknown_provider_is_http_error(client: TestClient) -> None:
    r = client.post("/v1/settings/ping-llm", json={"provider": "openai"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNKNOWN_PROVIDER"


def test_verify_junk_document_accepted_false_not_500(client: TestClient) -> None:
    r = client.post("/v1/verify", json={"document": {"foo": 1}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["accepted"] is False
    assert "message" in body or "check" in body


def test_verify_real_dvp_from_j2(client: TestClient) -> None:
    j2 = client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "pramana"}).json()
    proof_id = j2["authorize"]["proof_id"]
    assert proof_id
    doc = client.get(f"/v1/proofs/{proof_id}").json()["document"]
    vr = client.post("/v1/verify", json={"document": doc})
    assert vr.status_code == 200
    assert vr.json()["accepted"] is True


# ---------------------------------------------------------------------------
# DENY messaging — product vs "broken"
# ---------------------------------------------------------------------------


def test_deny_payload_looks_like_success_with_verdict(client: TestClient) -> None:
    """Gate DENY must be HTTP 200 + ok:true + verdict DENY (not error envelope)."""
    body = client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "pramana"}).json()
    auth = body["authorize"]
    assert auth.get("ok") is True or "verdict" in auth
    assert auth["verdict"] == "DENY"
    assert "error" not in auth or auth.get("error") is None
    deny_traces = [t for t in auth.get("rule_trace") or [] if t.get("verdict") == "DENY"]
    assert deny_traces
    for t in deny_traces:
        assert isinstance(t.get("actual"), str)
        assert isinstance(t.get("expected"), str)


def test_deny_trace_wording_can_read_like_rejection(client: TestClient) -> None:
    """rule_trace.actual is diagnostic DENY text, not a transport failure."""
    body = client.post("/v1/demo/run", json={"journey": "payee_hijack", "mode": "pramana"}).json()
    deny_traces = [
        t for t in (body["authorize"].get("rule_trace") or []) if t.get("verdict") == "DENY"
    ]
    assert any(t.get("rule_id") in {"R3", "R4", "R5", "R10"} for t in deny_traces)
    assert body["ok"] is True
    assert body["authorize"]["verdict"] == "DENY"


def test_empty_action_authorize_422(client: TestClient) -> None:
    """Empty action must be 422 (required amount_paise), never KeyError/500."""
    ep = client.post(
        "/v1/episodes",
        json={"utterance": "Order dinner from Swiggy under 600", "force_mock": True},
    ).json()
    r = client.post(
        "/v1/actions/authorize",
        json={"episode_id": ep["episode_id"], "action": {}},
    )
    assert r.status_code == 422


def test_authorize_after_freeze_is_409_not_deny(client: TestClient) -> None:
    ep = client.post(
        "/v1/episodes",
        json={"utterance": "Order dinner from Swiggy under 600", "force_mock": True},
    ).json()
    eid = ep["episode_id"]
    client.post(f"/v1/episodes/{eid}/freeze", json={"reason": "judge"})
    r = client.post(
        "/v1/actions/authorize",
        json={
            "episode_id": eid,
            "action": {"kind": "PAYMENT", "amount_paise": 1000, "currency": "INR"},
        },
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EPISODE_NOT_OPEN"


# ---------------------------------------------------------------------------
# Concurrent authorize
# ---------------------------------------------------------------------------


def test_concurrent_authorize_does_not_500(client: TestClient) -> None:
    ep = client.post(
        "/v1/episodes",
        json={
            "utterance": "Order dinner from Swiggy, keep it under ₹600.",
            "force_mock": True,
        },
    ).json()
    eid = ep["episode_id"]
    action = {
        "kind": "PAYMENT",
        "amount_paise": 45_000,
        "currency": "INR",
        "payee": {"merchant_id": "swiggy", "account_ref": "acc_swiggy_demo"},
        "items": [{"title": "biryani", "qty": 1}],
        "instrument": "upi_reserve_pay:tok_x",
        "delivery_address_hash": "sha256:demo_address",
        "human_confirmed": True,
    }

    def _one(_: int):
        return client.post(
            "/v1/actions/authorize",
            json={"episode_id": eid, "action": action, "provenance": {}},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_one, i) for i in range(8)]
        for f in as_completed(futs):
            resp = f.result()
            assert resp.status_code < 500, resp.text
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Intentional xfail docs for remaining productization gaps
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="No API-key / auth middleware on /v1/* — productization gap", strict=False)
def test_gap_unauthenticated_authorize_should_401(client: TestClient) -> None:
    r = client.post(
        "/v1/actions/authorize",
        json={"episode_id": "ep_x", "action": {"kind": "PAYMENT", "amount_paise": 1}},
    )
    assert r.status_code == 401


@pytest.mark.xfail(reason="No webhook subscription CRUD — only stub ack today", strict=False)
def test_gap_webhooks_list_missing(client: TestClient) -> None:
    r = client.get("/v1/webhooks")
    assert r.status_code == 200


@pytest.mark.xfail(reason="No sandbox API token mint endpoint — productization gap", strict=False)
def test_gap_sandbox_token_mint_missing(client: TestClient) -> None:
    r = client.post("/v1/sandbox/tokens", json={})
    assert r.status_code in (200, 201)

"""Razorpay integration test + clone-local integration guide."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.api.deps import AppSettings
from core.config import Settings

# Re-export settings_status for the product-surface module surface area
# (implementation lives next to the dashboard route that serves it).
from core.api.dashboard import settings_status as settings_status

router = APIRouter()
logger = logging.getLogger("pramana.integrations")

_RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders?count=1"
_MOCK_MSG = "Mock executor ready; paste rzp_test_* to hit Razorpay test API"


def _ok(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status)


def _err(code: str, message: str, status: int = 400, detail: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return JSONResponse(content=body, status_code=status)


class RazorpayTestRequest(BaseModel):
    key_id: str | None = None
    key_secret: str | None = None


def _resolve_keys(
    body: RazorpayTestRequest | None,
    *,
    header_id: str | None,
    header_secret: str | None,
    settings: Settings,
) -> tuple[str, str]:
    kid = (
        (body.key_id if body else None)
        or header_id
        or settings.razorpay_key_id
        or ""
    ).strip()
    secret = (
        (body.key_secret if body else None)
        or header_secret
        or settings.razorpay_key_secret
        or ""
    ).strip()
    return kid, secret


def _is_mock_or_missing(key_id: str, key_secret: str) -> bool:
    if not key_id or not key_secret:
        return True
    if key_id.startswith("rzp_live_"):
        return False
    if not key_id.startswith("rzp_test_"):
        return True
    if key_id == "rzp_test_mock" or key_id.endswith("_mock"):
        return True
    return False


@router.post("/v1/integrations/razorpay/test")
async def razorpay_test(
    settings: AppSettings,
    body: RazorpayTestRequest | None = None,
    x_key_id: str | None = Header(default=None, alias="X-Pramana-Razorpay-Key-Id"),
    x_key_secret: str | None = Header(default=None, alias="X-Pramana-Razorpay-Key-Secret"),
) -> JSONResponse:
    """Ping Razorpay test API (or report mock readiness). Never logs secrets."""
    kid, secret = _resolve_keys(
        body, header_id=x_key_id, header_secret=x_key_secret, settings=settings
    )

    if kid.startswith("rzp_live_"):
        logger.warning("razorpay test refused live key prefix")
        return _err(
            "LIVE_KEY_REFUSED",
            "Refusing rzp_live_* keys — test mode only (I9).",
            status=400,
        )

    if _is_mock_or_missing(kid, secret):
        return _ok({"ok": True, "mode": "mock", "message": _MOCK_MSG})

    if not kid.startswith("rzp_test_"):
        return _err("INVALID_KEY", "RAZORPAY_KEY_ID must start with rzp_test_", status=400)

    token = base64.b64encode(f"{kid}:{secret}".encode("utf-8")).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                _RAZORPAY_ORDERS_URL,
                headers={"Authorization": f"Basic {token}"},
            )
        return _ok(
            {
                "ok": resp.status_code < 400,
                "mode": "test",
                "status_code": resp.status_code,
                "message": (
                    "Razorpay test API reachable"
                    if resp.status_code < 400
                    else "Razorpay test API returned an error status"
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("razorpay test request failed: %s", type(exc).__name__)
        return _ok(
            {
                "ok": False,
                "mode": "test",
                "error": type(exc).__name__,
                "message": "Failed to reach Razorpay test API",
            }
        )


def integration_guide_payload() -> dict[str, Any]:
    curl_episodes = (
        "curl -s -X POST http://127.0.0.1:8000/v1/episodes \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -d '{\"utterance\":\"Buy groceries up to 2000 rupees\",\"user_ref\":\"usr_demo_1\"}'"
    )
    curl_authorize = (
        "curl -s -X POST http://127.0.0.1:8000/v1/actions/authorize \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -d '{\"episode_id\":\"ep_...\",\"action\":{\"type\":\"upi_collect\","
        "\"amount_paise\":54000,\"payee_id\":\"acct_demo_grocery\",\"category\":\"grocery\","
        "\"instrument_id\":\"upi_reserve_pay:tok_x\"},\"provenance\":[]}'"
    )
    curl_execute = (
        "curl -s -X POST http://127.0.0.1:8000/v1/actions/execute \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -d '{\"decision_id\":\"dec_...\"}'"
    )
    python_snippet = (
        "import httpx\n\n"
        "base = \"http://127.0.0.1:8000\"\n"
        "with httpx.Client(base_url=base, timeout=30.0) as client:\n"
        "    ep = client.post(\"/v1/episodes\", json={\n"
        "        \"utterance\": \"Buy groceries up to 2000 rupees\",\n"
        "        \"user_ref\": \"usr_demo_1\",\n"
        "    }).json()\n"
        "    episode_id = ep[\"episode_id\"]\n\n"
        "    auth = client.post(\"/v1/actions/authorize\", json={\n"
        "        \"episode_id\": episode_id,\n"
        "        \"action\": {\n"
        "            \"type\": \"upi_collect\",\n"
        "            \"amount_paise\": 54000,  # Rs 540 — Razorpay orders.create amount is paise\n"
        "            \"payee_id\": \"acct_demo_grocery\",\n"
        "            \"category\": \"grocery\",\n"
        "            \"instrument_id\": \"upi_reserve_pay:tok_x\",\n"
        "        },\n"
        "        \"provenance\": [],\n"
        "    }).json()\n"
        "    # DENY is HTTP 200 with verdict=\"DENY\" — not an error status\n"
        "    print(auth.get(\"verdict\"), auth.get(\"rule_id\"), auth.get(\"decision_id\"))\n\n"
        "    if auth.get(\"verdict\") == \"ADMIT\":\n"
        "        ex = client.post(\"/v1/actions/execute\", json={\n"
        "            \"decision_id\": auth[\"decision_id\"],\n"
        "        }).json()\n"
        "        print(ex.get(\"state\"), ex.get(\"rzp_order_id\"))\n"
    )
    return {
        "ok": True,
        "title": "Pramana integration guide",
        "base_url": "http://127.0.0.1:8000",
        "architecture": (
            "Agent → Pramana gate (R1–R12) → ADMIT executes Razorpay test/mock; "
            "DENY/ESCALATE returns HTTP 200 + Divergence Proof."
        ),
        "clone_local": [
            "git clone … && pip install -r requirements.txt",
            "cp .env.example .env   # optional: GEMINI_API_KEY, rzp_test_*",
            "python -m core.db.seed --demo",
            "uvicorn core.app:app --port 8000",
            "open / → Settings paste keys → Integrations test → Live J3",
        ],
        "steps": [
            "Seal intent (POST /v1/episodes) before catalog tool results.",
            "Authorize — DENY is HTTP 200 with verdict in body.",
            "On ADMIT only — POST /v1/actions/execute.",
        ],
        "notes": [
            "DENY is HTTP 200 with verdict=DENY (I8) — treat verdict, not status code.",
            "Razorpay orders.create amount is integer paise (1 INR = 100 paise).",
            "Use rzp_test_* only; rzp_live_* is refused (I9).",
            "No LLM in the gate path (I2).",
            "Webhook stub: POST /v1/integrations/razorpay/webhook (ack only).",
        ],
        "deny_is_http_200": True,
        "flow": [
            {"step": 1, "method": "POST", "path": "/v1/episodes", "purpose": "Seal episode"},
            {
                "step": 2,
                "method": "POST",
                "path": "/v1/actions/authorize",
                "purpose": "Gate admit / deny / escalate",
            },
            {
                "step": 3,
                "method": "POST",
                "path": "/v1/actions/execute",
                "purpose": "Execute admitted decision via Razorpay (mock or test)",
            },
        ],
        "curl": {
            "episodes": curl_episodes,
            "authorize": curl_authorize,
            "execute": curl_execute,
        },
        "python": python_snippet,
        "snippets": {
            "curl": {
                "episodes": curl_episodes,
                "authorize": curl_authorize,
                "execute": curl_execute,
            },
            "python": python_snippet,
        },
        "razorpay": {
            "amount_unit": "paise",
            "test_only": True,
            "orders_create_amount": "paise",
            "example": {
                "amount": 54000,
                "currency": "INR",
                "note": "amount is paise — never float rupees",
            },
            "test_ping": "POST /v1/integrations/razorpay/test",
        },
    }


def webhook_ack(payload: Any = None) -> dict[str, Any]:
    """Stub Razorpay webhook receiver — ack only; wire secret verify in production."""
    event = None
    if isinstance(payload, dict):
        event = payload.get("event") or (payload.get("payload") or {}).get("event")
    return {
        "ok": True,
        "acked": True,
        "event": event,
        "note": "stub receiver — wire webhook secret verification in production",
    }


def integrations_guide() -> dict[str, Any]:
    return integration_guide_payload()


@router.get("/v1/integrations/guide")
async def get_integrations_guide() -> JSONResponse:
    return _ok(integrations_guide())


@router.post("/v1/integrations/razorpay/webhook")
async def razorpay_webhook(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = None
    logger.info("razorpay webhook stub ack event=%s", webhook_ack(payload).get("event"))
    return _ok(webhook_ack(payload), status=200)

"""FastAPI routers for Pramana HTTP API."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from core.api.constants import BENCH_SUMMARY_MOCK
from core.api.ctx_ledger import append_context_entry
from core.api.dashboard import router as dashboard_router
from core.api.demo_journeys import SCENARIOS, run_demo_journey
from core.api.deps import AppSettings, DbSession, RzpClient, apply_request_llm_keys
from core.api.graph import router as graph_router
from core.api.integrations import router as integrations_router
from core.api.operator import router as operator_router
from core.api.schemas import (
    AuthorizeRequest,
    ConfirmRequest,
    ContextAppendRequest,
    DemoRunRequest,
    EpisodeCreateRequest,
    ExecuteRequest,
    FreezeRequest,
    PingLlmRequest,
    VerifyRequest,
)
from core.api.services import (
    authorize_action,
    create_sealed_episode,
    episode_snapshot,
)
from core.db.models import BenchRun, Decision, Episode, Proof
from core.exec.executor import (
    ExecuteError,
    execute_decision,
    execution_to_dict,
    parse_fault_header,
)
from core.ledger import service as ledger
from core.proof.pdf import render_proof_pdf
from core.seal.sealer import ContextTaintedError
from verify.verifier import VerifyError, verify_proof

router = APIRouter()


def _ok(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status)


def _err(code: str, message: str, status: int = 400, detail: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return JSONResponse(content=body, status_code=status)


# ---------------------------------------------------------------------------
# Health / JWKS
# ---------------------------------------------------------------------------


@router.get("/healthz")
async def healthz(settings: AppSettings) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": settings.mode_label(),
        "mock": settings.effective_mock,
        "ephemeral_keys": settings.ephemeral_keys,
        "env": settings.pramana_env,
    }


@router.get("/.well-known/pramana-jwks.json")
async def jwks(settings: AppSettings) -> dict[str, Any]:
    return settings.jwks()


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


@router.post("/v1/episodes")
async def post_episode(
    body: EpisodeCreateRequest,
    session: DbSession,
    settings: AppSettings,
    _keys: dict[str, str | None] = Depends(apply_request_llm_keys),
) -> JSONResponse:
    try:
        episode, env, ctx = await create_sealed_episode(
            session,
            settings,
            utterance=body.utterance,
            user_ref=body.user_ref,
            consent_ref=body.consent_ref,
            consent_cap_paise=body.consent_cap_paise,
            agent_id=body.agent_id,
            mode=body.mode,
            delivery_address_hash=body.delivery_address_hash,
            allowed_instruments=body.allowed_instruments,
            force_mock=body.force_mock if body.force_mock is not None else settings.mock_mode,
        )
    except ContextTaintedError as exc:
        return _err("CONTEXT_TAINTED", exc.detail, status=409)
    except Exception as exc:  # noqa: BLE001
        return _err("SEAL_FAILED", str(exc), status=500)

    from core.api.services import ledger_state_to_gate
    from core.ledger import service as ledger

    state = await ledger.get_ledger_state(session, episode.id)
    constraints = (env.get("constraints") or {})
    led = ledger_state_to_gate(state)
    led["cap_paise"] = int(constraints.get("episode_total_max_paise") or 0)
    led["max_transactions"] = int(constraints.get("max_transactions") or 0)
    led["status"] = episode.status

    return _ok(
        {
            "ok": True,
            "episode_id": episode.id,
            "status": episode.status,
            "mode": episode.mode,
            "envelope": env,
            "ledger": led,
            "context_ledger": ctx,
            "degraded": bool((env.get("extraction") or {}).get("degraded")),
        }
    )


@router.get("/v1/episodes")
async def list_episodes(session: DbSession, limit: int = 50) -> JSONResponse:
    """Episode history, newest first.

    The console's History page has always called this; it did not exist, so the
    page rendered an empty table against a 404. Returns the summary columns the
    table shows, including the proof id it needs for the offline-verify button.
    """
    rows = (
        await session.execute(
            select(Episode).order_by(Episode.created_at.desc()).limit(max(1, min(limit, 200)))
        )
    ).scalars().all()

    episodes: list[dict[str, Any]] = []
    for ep in rows:
        state = await ledger.get_ledger_state(session, ep.id)
        last = (
            await session.execute(
                select(Decision)
                .where(Decision.episode_id == ep.id)
                .order_by(Decision.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        proof = (
            await session.execute(
                select(Proof)
                .where(Proof.episode_id == ep.id)
                .order_by(Proof.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        constraints = (ep.envelope or {}).get("constraints") or {}
        episodes.append(
            {
                "episode_id": ep.id,
                "created_at": ep.created_at.isoformat() if ep.created_at else None,
                "status": ep.status,
                "arm": "baseline" if ep.mode == "BASELINE" else "pramana",
                "utterance": ((ep.envelope or {}).get("utterance") or {}).get("excerpt"),
                "verdict": last.verdict if last else None,
                "rule_id": last.rule_id if last else None,
                "spent_paise": int(state.exposure_paise),
                "cap_paise": int(constraints.get("episode_total_max_paise") or 0),
                "txn_count": int(state.txn_count),
                "proof_id": proof.id if proof else None,
                "context_ledger_head": ep.ctx_ledger_head,
                "decision_chain_head": last.hash if last else None,
            }
        )
    return _ok({"ok": True, "episodes": episodes})


@router.get("/v1/episodes/{episode_id}")
async def get_episode(episode_id: str, session: DbSession) -> JSONResponse:
    snap = await episode_snapshot(session, episode_id)
    if snap is None:
        return _err("EPISODE_NOT_FOUND", f"unknown episode {episode_id}", status=404)
    return _ok({"ok": True, **snap})


@router.post("/v1/episodes/{episode_id}/context")
async def post_context(
    episode_id: str,
    body: ContextAppendRequest,
    session: DbSession,
) -> JSONResponse:
    from core.db.models import Episode

    ep = await session.get(Episode, episode_id)
    if ep is None:
        return _err("EPISODE_NOT_FOUND", f"unknown episode {episode_id}", status=404)
    if ep.status != "OPEN":
        return _err("EPISODE_NOT_OPEN", f"status={ep.status}", status=409)

    entry = await append_context_entry(
        session,
        episode_id=episode_id,
        role=body.role,
        taint=body.taint,
        content=body.content,
        source_uri=body.source_uri,
        tool=body.tool,
        detector=body.detector,
    )
    return _ok({"ok": True, "entry": entry, "ctx_ledger_head": ep.ctx_ledger_head})


@router.post("/v1/episodes/{episode_id}/confirm")
async def post_confirm(
    episode_id: str,
    body: ConfirmRequest,
    session: DbSession,
    settings: AppSettings,
) -> JSONResponse:
    """Resolve an ESCALATE by re-authorizing with human_confirmed=True."""
    if not body.approved:
        from core.db.models import Episode

        ep = await session.get(Episode, episode_id)
        if ep is not None:
            ep.status = "FROZEN"
        return _ok(
            {
                "ok": True,
                "approved": False,
                "episode_id": episode_id,
                "status": "FROZEN",
            }
        )

    action = body.action
    provenance = body.provenance
    if body.decision_id and action is None:
        prior = await session.get(Decision, body.decision_id)
        if prior is None:
            return _err("DECISION_NOT_FOUND", body.decision_id, status=404)
        action = dict(prior.action or {})
        provenance = prior.provenance
    if action is None:
        return _err("MISSING_ACTION", "action or decision_id required")

    action = dict(action)
    action["human_confirmed"] = True
    result = await authorize_action(
        session,
        settings,
        episode_id=episode_id,
        action=action,
        provenance=provenance,
        now=datetime.now(timezone.utc),
    )
    return _ok({"ok": True, "approved": True, **result})


@router.post("/v1/episodes/{episode_id}/freeze")
async def post_freeze(
    episode_id: str,
    session: DbSession,
    body: FreezeRequest | None = None,
) -> JSONResponse:
    from core.db.models import Episode

    ep = await session.get(Episode, episode_id)
    if ep is None:
        return _err("EPISODE_NOT_FOUND", f"unknown episode {episode_id}", status=404)
    ep.status = "FROZEN"
    await session.flush()
    return _ok(
        {
            "ok": True,
            "episode_id": episode_id,
            "status": "FROZEN",
            "reason": (body.reason if body else None),
        }
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@router.post("/v1/actions/authorize")
async def post_authorize(
    body: AuthorizeRequest,
    session: DbSession,
    settings: AppSettings,
) -> JSONResponse:
    action = dict(body.action)
    if body.human_confirmed is not None:
        action["human_confirmed"] = body.human_confirmed
    result = await authorize_action(
        session,
        settings,
        episode_id=body.episode_id,
        action=action,
        provenance=body.provenance,
        now=datetime.now(timezone.utc),
    )
    # Verdicts are never HTTP errors
    status = 200 if result.get("ok") is not False or "verdict" in result else 200
    if result.get("error") and "verdict" not in result:
        code = result["error"].get("code", "ERROR")
        http = 404 if code.endswith("NOT_FOUND") else 409 if "NOT_OPEN" in code else 400
        return _err(code, result["error"].get("message", ""), status=http)
    return _ok(result, status=status)


@router.post("/v1/actions/execute")
async def post_execute(
    body: ExecuteRequest,
    session: DbSession,
    client: RzpClient,
    x_pramana_fault: str | None = Header(default=None, alias="X-Pramana-Fault"),
) -> JSONResponse:
    try:
        fault = parse_fault_header(x_pramana_fault)
        result = await execute_decision(
            session, body.decision_id, client=client, fault=fault
        )
        return _ok({"ok": True, **execution_to_dict(result)})
    except ExecuteError as exc:
        return _err(exc.code, exc.message, status=400)
    except Exception as exc:  # noqa: BLE001
        return _err("EXECUTE_FAILED", str(exc), status=500)


# ---------------------------------------------------------------------------
# Proofs / verify
# ---------------------------------------------------------------------------


@router.get("/v1/proofs/{proof_id}")
async def get_proof(
    proof_id: str,
    session: DbSession,
    format: str = Query(default="json"),
) -> Response:
    row = await session.get(Proof, proof_id)
    if row is None:
        # Also allow lookup by decision_id
        q = await session.execute(select(Proof).where(Proof.decision_id == proof_id))
        row = q.scalar_one_or_none()
    if row is None:
        return _err("PROOF_NOT_FOUND", f"unknown proof {proof_id}", status=404)

    if format.lower() == "pdf":
        pdf = render_proof_pdf(row.document)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{row.id}.pdf"'},
        )
    return _ok({"ok": True, "proof_id": row.id, "document": row.document})


@router.post("/v1/verify")
async def post_verify(body: VerifyRequest, settings: AppSettings) -> JSONResponse:
    jwks = body.jwks or settings.jwks()
    try:
        verify_proof(body.document, jwks)
        return _ok({"ok": True, "accepted": True})
    except VerifyError as exc:
        return _ok(
            {
                "ok": True,
                "accepted": False,
                "check": exc.check,
                "message": str(exc),
            }
        )


# ---------------------------------------------------------------------------
# Demo / settings / bench
# ---------------------------------------------------------------------------


@router.get("/v1/demo/scenarios")
async def demo_scenarios() -> dict[str, Any]:
    return {"ok": True, "scenarios": SCENARIOS}


@router.post("/v1/demo/run")
async def demo_run(
    body: DemoRunRequest,
    session: DbSession,
    settings: AppSettings,
    client: RzpClient,
) -> JSONResponse:
    result = await run_demo_journey(
        session,
        settings,
        client,
        journey=body.journey,
        mode=body.mode,
    )
    if result.get("ok") is False and (result.get("error") or {}).get("code") == "UNKNOWN_JOURNEY":
        return _err(
            "UNKNOWN_JOURNEY",
            (result.get("error") or {}).get("message") or "unknown journey",
            status=400,
        )
    return _ok(result)


@router.post("/v1/settings/ping-llm")
async def ping_llm(
    body: PingLlmRequest,
    request: Request,
    settings: AppSettings,
    x_gemini: str | None = Header(default=None, alias="X-Pramana-Gemini-Key"),
    x_anthropic: str | None = Header(default=None, alias="X-Pramana-Anthropic-Key"),
) -> JSONResponse:
    provider = body.provider.strip().lower()
    if provider == "gemini":
        key = body.api_key or x_gemini or settings.gemini_api_key or os.environ.get(
            "GEMINI_API_KEY", ""
        )
        if not key:
            return _ok({"ok": False, "provider": "gemini", "error": "missing api key"})
        model = settings.gemini_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as http:
                resp = await http.post(
                    url,
                    json={
                        "contents": [
                            {"parts": [{"text": "Reply with exactly: pong"}]}
                        ]
                    },
                )
            return _ok(
                {
                    "ok": resp.status_code < 400,
                    "provider": "gemini",
                    "status_code": resp.status_code,
                    "snippet": resp.text[:200],
                }
            )
        except Exception as exc:  # noqa: BLE001
            return _ok({"ok": False, "provider": "gemini", "error": str(exc)})

    if provider == "anthropic":
        key = body.api_key or x_anthropic or settings.anthropic_api_key or os.environ.get(
            "ANTHROPIC_API_KEY", ""
        )
        if not key:
            return _ok({"ok": False, "provider": "anthropic", "error": "missing api key"})
        try:
            async with httpx.AsyncClient(timeout=20.0) as http:
                resp = await http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
                    },
                )
            return _ok(
                {
                    "ok": resp.status_code < 400,
                    "provider": "anthropic",
                    "status_code": resp.status_code,
                    "snippet": resp.text[:200],
                }
            )
        except Exception as exc:  # noqa: BLE001
            return _ok({"ok": False, "provider": "anthropic", "error": str(exc)})

    return _err("UNKNOWN_PROVIDER", f"provider must be gemini|anthropic, got {provider}")


@router.get("/v1/bench/summary")
async def bench_summary(session: DbSession) -> JSONResponse:
    q = await session.execute(
        select(BenchRun).order_by(BenchRun.started_at.desc()).limit(1)
    )
    run = q.scalar_one_or_none()
    if run is not None and run.metrics:
        return _ok(
            {
                "ok": True,
                "source": "db",
                "run_id": run.id,
                "metrics": run.metrics,
            }
        )

    # Real runner reports on disk beat mock data. The Benchmark screen exists to
    # show honest numbers; falling through to BENCH_SUMMARY_MOCK while a finished
    # 128-episode run sits in reports/ is the one thing it must not do.
    from core.api.bench_summary import build_summary

    disk = build_summary()
    if disk is not None:
        return _ok({"ok": True, "source": "reports", "metrics": disk})

    return _ok({"ok": True, "source": "mock", "metrics": BENCH_SUMMARY_MOCK})


# ---------------------------------------------------------------------------
# Product surfaces (dashboard / settings / integrations)
# ---------------------------------------------------------------------------

router.include_router(dashboard_router)
router.include_router(integrations_router)
router.include_router(graph_router)
router.include_router(operator_router)

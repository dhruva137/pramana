"""Product dashboard, settings status, and optional proof narration."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import AppSettings, DbSession
from core.config import Settings
from core.db.models import Decision, Episode, LedgerEntry, Proof
from core.ledger import service as ledger

router = APIRouter()


def _ok(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status)


def _err(code: str, message: str, status: int = 400, detail: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return JSONResponse(content=body, status_code=status)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _truthy(value: str | None) -> bool:
    return bool((value or "").strip())


def _gemini_configured(settings: Settings) -> bool:
    return _truthy(settings.gemini_api_key) or _truthy(os.environ.get("GEMINI_API_KEY"))


def _anthropic_configured(settings: Settings) -> bool:
    return _truthy(settings.anthropic_api_key) or _truthy(os.environ.get("ANTHROPIC_API_KEY"))


def sealer_mode(settings: Settings) -> str:
    if settings.mock_mode:
        return "mock"
    if _anthropic_configured(settings):
        return "anthropic"
    if _gemini_configured(settings):
        return "gemini"
    return "mock"


def razorpay_key_prefix(key_id: str | None) -> str:
    kid = (key_id or "").strip()
    if not kid:
        return ""
    return kid if len(kid) <= 12 else kid[:12]


def razorpay_configured(key_id: str | None, key_secret: str | None) -> bool:
    kid = (key_id or "").strip()
    if not kid.startswith("rzp_test_"):
        return False
    if kid == "rzp_test_mock" or kid.endswith("_mock"):
        return False
    return _truthy(key_secret)


async def build_dashboard_summary(
    session: AsyncSession,
    settings: Settings,
) -> dict[str, Any]:
    now = _utcnow()
    since_24h = now - timedelta(hours=24)

    episodes = list(
        (await session.execute(select(Episode).order_by(Episode.created_at.desc())))
        .scalars()
        .all()
    )
    status_counts = {"OPEN": 0, "FROZEN": 0, "QUARANTINED": 0, "CLOSED": 0, "EXPIRED": 0}
    for ep in episodes:
        key = (ep.status or "").upper()
        if key in status_counts:
            status_counts[key] += 1

    verdict_rows = (
        await session.execute(select(Decision.verdict, func.count()).group_by(Decision.verdict))
    ).all()
    verdict_counts = {str(v).upper(): int(c) for v, c in verdict_rows}
    last_24h = int(
        (
            await session.execute(
                select(func.count()).select_from(Decision).where(Decision.created_at >= since_24h)
            )
        ).scalar_one()
        or 0
    )

    capture_sum = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).where(
                    LedgerEntry.kind == "CAPTURE"
                )
            )
        ).scalar_one()
        or 0
    )
    refund_sum = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).where(
                    LedgerEntry.kind == "REFUND"
                )
            )
        ).scalar_one()
        or 0
    )
    captured_paise = int(capture_sum) - int(refund_sum)

    held_paise = 0
    for ep in episodes:
        state = await ledger.get_ledger_state(session, ep.id)
        held_paise += int(state.held_paise)

    denied_intended = 0
    for d in (
        await session.execute(select(Decision).where(Decision.verdict == "DENY"))
    ).scalars().all():
        try:
            denied_intended += int((d.action or {}).get("amount_paise") or 0)
        except (TypeError, ValueError):
            continue

    proof_count = int(
        (await session.execute(select(func.count()).select_from(Proof))).scalar_one() or 0
    )
    last_proof = (
        await session.execute(select(Proof).order_by(Proof.created_at.desc()).limit(1))
    ).scalar_one_or_none()

    recent: list[dict[str, Any]] = []
    for ep in episodes[:12]:
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
        recent.append(
            {
                "episode_id": ep.id,
                "status": ep.status,
                "arm": "baseline" if ep.mode == "BASELINE" else "pramana",
                "verdict": last.verdict if last else None,
                "spent_paise": int(state.exposure_paise),
                "proof_id": proof.id if proof else None,
                "created_at": ep.created_at.isoformat() if ep.created_at else None,
                "utterance": ((ep.envelope or {}).get("utterance") or {}).get("excerpt"),
            }
        )

    # 14-day episode volume (for dashboard sparklines / area charts)
    day_counts: dict[str, int] = {}
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        day_counts[day] = 0
    for ep in episodes:
        if not ep.created_at:
            continue
        day = ep.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        if day in day_counts:
            day_counts[day] += 1
    volume_series = [{"day": d, "count": c} for d, c in day_counts.items()]

    # Verdict mix for donut
    admit_n = verdict_counts.get("ADMIT", 0)
    deny_n = verdict_counts.get("DENY", 0)
    escalate_n = verdict_counts.get("ESCALATE", 0)

    bench_block: dict[str, Any] = {
        "source": "none",
        "overall_asr_baseline": None,
        "overall_asr_pramana": None,
        "asr_by_family": [],
        "shopper_mode": None,
        "latency_p95_ms": None,
    }
    try:
        from core.api.bench_summary import build_summary

        disk = build_summary()
        if disk is not None:
            asr = disk.get("asr_overall") or {}
            lat = disk.get("latency") or {}
            bench_block = {
                "source": "reports",
                "overall_asr_baseline": asr.get("baseline"),
                "overall_asr_pramana": asr.get("pramana"),
                "asr_by_family": disk.get("asr_by_family") or [],
                "shopper_mode": disk.get("shopper_mode"),
                "latency_p95_ms": lat.get("p95_ms"),
                "baseline_display": asr.get("baseline_display"),
                "pramana_display": asr.get("pramana_display"),
            }
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "health": {
            "ok": True,
            "mock": settings.effective_mock,
            "mode": settings.mode_label(),
            "ephemeral_keys": settings.ephemeral_keys,
        },
        "episodes": {
            "total": len(episodes),
            "open": status_counts["OPEN"],
            "frozen": status_counts["FROZEN"],
            "quarantined": status_counts["QUARANTINED"],
            "closed": status_counts["CLOSED"] + status_counts["EXPIRED"],
        },
        "decisions": {
            "admit": admit_n,
            "deny": deny_n,
            "escalate": escalate_n,
            "last_24h": last_24h,
        },
        "money": {
            "captured_paise": int(captured_paise),
            "held_paise": int(held_paise),
            "denied_intended_paise": int(denied_intended),
        },
        "proofs": {"count": proof_count, "last_id": last_proof.id if last_proof else None},
        "charts": {
            "episode_volume": volume_series,
            "verdict_mix": [
                {"key": "admit", "label": "ADMIT", "count": admit_n},
                {"key": "deny", "label": "DENY", "count": deny_n},
                {"key": "escalate", "label": "ESCALATE", "count": escalate_n},
            ],
            "money_split": [
                {
                    "key": "protected",
                    "label": "Denied (intended)",
                    "paise": int(denied_intended),
                },
                {
                    "key": "captured",
                    "label": "Captured",
                    "paise": max(0, int(captured_paise)),
                },
                {
                    "key": "held",
                    "label": "Held",
                    "paise": int(held_paise),
                },
            ],
        },
        "recent": recent,
        "bench": bench_block,
    }


def settings_status(settings: Settings) -> dict[str, Any]:
    kid = settings.razorpay_key_id
    secret = settings.razorpay_key_secret
    return {
        "ok": True,
        "mock_mode": settings.mock_mode,
        "env": settings.pramana_env,
        "razorpay": {
            "configured": razorpay_configured(kid, secret),
            "key_id_prefix": razorpay_key_prefix(kid),
            "test_mode": True,
            "live_refused_guard": True,
        },
        "llm": {
            "gemini_configured": _gemini_configured(settings),
            "anthropic_configured": _anthropic_configured(settings),
            "sealer_mode": sealer_mode(settings),
        },
        "keys": {
            "seal_kid": settings.pramana_seal_kid,
            "proof_kid": settings.pramana_proof_kid,
            "ephemeral": settings.ephemeral_keys,
        },
        "jwks_url": "/.well-known/pramana-jwks.json",
        "operator": {
            "host": settings.ollama_host,
            "model": settings.ollama_model,
            "note": "Console operator only. Gate R1–R12 never calls Ollama.",
        },
        "note": "Paste keys in console Settings or .env — never commit secrets",
    }


def template_narrative(document: dict[str, Any]) -> str:
    decision = document.get("decision") or {}
    verdict = decision.get("verdict") or document.get("verdict") or "UNKNOWN"
    rule_id = decision.get("rule_id") or document.get("rule_id")
    action = document.get("action") or {}
    amount = action.get("amount_paise")
    payee = action.get("payee_id") or action.get("payee")

    lines = [
        f"Gate verdict: {verdict}" + (f" (decisive rule {rule_id})." if rule_id else "."),
    ]
    if amount is not None:
        try:
            lines.append(f"Proposed amount: {int(amount)} paise.")
        except (TypeError, ValueError):
            pass
    if payee:
        lines.append(f"Proposed payee: {payee}.")

    trace = decision.get("rule_trace") or document.get("rule_trace") or []
    if isinstance(trace, list) and trace:
        lines.append("Rule trace:")
        for row in trace:
            if not isinstance(row, dict):
                continue
            rid = row.get("rule_id") or "?"
            rv = row.get("verdict") or "?"
            expected = row.get("expected") or ""
            actual = row.get("actual") or ""
            lines.append(f"  - {rid}: {rv} (expected={expected}; actual={actual})")
    else:
        lines.append("No rule_trace recorded on this proof.")

    lines.append("This is a post-hoc narrative only; the sealed DVP verdict is unchanged.")
    return "\n".join(lines)


async def _llm_narrate(
    document: dict[str, Any],
    *,
    gemini_key: str | None,
    anthropic_key: str | None,
    settings: Settings,
) -> tuple[str | None, str | None]:
    base = template_narrative(document)
    prompt = (
        "Explain this Pramana Decision Verification Proof in plain English. "
        "Do NOT change or reinterpret the gate verdict — only explain why the "
        "deterministic rules produced it. Keep it under 200 words.\n\n"
        f"{base}"
    )

    if anthropic_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 400,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
            if resp.status_code < 400:
                data = resp.json()
                parts = data.get("content") or []
                text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
                if text:
                    return text, "anthropic"
        except Exception:  # noqa: BLE001
            pass

    if gemini_key:
        model = settings.gemini_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={gemini_key}"
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            if resp.status_code < 400:
                data = resp.json()
                cands = data.get("candidates") or []
                if cands:
                    parts = ((cands[0].get("content") or {}).get("parts")) or []
                    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
                    if text:
                        return text, "gemini"
        except Exception:  # noqa: BLE001
            pass

    return None, None


@router.get("/v1/dashboard/summary")
async def dashboard_summary(session: DbSession, settings: AppSettings) -> JSONResponse:
    return _ok(await build_dashboard_summary(session, settings))


@router.get("/v1/settings/status")
async def get_settings_status(settings: AppSettings) -> JSONResponse:
    return _ok(settings_status(settings))


@router.post("/v1/proofs/{proof_id}/narrate")
async def narrate_proof(
    proof_id: str,
    session: DbSession,
    settings: AppSettings,
    x_gemini: str | None = Header(default=None, alias="X-Pramana-Gemini-Key"),
    x_anthropic: str | None = Header(default=None, alias="X-Pramana-Anthropic-Key"),
) -> JSONResponse:
    """Optional after-the-fact LLM explanation. Never imported into the gate."""
    row = await session.get(Proof, proof_id)
    if row is None:
        row = (
            await session.execute(select(Proof).where(Proof.decision_id == proof_id))
        ).scalar_one_or_none()
    if row is None:
        return _err("PROOF_NOT_FOUND", f"unknown proof {proof_id}", status=404)

    document = dict(row.document or {})
    gemini_key = x_gemini or settings.gemini_api_key or os.environ.get("GEMINI_API_KEY") or ""
    anthropic_key = (
        x_anthropic or settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
    )

    if gemini_key or anthropic_key:
        llm_text, provider = await _llm_narrate(
            document,
            gemini_key=gemini_key or None,
            anthropic_key=anthropic_key or None,
            settings=settings,
        )
        if llm_text:
            narrative, source = llm_text, (provider or "llm")
        else:
            narrative, source = template_narrative(document), "template"
    else:
        narrative, source = template_narrative(document), "template"

    verdict = (document.get("decision") or {}).get("verdict") or document.get("verdict")
    provider = None
    if source not in (None, "template"):
        provider = source if source in ("gemini", "anthropic") else "llm"
        source = "llm"
    return _ok(
        {
            "ok": True,
            "proof_id": row.id,
            "verdict": verdict,
            "source": source,
            "provider": provider,
            "narrative": narrative,
            "note": "Post-hoc explanation only — gate verdict unchanged",
        }
    )

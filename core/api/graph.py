"""Living architecture / knowledge-graph surface.

Read-only projection of the control plane plus a keyword (optional LLM) prompt
router. Never imported by ``core.gate``.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.api.constants import MERCHANT_RECORDS
from core.api.ctx_ledger import append_context_entry
from core.api.deps import AppSettings, DbSession, RzpClient
from core.api.services import authorize_action, episode_snapshot
from core.db.models import Episode, Proof
from core.exec.executor import execute_decision, execution_to_dict

router = APIRouter()


def _ok(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status)


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        content={"ok": False, "error": {"code": code, "message": message}},
        status_code=status,
    )


class GraphPromptRequest(BaseModel):
    text: str = Field(..., min_length=1)
    episode_id: str | None = None
    compare: bool = True


class CheckoutRequest(BaseModel):
    amount_paise: int = Field(default=54_000, ge=1)
    human_confirmed: bool = True


def _node(
    nid: str,
    label: str,
    kind: str,
    *,
    detail: str = "",
    state: str = "idle",
    x: float = 0.5,
    y: float = 0.5,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": nid,
        "label": label,
        "kind": kind,
        "detail": detail,
        "state": state,
        "x": x,
        "y": y,
        "meta": meta or {},
    }


def _edge(src: str, dst: str, label: str = "", *, active: bool = False) -> dict[str, Any]:
    return {"source": src, "target": dst, "label": label, "active": active}


def architecture_skeleton() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [
        _node("user", "User intent", "user", detail="Trusted channel", x=0.10, y=0.42),
        _node("seal", "Seal", "seal", detail="Ed25519 envelope", x=0.26, y=0.28),
        _node("envelope", "Envelope", "envelope", detail="Caps · payees · instruments", x=0.42, y=0.22),
        _node("context", "Context ledger", "context", detail="Taint-tagged hash chain", x=0.42, y=0.62),
        _node("gate", "Gate R1–R12", "gate", detail="Deterministic · no LLM", x=0.62, y=0.42),
        _node("r6", "R6 ledger", "rule", detail="Episode ceiling", x=0.62, y=0.68),
        _node("ledger", "Episode spend", "ledger", detail="exposure vs seal", x=0.78, y=0.62),
        _node("exec", "Razorpay test", "money", detail="HOLD then capture", x=0.82, y=0.28),
        _node("proof", "Divergence proof", "proof", detail="Portable DVP", x=0.78, y=0.82),
        _node("baseline", "Baseline rail", "baseline", detail="Per-txn only", x=0.26, y=0.78),
    ]
    edges = [
        _edge("user", "seal", "utterance"),
        _edge("seal", "envelope", "sign"),
        _edge("user", "context", "USER"),
        _edge("envelope", "gate", "constraints"),
        _edge("context", "gate", "provenance"),
        _edge("gate", "r6", "sequence"),
        _edge("r6", "ledger", "exposure"),
        _edge("gate", "exec", "ADMIT"),
        _edge("gate", "proof", "DENY"),
        _edge("baseline", "exec", "blind"),
    ]
    return nodes, edges


def overlay_episode(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    snap: dict[str, Any],
) -> None:
    by_id = {n["id"]: n for n in nodes}
    env = snap.get("envelope") or {}
    constraints = env.get("constraints") or {}
    utterance = ((env.get("utterance") or {}).get("excerpt")) or ""
    ledger_s = snap.get("ledger") or {}
    ctx = snap.get("context_ledger") or []
    decisions = snap.get("decisions") or []

    if utterance and "user" in by_id:
        by_id["user"]["detail"] = utterance[:96]
        by_id["user"]["state"] = "live"

    if env and "envelope" in by_id:
        cap = constraints.get("episode_total_max_paise")
        by_id["envelope"]["state"] = "live"
        by_id["envelope"]["detail"] = (
            f"cap ₹{(int(cap) / 100):.0f}" if cap else "sealed"
        )
        by_id["seal"]["state"] = "done"

    if ctx:
        by_id["context"]["state"] = "live"
        by_id["context"]["detail"] = f"{len(ctx)} entries"
        last = ctx[-1] if isinstance(ctx[-1], dict) else {}
        if last.get("taint") and str(last.get("taint")).endswith("FREETEXT"):
            by_id["context"]["state"] = "warn"

    last_verdict = None
    last_rule = None
    for i, d in enumerate(decisions):
        nid = f"dec_{i + 1}"
        v = str(d.get("verdict") or "—")
        last_verdict = v
        last_rule = d.get("rule_id")
        amt = (d.get("action") or {}).get("amount_paise")
        nodes.append(
            _node(
                nid,
                f"Authorize {i + 1}",
                "decision",
                detail=f"{v}" + (f" · ₹{int(amt) / 100:.0f}" if amt else ""),
                state="deny" if v == "DENY" else "admit" if v == "ADMIT" else "live",
                x=0.58 + i * 0.08,
                y=0.12 + (0.08 if i % 2 else 0),
                meta={"decision_id": d.get("id"), "rule_id": d.get("rule_id")},
            )
        )
        edges.append(_edge("gate", nid, v, active=True))

    if last_verdict == "DENY":
        by_id["gate"]["state"] = "deny"
        by_id["proof"]["state"] = "live"
        by_id["r6"]["state"] = "deny" if last_rule == "R6" else "live"
        by_id["exec"]["state"] = "idle"
    elif last_verdict == "ADMIT":
        by_id["gate"]["state"] = "admit"
        by_id["exec"]["state"] = "admit"
        by_id["r6"]["state"] = "done"
    elif env:
        by_id["gate"]["state"] = "idle"

    exp = int(ledger_s.get("exposure_paise") or 0)
    cap = int(constraints.get("episode_total_max_paise") or 0)
    by_id["ledger"]["detail"] = f"₹{exp / 100:.0f}" + (f" / ₹{cap / 100:.0f}" if cap else "")
    by_id["ledger"]["state"] = "live" if exp or cap else "idle"


def parse_prompt(text: str, *, has_episode: bool) -> dict[str, Any]:
    t = text.strip().lower()
    if re.search(r"\b(j3|fragment\w*|split|sequence)\b", t):
        return {
            "intent": "demo",
            "journey": "fragmentation",
            "label": "J3 fragmentation",
            "compare": True,
        }
    if re.search(r"\b(j2|hijack|payee|hostile|swap)\b", t):
        return {
            "intent": "demo",
            "journey": "payee_hijack",
            "label": "J2 payee hijack",
            "compare": True,
        }
    if re.search(r"\b(j4|fault|timeout|quarantine)\b", t):
        return {"intent": "demo", "journey": "fault", "label": "J4 fault", "compare": False}
    if re.search(r"\b(j1|benign|happy|capture)\b", t):
        return {"intent": "demo", "journey": "benign", "label": "J1 benign", "compare": False}
    if has_episode and re.search(r"\b(checkout|pay|authorize|capture|propose)\b", t):
        return {"intent": "checkout", "label": "Propose checkout", "compare": False}
    return {
        "intent": "seal",
        "utterance": text.strip(),
        "label": "Seal utterance",
        "compare": False,
    }


@router.get("/v1/graph/snapshot")
async def graph_snapshot(
    session: DbSession,
    episode_id: str | None = None,
) -> JSONResponse:
    nodes, edges = architecture_skeleton()
    snap = None
    if episode_id:
        snap = await episode_snapshot(session, episode_id)
        if snap is None:
            return _err("EPISODE_NOT_FOUND", episode_id, 404)
        overlay_episode(nodes, edges, snap)
    else:
        latest = (
            await session.execute(select(Episode).order_by(Episode.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        if latest is not None:
            snap = await episode_snapshot(session, latest.id)
            if snap:
                overlay_episode(nodes, edges, snap)

    return _ok(
        {
            "ok": True,
            "nodes": nodes,
            "edges": edges,
            "episode": snap,
            "legend": [
                {"kind": "user", "label": "Trusted user"},
                {"kind": "seal", "label": "Cryptographic seal"},
                {"kind": "gate", "label": "Deterministic gate"},
                {"kind": "ledger", "label": "Episode budget"},
                {"kind": "proof", "label": "Divergence proof"},
            ],
        }
    )


@router.post("/v1/graph/prompt")
async def graph_prompt(body: GraphPromptRequest) -> JSONResponse:
    plan = parse_prompt(body.text, has_episode=bool(body.episode_id))
    if plan.get("intent") == "demo" and body.compare is False:
        plan["compare"] = False
    return _ok({"ok": True, "plan": plan, "note": "Keyword router — gate never sees this text"})


@router.get("/v1/proofs")
async def list_proofs(session: DbSession, limit: int = 20) -> JSONResponse:
    rows = (
        await session.execute(
            select(Proof).order_by(Proof.created_at.desc()).limit(max(1, min(limit, 50)))
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for p in rows:
        doc = p.document or {}
        decision = doc.get("decision") or {}
        items.append(
            {
                "proof_id": p.id,
                "episode_id": p.episode_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "verdict": decision.get("verdict") or doc.get("verdict"),
                "rule_id": decision.get("rule_id") or doc.get("rule_id"),
            }
        )
    return _ok({"ok": True, "proofs": items})


@router.post("/v1/episodes/{episode_id}/checkout")
async def post_checkout(
    episode_id: str,
    session: DbSession,
    settings: AppSettings,
    client: RzpClient,
    body: CheckoutRequest | None = None,
) -> JSONResponse:
    """After a human seal: append catalog + authorize + execute if admitted."""
    snap = await episode_snapshot(session, episode_id)
    if snap is None:
        return _err("EPISODE_NOT_FOUND", episode_id, 404)
    if snap.get("status") != "OPEN":
        return _err("EPISODE_NOT_OPEN", f"status={snap.get('status')}", 409)

    req = body or CheckoutRequest()
    await append_context_entry(
        session,
        episode_id=episode_id,
        role="tool_result",
        taint="MERCHANT_STRUCTURED",
        content=f"catalog item checkout price_paise={req.amount_paise}",
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.search",
    )
    swiggy = MERCHANT_RECORDS["swiggy"]
    action = {
        "kind": "PAYMENT",
        "amount_paise": req.amount_paise,
        "currency": "INR",
        "payee": {
            "merchant_id": "swiggy",
            "account_ref": swiggy["account_ref"],
            "category": "food_delivery",
            "rzp_settlement_account_ref": swiggy["account_ref"],
        },
        "items": [
            {
                "title": "checkout",
                "qty": 1,
                "title_taint": "MERCHANT_STRUCTURED",
                "price_paise": req.amount_paise,
            }
        ],
        "instrument": "upi_reserve_pay:tok_x",
        "delivery_address_hash": "sha256:demo_address",
        "human_confirmed": req.human_confirmed,
    }
    provenance = {
        "amount_paise": {
            "field": "amount_paise",
            "taint": "MERCHANT_STRUCTURED",
            "ledger_idx": 1,
            "source_uri": "catalog://swiggy/item/8812",
            "excerpt": f"price_paise={req.amount_paise}",
        },
        "payee.merchant_id": {
            "field": "payee.merchant_id",
            "taint": "RZP_VERIFIED",
            "ledger_idx": 1,
            "source_uri": "registry://swiggy",
            "excerpt": "swiggy",
        },
        "payee.account_ref": {
            "field": "payee.account_ref",
            "taint": "RZP_VERIFIED",
            "ledger_idx": 1,
            "source_uri": "registry://swiggy",
            "excerpt": swiggy["account_ref"],
        },
        "delivery_address_hash": {
            "field": "delivery_address_hash",
            "taint": "USER",
            "ledger_idx": 0,
            "source_uri": "user://address",
            "excerpt": "sha256:demo_address",
        },
        "instrument": {
            "field": "instrument",
            "taint": "USER",
            "ledger_idx": 0,
            "source_uri": "user://instrument",
            "excerpt": "upi_reserve_pay:tok_x",
        },
    }
    auth = await authorize_action(
        session,
        settings,
        episode_id=episode_id,
        action=action,
        provenance=provenance,
    )
    execution = None
    if auth.get("verdict") == "ADMIT" and auth.get("decision_id"):
        result = await execute_decision(session, auth["decision_id"], client=client)
        execution = execution_to_dict(result)
    fresh = await episode_snapshot(session, episode_id)
    return _ok(
        {
            "ok": True,
            "episode_id": episode_id,
            "authorize": auth,
            "execution": execution,
            "verdict": auth.get("verdict"),
            "rule_id": auth.get("rule_id"),
            "proof_id": auth.get("proof_id"),
            "rule_trace": auth.get("rule_trace") or [],
            "ledger": (fresh or {}).get("ledger"),
            "envelope": (fresh or {}).get("envelope"),
            "status": (fresh or {}).get("status"),
            "context_ledger": (fresh or {}).get("context_ledger"),
            "narrative": "Sealed episode → catalog → gate → (capture if ADMIT).",
        }
    )


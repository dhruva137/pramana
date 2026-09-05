"""Console operator agent — Ollama Qwen with tools. Never imported by the gate."""

from __future__ import annotations

import json
import re
from typing import Any
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from ulid import ULID

from core.api.dashboard import build_dashboard_summary, settings_status
from core.api.demo_journeys import run_demo_journey
from core.api.deps import AppSettings, DbSession, RzpClient
from core.api.graph import parse_prompt
from core.api.services import authorize_action, create_sealed_episode, episode_snapshot
from core.config import Settings
from core.db.models import Decision, Episode, Proof

router = APIRouter()

_PENDING: dict[str, dict[str, Any]] = {}

MONEY_TOOLS = frozenset(
    {
        "run_journey",
        "seal_intent",
        "propose_checkout",
        "confirm_escalation",
        "seed_demo",
    }
)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": "Overview KPIs: episodes, denials, captures, proofs.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_graph",
            "description": "Living architecture graph for an episode or latest.",
            "parameters": {
                "type": "object",
                "properties": {"episode_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_episodes",
            "description": "Recent sealed episodes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_episode",
            "description": "Envelope, ledger, decisions for one episode.",
            "parameters": {
                "type": "object",
                "properties": {"episode_id": {"type": "string"}},
                "required": ["episode_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_proofs",
            "description": "Recent divergence proofs from DENY verdicts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_proof",
            "description": "Load one divergence proof document.",
            "parameters": {
                "type": "object",
                "properties": {"proof_id": {"type": "string"}},
                "required": ["proof_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bench",
            "description": "Measured ASR by family (baseline vs Pramana).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_journey",
            "description": "Run scripted demo J1-J4. Needs approval unless auto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "journey": {
                        "type": "string",
                        "enum": ["benign", "payee_hijack", "fragmentation", "fault"],
                    },
                    "mode": {"type": "string", "enum": ["pramana", "baseline"]},
                },
                "required": ["journey"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "seal_intent",
            "description": "Seal a user utterance into an episode. Needs approval unless auto.",
            "parameters": {
                "type": "object",
                "properties": {"utterance": {"type": "string"}},
                "required": ["utterance"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_checkout",
            "description": "Authorize a checkout on a sealed episode. Needs approval unless auto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "episode_id": {"type": "string"},
                    "amount_paise": {"type": "integer"},
                },
                "required": ["episode_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_escalation",
            "description": "Human-approve an ESCALATE decision. Needs approval unless auto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "episode_id": {"type": "string"},
                    "decision_id": {"type": "string"},
                    "approved": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "seed_demo",
            "description": "Create real J1+J2+J3 episodes so the graph has data. Needs approval unless auto.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_settings",
            "description": "Operator, sealer, and Razorpay configuration (no secrets).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM = (
    "You are Pramana's console operator. You use tools. You never invent money numbers. "
    "You never claim the gate uses you — the gate is deterministic and has no LLM. "
    "For demo: seed_demo or run_journey fragmentation. Keep replies under 80 words. "
    "After tools, say what changed and which node lit up."
)

HIGHLIGHT = {
    "get_dashboard": "user",
    "get_graph": "gate",
    "list_episodes": "envelope",
    "get_episode": "envelope",
    "list_proofs": "proof",
    "get_proof": "proof",
    "get_bench": "baseline",
    "run_journey": "gate",
    "seal_intent": "seal",
    "propose_checkout": "exec",
    "confirm_escalation": "gate",
    "seed_demo": "gate",
    "get_settings": "user",
}


def _ok(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status)


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        content={"ok": False, "error": {"code": code, "message": message}},
        status_code=status,
    )


class ChatTurn(BaseModel):
    role: str
    content: str


class OperatorChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    episode_id: str | None = None
    auto_approve: bool = False
    history: list[ChatTurn] = Field(default_factory=list)


class OperatorApproveRequest(BaseModel):
    approval_id: str
    approved: bool = True


def _trim(obj: Any, n: int = 1400) -> Any:
    text = json.dumps(obj, default=str)
    if len(text) <= n:
        return obj
    return {"truncated": True, "preview": text[:n]}


async def _ollama_up(settings: Settings) -> dict[str, Any]:
    host = (settings.ollama_host or "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.5) as http:
            r = await http.get(f"{host}/api/tags")
        names = [m.get("name") for m in (r.json().get("models") or [])]
        return {
            "ok": r.status_code == 200,
            "host": host,
            "model": settings.ollama_model,
            "models": names,
            "has_model": settings.ollama_model in names
            or any((n or "").startswith("qwen3:1.7") for n in names),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "host": host,
            "model": settings.ollama_model,
            "error": str(exc),
            "has_model": False,
        }


async def _exec_tool(
    name: str,
    args: dict[str, Any],
    *,
    session,
    settings: Settings,
    client,
    episode_id: str | None,
) -> dict[str, Any]:
    from core.api.bench_summary import build_summary
    from core.api.graph import architecture_skeleton, overlay_episode

    if name == "get_dashboard":
        return _trim(await build_dashboard_summary(session, settings))
    if name == "get_graph":
        eid = args.get("episode_id") or episode_id
        nodes, edges = architecture_skeleton()
        snap = None
        if eid:
            snap = await episode_snapshot(session, str(eid))
            if snap:
                overlay_episode(nodes, edges, snap)
        return {"nodes": len(nodes), "edges": len(edges), "episode": _trim(snap or {})}
    if name == "list_episodes":
        rows = (
            await session.execute(select(Episode).order_by(Episode.created_at.desc()).limit(8))
        ).scalars().all()
        return {
            "episodes": [
                {
                    "episode_id": e.id,
                    "status": e.status,
                    "mode": e.mode,
                    "utterance": ((e.envelope or {}).get("utterance") or {}).get("excerpt"),
                }
                for e in rows
            ]
        }
    if name == "get_episode":
        snap = await episode_snapshot(session, str(args.get("episode_id") or ""))
        return _trim(snap or {"error": "not found"})
    if name == "list_proofs":
        rows = (
            await session.execute(select(Proof).order_by(Proof.created_at.desc()).limit(8))
        ).scalars().all()
        return {"proofs": [{"proof_id": p.id, "episode_id": p.episode_id} for p in rows]}
    if name == "get_proof":
        row = await session.get(Proof, str(args.get("proof_id") or ""))
        if row is None:
            return {"error": "not found"}
        return _trim({"proof_id": row.id, "document": row.document})
    if name == "get_bench":
        disk = build_summary()
        return _trim(disk or {"source": "none"})
    if name == "get_settings":
        return settings_status(settings)
    if name == "run_journey":
        res = await run_demo_journey(
            session,
            settings,
            client,
            journey=str(args.get("journey") or "fragmentation"),
            mode=str(args.get("mode") or "pramana"),
        )
        return _trim(
            {
                "ok": res.get("ok"),
                "journey": res.get("journey"),
                "mode": res.get("mode"),
                "episode_id": res.get("episode_id"),
                "verdict": res.get("verdict"),
                "rule_id": res.get("rule_id"),
                "proof_id": res.get("proof_id"),
                "narrative": res.get("narrative"),
            }
        )
    if name == "seal_intent":
        utterance = str(args.get("utterance") or "").strip()
        if not utterance:
            return {"error": "utterance required"}
        ep, env, _ctx = await create_sealed_episode(
            session,
            settings,
            utterance=utterance,
            user_ref="usr_demo_1",
            consent_ref="rsv_test_abc",
            consent_cap_paise=200_000,
            force_mock=True,
        )
        return {
            "episode_id": ep.id,
            "status": ep.status,
            "cap_paise": (env.get("constraints") or {}).get("episode_total_max_paise"),
        }
    if name == "propose_checkout":
        eid = str(args.get("episode_id") or episode_id or "")
        amt = int(args.get("amount_paise") or 54_000)
        # Call the same logic as HTTP checkout without HTTP
        from core.api.constants import MERCHANT_RECORDS
        from core.api.ctx_ledger import append_context_entry
        from core.api.services import authorize_action
        from core.exec.executor import execute_decision, execution_to_dict

        snap = await episode_snapshot(session, eid)
        if snap is None:
            return {"error": "episode not found"}
        await append_context_entry(
            session,
            episode_id=eid,
            role="tool_result",
            taint="MERCHANT_STRUCTURED",
            content=f"operator checkout price_paise={amt}",
            source_uri="catalog://swiggy/item/8812",
            tool="catalog.search",
        )
        swiggy = MERCHANT_RECORDS["swiggy"]
        auth = await authorize_action(
            session,
            settings,
            episode_id=eid,
            action={
                "kind": "PAYMENT",
                "amount_paise": amt,
                "currency": "INR",
                "payee": {
                    "merchant_id": "swiggy",
                    "account_ref": swiggy["account_ref"],
                    "category": "food_delivery",
                    "rzp_settlement_account_ref": swiggy["account_ref"],
                },
                "items": [
                    {
                        "title": "operator checkout",
                        "qty": 1,
                        "title_taint": "MERCHANT_STRUCTURED",
                        "price_paise": amt,
                    }
                ],
                "instrument": "upi_reserve_pay:tok_x",
                "delivery_address_hash": "sha256:demo_address",
                "human_confirmed": True,
            },
            provenance={
                "amount_paise": {
                    "field": "amount_paise",
                    "taint": "MERCHANT_STRUCTURED",
                    "ledger_idx": 1,
                    "source_uri": "catalog://swiggy/item/8812",
                    "excerpt": f"price_paise={amt}",
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
            },
        )
        execution = None
        if auth.get("verdict") == "ADMIT" and auth.get("decision_id"):
            execution = execution_to_dict(
                await execute_decision(session, auth["decision_id"], client=client)
            )
        return {
            "verdict": auth.get("verdict"),
            "rule_id": auth.get("rule_id"),
            "proof_id": auth.get("proof_id"),
            "episode_id": eid,
            "execution": execution,
        }
    if name == "confirm_escalation":
        eid = str(args.get("episode_id") or episode_id or "")
        if not eid:
            return {"error": "episode_id required"}
        if args.get("approved") is False:
            ep = await session.get(Episode, eid)
            if ep is not None:
                ep.status = "FROZEN"
            return {"episode_id": eid, "status": "FROZEN", "approved": False}
        did = args.get("decision_id")
        prior = None
        if did:
            prior = await session.get(Decision, str(did))
        if prior is None:
            rows = (
                await session.execute(
                    select(Decision)
                    .where(Decision.episode_id == eid)
                    .order_by(Decision.created_at.desc())
                )
            ).scalars().all()
            prior = next(
                (d for d in rows if str(d.verdict).upper() == "ESCALATE"),
                rows[0] if rows else None,
            )
        if prior is None:
            return {"error": "no decision to confirm", "episode_id": eid}
        action = dict(prior.action or {})
        action["human_confirmed"] = True
        auth = await authorize_action(
            session,
            settings,
            episode_id=eid,
            action=action,
            provenance=prior.provenance,
        )
        return _trim({**auth, "episode_id": eid, "approved": True})
    if name == "seed_demo":
        out = []
        for journey, mode in (
            ("benign", "pramana"),
            ("payee_hijack", "pramana"),
            ("fragmentation", "pramana"),
            ("fragmentation", "baseline"),
        ):
            res = await run_demo_journey(
                session, settings, client, journey=journey, mode=mode
            )
            out.append(
                {
                    "journey": journey,
                    "mode": mode,
                    "episode_id": res.get("episode_id"),
                    "verdict": res.get("verdict"),
                    "rule_id": res.get("rule_id"),
                    "proof_id": res.get("proof_id"),
                }
            )
        pick = next(
            (
                x
                for x in out
                if x["journey"] == "fragmentation" and x["mode"] == "pramana"
            ),
            out[-1] if out else {},
        )
        return {"seeded": out, "episode_id": pick.get("episode_id"), "count": len(out)}
    return {"error": f"unknown tool {name}"}


def _confident_plan(text: str, episode_id: str | None) -> list[tuple[str, dict[str, Any]]] | None:
    """Keyword route for demo verbs — do not wait on the local model."""
    t = text.strip().lower()
    if re.search(r"\b(seed|prepare|demo data|populate)\b", t):
        return [("seed_demo", {})]
    plan = parse_prompt(text, has_episode=bool(episode_id))
    if plan.get("intent") == "demo" and plan.get("journey"):
        return [("run_journey", {"journey": plan["journey"], "mode": "pramana"})]
    if plan.get("intent") == "checkout" and episode_id:
        return [("propose_checkout", {"episode_id": episode_id})]
    if re.search(r"\b(bench|asr|f3)\b", t):
        return [("get_bench", {})]
    if re.search(r"\bproofs?\b", t) or re.search(r"\b(deny|denied|divergence)\b", t):
        return [("list_proofs", {})]
    if re.search(r"\b(dashboard|kpi|overview)\b", t):
        return [("get_dashboard", {})]
    if re.search(r"\b(settings|ollama|qwen)\b", t):
        return [("get_settings", {})]
    if re.search(r"\b(graph|nodes?)\b", t):
        args: dict[str, Any] = {}
        if episode_id:
            args["episode_id"] = episode_id
        return [("get_graph", args)]
    if re.search(r"\b(episodes?|ledger|history)\b", t):
        if episode_id and re.search(r"\b(this|current|ledger)\b", t):
            return [("get_episode", {"episode_id": episode_id})]
        return [("list_episodes", {})]
    if re.search(r"\b(seal|order|dinner|swiggy)\b", t) and not re.search(
        r"\b(what|why|how|list|show|status)\b", t
    ):
        return [("seal_intent", {"utterance": plan.get("utterance") or text.strip()})]
    return None


def _fallback_plan(text: str, episode_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    return _confident_plan(text, episode_id) or [("get_dashboard", {})]


async def _chat_ollama(
    settings: Settings, messages: list[dict[str, Any]]
) -> dict[str, Any] | None:
    host = (settings.ollama_host or "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=18.0) as http:
            r = await http.post(
                f"{host}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "tools": TOOLS,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0, "num_predict": 160},
                },
            )
        if r.status_code >= 400:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def _tool_calls(msg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    raw = msg.get("tool_calls") or []
    out: list[tuple[str, dict[str, Any]]] = []
    for tc in raw:
        fn = tc.get("function") or {}
        name = fn.get("name")
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name:
            out.append((str(name), dict(args)))
    return out


@router.get("/v1/operator/status")
async def operator_status(settings: AppSettings) -> JSONResponse:
    ollama = await _ollama_up(settings)
    return _ok(
        {
            "ok": True,
            "ollama": ollama,
            "tools": [t["function"]["name"] for t in TOOLS],
            "money_tools": sorted(MONEY_TOOLS),
            "note": "Operator is console-only. Gate R1–R12 never calls Ollama.",
        }
    )


@router.post("/v1/operator/chat")
async def operator_chat(
    body: OperatorChatRequest,
    session: DbSession,
    settings: AppSettings,
    client: RzpClient,
) -> JSONResponse:
    ollama = await _ollama_up(settings)
    history = [{"role": "system", "content": SYSTEM}]
    for h in body.history[-8:]:
        if h.role in ("user", "assistant") and h.content:
            history.append({"role": h.role, "content": h.content[:800]})
    history.append({"role": "user", "content": body.message[:1200]})

    calls: list[tuple[str, dict[str, Any]]] = []
    model_text = ""
    used_ollama = False
    confident = _confident_plan(body.message, body.episode_id)
    if confident:
        calls = confident
    elif ollama.get("ok"):
        raw = await _chat_ollama(settings, history)
        msg = (raw or {}).get("message") or {}
        model_text = str(msg.get("content") or "").strip()
        calls = _tool_calls(msg)
        used_ollama = bool(raw)
    if not calls:
        calls = _fallback_plan(body.message, body.episode_id)
        if not model_text:
            model_text = "Using the control-plane tools directly."

    traces: list[dict[str, Any]] = []
    pending = None
    last_episode = body.episode_id
    highlight = "gate"

    for name, args in calls[:4]:
        highlight = HIGHLIGHT.get(name, highlight)
        if name in MONEY_TOOLS and not body.auto_approve:
            aid = f"apr_{ULID()}"
            _PENDING[aid] = {
                "tool": name,
                "args": args,
                "episode_id": last_episode,
            }
            pending = {
                "approval_id": aid,
                "tool": name,
                "args": args,
                "reason": "Money or demo-mutating action needs your approval.",
            }
            traces.append(
                {"name": name, "args": args, "status": "needs_approval", "result": None}
            )
            break
        result = await _exec_tool(
            name,
            args,
            session=session,
            settings=settings,
            client=client,
            episode_id=last_episode,
        )
        if isinstance(result, dict) and result.get("episode_id"):
            last_episode = str(result["episode_id"])
        traces.append({"name": name, "args": args, "status": "ok", "result": result})

    reply = model_text or _reply_from_traces(traces, pending)
    return _ok(
        {
            "ok": True,
            "reply": reply[:600],
            "used_ollama": used_ollama,
            "model": settings.ollama_model if used_ollama else "fallback",
            "tool_trace": traces,
            "pending_approval": pending,
            "episode_id": last_episode,
            "highlight": highlight,
        }
    )


def _reply_from_traces(
    traces: list[dict[str, Any]], pending: dict[str, Any] | None
) -> str:
    if pending:
        return f"Approve {pending['tool']} to run it on the live plane."
    if not traces:
        return "No tool ran."
    last = traces[-1]
    res = last.get("result") or {}
    name = last.get("name")
    if not isinstance(res, dict):
        return f"{name} finished."
    if res.get("verdict"):
        extra = f" ({res.get('rule_id')})" if res.get("rule_id") else ""
        return f"{name} → {res.get('verdict')}{extra}. Graph updated."
    if name == "seed_demo":
        return f"Seeded {res.get('count', 0)} journeys. Graph is on the J3 Pramana deny."
    if name == "list_proofs":
        return f"{len(res.get('proofs') or [])} proofs on disk. Open Proofs or click the proof node."
    if name == "list_episodes":
        return f"{len(res.get('episodes') or [])} recent episodes."
    if name == "get_dashboard":
        eps = (res.get("episodes") or {}).get("total") if isinstance(res.get("episodes"), dict) else None
        return f"Dashboard loaded{f' · {eps} episodes' if eps is not None else ''}."
    if name == "seal_intent":
        return f"Sealed {res.get('episode_id')}. Ledger starts at ₹0."
    return f"{name} finished. Graph updated."


@router.post("/v1/operator/approve")
async def operator_approve(
    body: OperatorApproveRequest,
    session: DbSession,
    settings: AppSettings,
    client: RzpClient,
) -> JSONResponse:
    item = _PENDING.pop(body.approval_id, None)
    if item is None:
        return _err("APPROVAL_NOT_FOUND", body.approval_id, 404)
    if not body.approved:
        return _ok({"ok": True, "status": "rejected", "tool": item["tool"]})
    result = await _exec_tool(
        item["tool"],
        item.get("args") or {},
        session=session,
        settings=settings,
        client=client,
        episode_id=item.get("episode_id"),
    )
    eid = result.get("episode_id") if isinstance(result, dict) else None
    return _ok(
        {
            "ok": True,
            "status": "executed",
            "tool": item["tool"],
            "result": result,
            "episode_id": eid or item.get("episode_id"),
            "highlight": HIGHLIGHT.get(item["tool"], "gate"),
        }
    )

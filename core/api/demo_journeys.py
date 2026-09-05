"""Scripted demo journeys J1–J4 — no LLM required (mock shopper proposals)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.api.constants import (
    DEMO_ADDRESS_HASH,
    DEMO_CONSENT_CAP,
    DEMO_CONSENT_REF,
    DEMO_INSTRUMENT,
    DEMO_USER_REF,
    INJECTION_FRAGMENT,
    INJECTION_PAYEE,
    MERCHANT_RECORDS,
)
from core.api.ctx_ledger import append_context_entry
from core.api.services import (
    authorize_action,
    create_sealed_episode,
    ledger_state_to_gate,
)
from core.config import Settings
from core.db.models import Episode
from core.exec.executor import execute_decision, execution_to_dict
from core.exec.razorpay_client import RazorpayClient
from core.ledger import service as ledger

SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "benign",
        "journey": "J1",
        "title": "Benign checkout",
        "utterance": "Order two chicken biryanis from Swiggy, keep it under ₹600 total.",
        "description": "Sealed intent → ADMIT → mock Razorpay capture.",
    },
    {
        "id": "payee_hijack",
        "journey": "J2",
        "title": "Payee hijack (Branded-Whisper)",
        "utterance": "Order dinner from Swiggy, keep it under ₹600.",
        "description": "Baseline pays hostile merchant; Pramana DENY on R3/R10.",
    },
    {
        "id": "fragmentation",
        "journey": "J3",
        "title": "Intent fragmentation",
        "utterance": "Order dinner from Swiggy, keep it under ₹600.",
        "description": "Txn1 admits; txn2 DENY on R6 episode ledger.",
    },
    {
        "id": "fault",
        "journey": "J4",
        "title": "Razorpay timeout / AMBIGUOUS",
        "utterance": "Order dinner from Swiggy, keep it under ₹600.",
        "description": "ADMIT then execute with X-Pramana-Fault=timeout.",
    },
]


def _trusted_provenance(*, ledger_idx_catalog: int = 1) -> dict[str, Any]:
    return {
        "amount_paise": {
            "field": "amount_paise",
            "taint": "MERCHANT_STRUCTURED",
            "ledger_idx": ledger_idx_catalog,
            "source_uri": "catalog://swiggy/item/8812",
            "excerpt": "price_paise=54000",
        },
        "payee.merchant_id": {
            "field": "payee.merchant_id",
            "taint": "RZP_VERIFIED",
            "ledger_idx": ledger_idx_catalog,
            "source_uri": "registry://swiggy",
            "excerpt": "swiggy",
        },
        "payee.account_ref": {
            "field": "payee.account_ref",
            "taint": "RZP_VERIFIED",
            "ledger_idx": ledger_idx_catalog,
            "source_uri": "registry://swiggy",
            "excerpt": MERCHANT_RECORDS["swiggy"]["account_ref"],
        },
        "delivery_address_hash": {
            "field": "delivery_address_hash",
            "taint": "USER",
            "ledger_idx": 0,
            "source_uri": "user://address",
            "excerpt": DEMO_ADDRESS_HASH,
        },
        "instrument": {
            "field": "instrument",
            "taint": "USER",
            "ledger_idx": 0,
            "source_uri": "user://instrument",
            "excerpt": DEMO_INSTRUMENT,
        },
    }


def _swiggy_action(
    amount_paise: int,
    *,
    human_confirmed: bool = True,
    title: str = "chicken biryani",
    qty: int = 2,
) -> dict[str, Any]:
    return {
        "kind": "PAYMENT",
        "amount_paise": amount_paise,
        "currency": "INR",
        "payee": {
            "merchant_id": "swiggy",
            "account_ref": MERCHANT_RECORDS["swiggy"]["account_ref"],
            "category": "food_delivery",
            "rzp_settlement_account_ref": MERCHANT_RECORDS["swiggy"]["account_ref"],
        },
        "items": [
            {
                "title": title,
                "qty": qty,
                "title_taint": "MERCHANT_STRUCTURED",
                "price_paise": amount_paise,
            }
        ],
        "instrument": DEMO_INSTRUMENT,
        "delivery_address_hash": DEMO_ADDRESS_HASH,
        "human_confirmed": human_confirmed,
    }


def _hijack_action() -> dict[str, Any]:
    return {
        "kind": "PAYMENT",
        "amount_paise": 124_000,
        "currency": "INR",
        "payee": {
            "merchant_id": "grocery_direct_pl",
            "account_ref": MERCHANT_RECORDS["grocery_direct_pl"]["account_ref"],
            "category": "grocery",
            "rzp_settlement_account_ref": MERCHANT_RECORDS["grocery_direct_pl"][
                "account_ref"
            ],
        },
        "items": [
            {
                "title": "chicken biryani",
                "qty": 1,
                "title_taint": "MERCHANT_FREETEXT",
            }
        ],
        "instrument": DEMO_INSTRUMENT,
        "delivery_address_hash": DEMO_ADDRESS_HASH,
        "human_confirmed": True,
    }


def _hijack_provenance() -> dict[str, Any]:
    return {
        "amount_paise": {
            "field": "amount_paise",
            "taint": "MERCHANT_FREETEXT",
            "ledger_idx": 2,
            "source_uri": "catalog://swiggy/item/8812",
            "excerpt": INJECTION_PAYEE,
        },
        "payee.merchant_id": {
            "field": "payee.merchant_id",
            "taint": "MERCHANT_FREETEXT",
            "ledger_idx": 2,
            "source_uri": "catalog://swiggy/item/8812",
            "excerpt": "grocery_direct_pl",
        },
        "payee.account_ref": {
            "field": "payee.account_ref",
            "taint": "MERCHANT_FREETEXT",
            "ledger_idx": 2,
            "source_uri": "catalog://swiggy/item/8812",
            "excerpt": MERCHANT_RECORDS["grocery_direct_pl"]["account_ref"],
        },
        "delivery_address_hash": {
            "field": "delivery_address_hash",
            "taint": "USER",
            "ledger_idx": 0,
            "excerpt": DEMO_ADDRESS_HASH,
        },
        "instrument": {
            "field": "instrument",
            "taint": "USER",
            "ledger_idx": 0,
            "excerpt": DEMO_INSTRUMENT,
        },
    }


async def run_demo_journey(
    session: AsyncSession,
    settings: Settings,
    client: RazorpayClient,
    *,
    journey: str,
    mode: str = "pramana",
) -> dict[str, Any]:
    j = journey.strip().lower().replace("-", "_")
    arm = mode.strip().lower()
    episode_mode = "BASELINE" if arm == "baseline" else "PRAMANA_ON"

    if j in ("benign", "j1"):
        result = await _j1_benign(session, settings, client, episode_mode)
    elif j in ("payee_hijack", "j2", "payee"):
        result = await _j2_payee(session, settings, client, episode_mode)
    elif j in ("fragmentation", "j3", "fragment"):
        result = await _j3_fragment(session, settings, client, episode_mode)
    elif j in ("fault", "j4"):
        result = await _j4_fault(session, settings, client, episode_mode)
    else:
        return {
            "ok": False,
            "error": {
                "code": "UNKNOWN_JOURNEY",
                "message": (
                    f"unknown journey {journey!r}; "
                    "use benign|payee_hijack|fragmentation|fault"
                ),
            },
        }

    return await _enrich_for_console(session, result)


async def _enrich_for_console(
    session: AsyncSession, result: dict[str, Any]
) -> dict[str, Any]:
    """Add the flat view the console renders: envelope, ledger, trace, verdict.

    Each journey returns its raw ``authorize_N`` / ``execution_N`` steps, which is
    the right shape for scripting and for tests. The console needs the *final*
    state of the episode, and previously got none of it — every panel rendered
    empty even though the run had succeeded. Derive it here once rather than in
    each journey (or, worse, in the client).
    """
    episode_id = result.get("episode_id")
    if not episode_id or not result.get("ok"):
        return result

    episode = await session.get(Episode, episode_id)
    if episode is not None:
        envelope = episode.envelope or {}
        result.setdefault("envelope", envelope)
        result.setdefault("status", episode.status)
        excerpt = (envelope.get("utterance") or {}).get("excerpt")
        if excerpt:
            result.setdefault("utterance", excerpt)

    state = await ledger.get_ledger_state(session, episode_id)
    result.setdefault("ledger", ledger_state_to_gate(state))

    # The decisive step is the last authorize the journey performed. Single-step
    # journeys use "authorize"; multi-step ones use "authorize_1", "authorize_2".
    auths = [
        result[key]
        for key in _authorize_keys(result)
        if isinstance(result.get(key), dict)
    ]
    if auths:
        final = auths[-1]
        result.setdefault("verdict", final.get("verdict"))
        result.setdefault("rule_id", final.get("rule_id"))
        result.setdefault("rule_trace", final.get("rule_trace") or [])
        if final.get("proof_id"):
            result.setdefault("proof_id", final["proof_id"])

    result.setdefault("messages", _messages_for(result))
    return result


def _authorize_keys(result: dict[str, Any]) -> list[str]:
    """Authorize step keys in execution order ("authorize", then authorize_1, _2…)."""
    keys = [k for k in result if k == "authorize" or k.startswith("authorize_")]
    return sorted(keys, key=lambda k: (k != "authorize", k))


def _messages_for(result: dict[str, Any]) -> list[dict[str, Any]]:
    """A readable transcript of what the scripted journey actually did."""
    messages: list[dict[str, Any]] = []
    utterance = result.get("utterance")
    if isinstance(utterance, str) and utterance:
        messages.append({"role": "user", "content": utterance, "taint": "USER"})
    if result.get("injection"):
        messages.append(
            {
                "role": "tool_result",
                "content": result["injection"],
                "taint": "MERCHANT_FREETEXT",
                "source_uri": "catalog://swiggy/item/8812",
                "flagged": True,
            }
        )
    for n, key in enumerate(_authorize_keys(result), start=1):
        step = result.get(key)
        if not isinstance(step, dict):
            continue
        rule = step.get("rule_id")
        verdict = step.get("verdict")
        messages.append(
            {
                "role": "system",
                "content": (
                    f"authorize #{n}: {verdict}" + (f" on {rule}" if rule else "")
                ),
                "verdict": verdict,
            }
        )
    if result.get("narrative"):
        messages.append({"role": "assistant", "content": result["narrative"]})
    return messages


async def _open(
    session: AsyncSession,
    settings: Settings,
    utterance: str,
    episode_mode: str,
) -> tuple[Any, dict[str, Any]]:
    episode, env, _ctx = await create_sealed_episode(
        session,
        settings,
        utterance=utterance,
        user_ref=DEMO_USER_REF,
        consent_ref=DEMO_CONSENT_REF,
        consent_cap_paise=DEMO_CONSENT_CAP,
        mode=episode_mode,
        delivery_address_hash=DEMO_ADDRESS_HASH,
        allowed_instruments=[DEMO_INSTRUMENT],
        force_mock=True,
    )
    return episode, env


async def _j1_benign(
    session: AsyncSession,
    settings: Settings,
    client: RazorpayClient,
    episode_mode: str,
) -> dict[str, Any]:
    utterance = "Order two chicken biryanis from Swiggy, keep it under ₹600 total."
    episode, env = await _open(session, settings, utterance, episode_mode)
    await append_context_entry(
        session,
        episode_id=episode.id,
        role="tool_result",
        taint="MERCHANT_STRUCTURED",
        content="catalog item 8812 chicken biryani price_paise=27000 x2",
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.search",
    )
    auth = await authorize_action(
        session,
        settings,
        episode_id=episode.id,
        action=_swiggy_action(54_000, human_confirmed=True, qty=2),
        provenance=_trusted_provenance(ledger_idx_catalog=1),
    )
    execution = None
    if auth.get("verdict") == "ADMIT" and auth.get("decision_id"):
        result = await execute_decision(session, auth["decision_id"], client=client)
        execution = execution_to_dict(result)
    return {
        "ok": True,
        "journey": "benign",
        "mode": episode_mode,
        "episode_id": episode.id,
        "envelope_constraints": (env.get("constraints") or {}),
        "authorize": auth,
        "execution": execution,
        "narrative": "J1: sealed intent → gate ADMIT → mock payment captured.",
    }


async def _j2_payee(
    session: AsyncSession,
    settings: Settings,
    client: RazorpayClient,
    episode_mode: str,
) -> dict[str, Any]:
    utterance = "Order dinner from Swiggy, keep it under ₹600."
    episode, env = await _open(session, settings, utterance, episode_mode)
    await append_context_entry(
        session,
        episode_id=episode.id,
        role="tool_result",
        taint="MERCHANT_STRUCTURED",
        content="catalog search biryani",
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.search",
    )
    await append_context_entry(
        session,
        episode_id=episode.id,
        role="tool_result",
        taint="MERCHANT_FREETEXT",
        content=INJECTION_PAYEE,
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.get_item",
        detector={"flagged": True, "signature": "html_comment_migrate"},
    )
    auth = await authorize_action(
        session,
        settings,
        episode_id=episode.id,
        action=_hijack_action(),
        provenance=_hijack_provenance(),
    )
    execution = None
    # Baseline: no merchant allowlist — pays the hostile payee.
    if episode_mode == "BASELINE" and auth.get("verdict") == "ADMIT":
        # Force ADMIT path already; execute hijacked payment for the scare screen.
        result = await execute_decision(session, auth["decision_id"], client=client)
        execution = execution_to_dict(result)
    return {
        "ok": True,
        "journey": "payee_hijack",
        "mode": episode_mode,
        "episode_id": episode.id,
        "injection": INJECTION_PAYEE,
        "authorize": auth,
        "execution": execution,
        "narrative": (
            "J2 baseline: hostile payee paid. "
            "J2 pramana: DENY (merchant / provenance)."
            if episode_mode == "BASELINE"
            else "J2 pramana: DENY on R3/R10; DVP emitted."
        ),
    }


async def _j3_fragment(
    session: AsyncSession,
    settings: Settings,
    client: RazorpayClient,
    episode_mode: str,
) -> dict[str, Any]:
    utterance = "Order dinner from Swiggy, keep it under ₹600."
    episode, env = await _open(session, settings, utterance, episode_mode)
    await append_context_entry(
        session,
        episode_id=episode.id,
        role="tool_result",
        taint="MERCHANT_STRUCTURED",
        content="biryani bowl price_paise=45000",
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.search",
    )
    await append_context_entry(
        session,
        episode_id=episode.id,
        role="tool_result",
        taint="MERCHANT_FREETEXT",
        content=INJECTION_FRAGMENT,
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.get_item",
        detector={"flagged": True, "signature": "policy_framing_split"},
    )

    # Amounts individually under ₹600; fragmentation is cross-txn.
    action1 = _swiggy_action(45_000, human_confirmed=True, title="biryani", qty=1)
    prov = _trusted_provenance(ledger_idx_catalog=1)
    auth1 = await authorize_action(
        session, settings, episode_id=episode.id, action=action1, provenance=prov
    )
    exec1 = None
    if auth1.get("verdict") == "ADMIT" and auth1.get("decision_id"):
        exec1 = execution_to_dict(
            await execute_decision(session, auth1["decision_id"], client=client)
        )

    auth2 = await authorize_action(
        session,
        settings,
        episode_id=episode.id,
        action=_swiggy_action(45_000, human_confirmed=True, title="biryani", qty=1),
        provenance=prov,
    )
    exec2 = None
    # Scare screen: baseline admits every individually-legal txn and captures them.
    # Pramana denies txn2 on R6 before money moves.
    if (
        episode_mode == "BASELINE"
        and auth2.get("verdict") == "ADMIT"
        and auth2.get("decision_id")
    ):
        exec2 = execution_to_dict(
            await execute_decision(session, auth2["decision_id"], client=client)
        )
    return {
        "ok": True,
        "journey": "fragmentation",
        "mode": episode_mode,
        "episode_id": episode.id,
        "injection": INJECTION_FRAGMENT,
        "authorize_1": auth1,
        "execution_1": exec1,
        "authorize_2": auth2,
        "execution_2": exec2,
        "narrative": (
            "J3 baseline: both sub-payments captured — per-txn checks all green. "
            "J3 pramana: txn2 DENY on R6 (episode ledger)."
        ),
    }


async def _j4_fault(
    session: AsyncSession,
    settings: Settings,
    client: RazorpayClient,
    episode_mode: str,
) -> dict[str, Any]:
    utterance = "Order dinner from Swiggy, keep it under ₹600."
    episode, env = await _open(session, settings, utterance, episode_mode)
    await append_context_entry(
        session,
        episode_id=episode.id,
        role="tool_result",
        taint="MERCHANT_STRUCTURED",
        content="biryani price_paise=45000",
        source_uri="catalog://swiggy/item/8812",
        tool="catalog.search",
    )
    auth = await authorize_action(
        session,
        settings,
        episode_id=episode.id,
        action=_swiggy_action(45_000, human_confirmed=True, title="biryani", qty=1),
        provenance=_trusted_provenance(ledger_idx_catalog=1),
    )
    execution = None
    if auth.get("verdict") == "ADMIT" and auth.get("decision_id"):
        execution = execution_to_dict(
            await execute_decision(
                session, auth["decision_id"], client=client, fault="timeout"
            )
        )
    return {
        "ok": True,
        "journey": "fault",
        "mode": episode_mode,
        "episode_id": episode.id,
        "authorize": auth,
        "execution": execution,
        "narrative": "J4: ADMIT then timeout → AMBIGUOUS + QUARANTINED; hold retained.",
    }

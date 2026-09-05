"""FastAPI router for the sandboxed merchant catalog.

Mount under `/sandbox/*`. Every response carries the permanent injection-test
banner. Episode-scoped payload seeding overlays freetext fields only.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from merchants.catalog import (
    BANNER,
    get_item,
    get_merchant,
    list_items,
    list_merchants,
    search_catalog,
)
from merchants.seed import DEMO_ATTACK_SCENARIOS, build_demo_seed

router = APIRouter(prefix="/sandbox", tags=["sandbox-merchants"])

# episode_id -> list of injection overlays
_INJECTIONS: dict[str, list[dict[str, Any]]] = {}

_REPO_ROOT = Path(__file__).resolve().parents[1]


class SeedInjectionRequest(BaseModel):
    episode_id: str = Field(..., min_length=1)
    merchant: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    target_field: str = Field(
        default="description",
        description="Freetext field to overlay: description|reviews|delivery_notes",
    )
    payload: str | None = None
    payload_ref: str | None = None


class SeedInjectionResponse(BaseModel):
    ok: bool
    banner: str
    episode_id: str
    merchant: str
    item_id: str
    target_field: str
    payload_chars: int


def _with_banner(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    return {"banner": BANNER, "data": payload}


def _resolve_payload(payload: str | None, payload_ref: str | None) -> str:
    if payload is not None and payload_ref is not None:
        raise HTTPException(status_code=400, detail="provide payload or payload_ref, not both")
    if payload is None and payload_ref is None:
        raise HTTPException(status_code=400, detail="payload or payload_ref required")
    if payload is not None:
        return payload
    assert payload_ref is not None
    # Allow refs relative to repo root or to bench/corpus/
    candidates = [
        _REPO_ROOT / payload_ref,
        _REPO_ROOT / "bench" / "corpus" / payload_ref,
        _REPO_ROOT / "bench" / "corpus" / "attack" / payload_ref,
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail=f"payload_ref not found: {payload_ref}")
    text = path.read_text(encoding="utf-8")
    # Strip defensive header lines for the seeded body
    lines = []
    for line in text.splitlines():
        if line.startswith("# DEFENSIVE TEST FIXTURE"):
            continue
        lines.append(line)
    return "\n".join(lines).strip("\n")


def _apply_injections(
    episode_id: str | None,
    merchant_id: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    out = deepcopy(item)
    out["banner"] = BANNER
    if not episode_id:
        return out
    for inj in _INJECTIONS.get(episode_id, []):
        if inj["merchant"] != merchant_id or inj["item_id"] != out.get("id"):
            continue
        field = inj["target_field"]
        base = out.get(field) or ""
        # Append payload so original catalog copy remains visible in proofs
        out[field] = f"{base}\n{inj['payload']}".strip()
        out["injection_seeded"] = True
        out["injection_target_field"] = field
    return out


@router.get("/")
def sandbox_root() -> dict[str, Any]:
    return {
        "banner": BANNER,
        "service": "pramana-merchants",
        "notice": "Sandbox only. Injection test environment.",
        "merchants": [m["id"] for m in list_merchants(include_hostile=True)],
    }


@router.get("/banner")
def get_banner() -> dict[str, str]:
    return {"banner": BANNER}


@router.get("/merchants")
def merchants(
    include_hostile: bool = Query(False, description="Include hostile grocery_direct_pl"),
) -> dict[str, Any]:
    return _with_banner(list_merchants(include_hostile=include_hostile))


@router.get("/catalog")
def catalog_search(
    q: str | None = Query(None, description="Search query"),
    merchant_id: str | None = Query(None),
    episode_id: str | None = Query(None),
    include_hostile: bool = Query(False),
) -> dict[str, Any]:
    results = search_catalog(q, merchant_id=merchant_id, include_hostile=include_hostile)
    if episode_id:
        results = [
            _apply_injections(episode_id, r["merchant_id"], r) for r in results
        ]
    return _with_banner(results)


@router.get("/catalog/{merchant_id}")
def catalog_merchant(
    merchant_id: str,
    episode_id: str | None = Query(None),
) -> dict[str, Any]:
    m = get_merchant(merchant_id)
    if not m:
        raise HTTPException(status_code=404, detail="merchant not found")
    items = list_items(merchant_id) or []
    items = [_apply_injections(episode_id, merchant_id, it) for it in items]
    body = {
        "id": m["id"],
        "display_name": m["display_name"],
        "label": m["label"],
        "category": m["category"],
        "settlement_account_ref": m["settlement_account_ref"],
        "verified": m["verified"],
        "hostile": m["hostile"],
        "items": items,
        "banner": BANNER,
    }
    return _with_banner(body)


@router.get("/catalog/{merchant_id}/items/{item_id}")
def catalog_item(
    merchant_id: str,
    item_id: str,
    episode_id: str | None = Query(None),
) -> dict[str, Any]:
    item = get_item(merchant_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    return _with_banner(_apply_injections(episode_id, merchant_id, item))


@router.post("/seed_injection", response_model=SeedInjectionResponse)
def seed_injection(req: SeedInjectionRequest) -> SeedInjectionResponse:
    """Seed a fixed handwritten payload into a catalog field for one episode."""
    field = req.target_field
    if field == "item_description":
        field = "description"
    if field not in {"description", "reviews", "delivery_notes"}:
        raise HTTPException(
            status_code=400,
            detail="target_field must be description|item_description|reviews|delivery_notes",
        )
    if get_item(req.merchant, req.item_id) is None:
        raise HTTPException(status_code=404, detail="merchant/item not found")
    text = _resolve_payload(req.payload, req.payload_ref)
    entry = {
        "merchant": req.merchant,
        "item_id": req.item_id,
        "target_field": field,
        "payload": text,
    }
    bucket = _INJECTIONS.setdefault(req.episode_id, [])
    # Replace prior seed for same merchant/item/field
    bucket[:] = [
        e
        for e in bucket
        if not (
            e["merchant"] == req.merchant
            and e["item_id"] == req.item_id
            and e["target_field"] == field
        )
    ]
    bucket.append(entry)
    return SeedInjectionResponse(
        ok=True,
        banner=BANNER,
        episode_id=req.episode_id,
        merchant=req.merchant,
        item_id=req.item_id,
        target_field=field,
        payload_chars=len(text),
    )


@router.delete("/seed_injection/{episode_id}")
def clear_injection(episode_id: str) -> dict[str, Any]:
    removed = len(_INJECTIONS.pop(episode_id, []))
    return {"banner": BANNER, "episode_id": episode_id, "cleared": removed}


@router.get("/demo/seed")
def demo_seed() -> dict[str, Any]:
    """Return the demo seed blob (merchants + pre-armed scenarios + demo user)."""
    return _with_banner(build_demo_seed())


@router.get("/demo/scenarios")
def demo_scenarios() -> dict[str, Any]:
    return _with_banner(DEMO_ATTACK_SCENARIOS)


def reset_injections() -> None:
    """Test helper — wipe all episode overlays."""
    _INJECTIONS.clear()

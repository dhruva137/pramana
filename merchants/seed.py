"""Demo seed helpers for the sandboxed merchant catalog.

Idempotent in-memory overlays used by `python -m core.db.seed --demo`
(and by local tests). Does not touch production systems.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from merchants.catalog import BANNER, MERCHANTS, get_item

# Pre-armed demo attack scenarios the console can trigger (payload text only;
# still requires explicit seed_injection per episode).
DEMO_ATTACK_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "demo_f1_payee",
        "family": "payee_substitution",
        "merchant": "swiggy_sim",
        "item_id": "8812",
        "target_field": "item_description",
        "payload_ref": "bench/corpus/attack/payloads/f1/html_comment_migrate.txt",
        "title": "Payee migrate HTML comment",
    },
    {
        "id": "demo_f3_fragmentation",
        "family": "fragmentation",
        "merchant": "swiggy_sim",
        "item_id": "8812",
        "target_field": "item_description",
        "payload_ref": "bench/corpus/attack/payloads/f3/policy_framing.txt",
        "title": "Split-to-evade policy framing",
    },
    {
        "id": "demo_f4_address",
        "family": "delivery_redirect",
        "merchant": "zepto_sim",
        "item_id": "5501",
        "target_field": "delivery_notes",
        "payload_ref": "bench/corpus/attack/payloads/f4/updated_address.txt",
        "title": "Updated delivery address note",
    },
]

DEMO_USER = {
    "user_ref": "user_demo_01",
    "display_name": "Demo Shopper",
    "saved_address": {
        "line1": "12 Sandbox Lane",
        "city": "Bengaluru",
        "pincode": "560001",
        "address_hash": "addr_hash_demo_home_v1",
    },
    "consent": {
        "instrument": "upi_reserve_pay:tok_demo",
        "cap_paise": 200000,
        "mode": "test",
    },
}


def demo_merchant_summaries() -> list[dict[str, Any]]:
    """Three clean sims + hostile payee, as expected by deploy seeding docs."""
    ids = ["swiggy_sim", "zomato_sim", "zepto_sim", "grocery_direct_pl"]
    out = []
    for mid in ids:
        m = MERCHANTS[mid]
        out.append(
            {
                "id": m["id"],
                "display_name": m["display_name"],
                "settlement_account_ref": m["settlement_account_ref"],
                "verified": m["verified"],
                "hostile": m["hostile"],
                "category": m["category"],
                "banner": BANNER,
                "items": deepcopy(m["items"]),
            }
        )
    return out


def build_demo_seed() -> dict[str, Any]:
    """Full demo seed blob — idempotent re-apply is safe (pure data)."""
    return {
        "banner": BANNER,
        "merchants": demo_merchant_summaries(),
        "attack_scenarios": deepcopy(DEMO_ATTACK_SCENARIOS),
        "user": deepcopy(DEMO_USER),
        "sample_item": get_item("swiggy_sim", "8812"),
    }

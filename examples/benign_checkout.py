"""
Example: seal → authorize a benign payment through Pramana (MOCK).

  python -m examples.benign_checkout
"""

from __future__ import annotations

from examples.pramana_client import PramanaClient


def main() -> None:
    c = PramanaClient()
    print("health", c.health())
    ep = c.create_episode("Order two chicken biryanis from Swiggy, under 600 total")
    eid = ep["episode_id"]
    print("sealed", eid)
    c.append_context(
        eid,
        content="biryani bowl price_paise=54000 merchant=swiggy",
        taint="MERCHANT_STRUCTURED",
        source_uri="catalog://swiggy/item/8812",
    )
    action = {
        "kind": "PAYMENT",
        "amount_paise": 54000,
        "currency": "INR",
        "payee": {"merchant_id": "swiggy", "account_ref": "acc_swiggy_settle"},
        "items": [{"title": "biryani", "qty": 2, "unit_price_paise": 27000}],
        "instrument": "upi_reserve_pay:tok_x",
        "delivery_address_hash": "sha256:demo_address",
        "human_confirmed": True,
    }
    provenance = {
        "amount_paise": {"taint": "MERCHANT_STRUCTURED", "ledger_idx": 1},
        "payee.merchant_id": {"taint": "RZP_VERIFIED", "ledger_idx": 1},
        "payee.account_ref": {"taint": "RZP_VERIFIED", "ledger_idx": 1},
        "delivery_address_hash": {"taint": "USER", "ledger_idx": 0},
        "instrument": {"taint": "USER", "ledger_idx": 0},
    }
    decision = c.authorize(eid, action, provenance)
    print("verdict", decision.get("verdict"), decision.get("rule_id"))
    if decision.get("verdict") == "ADMIT" and decision.get("decision_id"):
        print("execute", c.execute(decision["decision_id"]))
    elif decision.get("proof_id"):
        print("denied — proof", decision["proof_id"])


if __name__ == "__main__":
    main()

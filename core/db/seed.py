"""Demo seed: merchants, users, optional dashboard history.

Loads fixtures from core/db/seed_data/*.json.

Usage:
  python -m core.db.seed --demo
  python -m core.db.seed --demo --history
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from core.db.models import DemoUser, Episode, MerchantRef
from core.db.session import async_session_factory, get_engine, init_db, reset_engine

SEED_DIR = Path(__file__).resolve().parent / "seed_data"
DEMO_CONSENT_CAP_PAISE = 200_000  # ₹2,000 — default for usr_demo_1


def _load_json(name: str) -> dict[str, Any]:
    path = SEED_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"seed fixture missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_merchant_rows() -> list[dict[str, Any]]:
    """MerchantRef rows from merchants.json (registry fields only)."""
    raw = _load_json("merchants.json")
    rows: list[dict[str, Any]] = []
    for m in raw.get("merchants") or []:
        rows.append(
            {
                "merchant_id": m["merchant_id"],
                "display_name": m["display_name"],
                "category": m["category"],
                "account_ref": m["account_ref"],
                "taint": m.get("taint") or "RZP_VERIFIED",
            }
        )
    return rows


def load_user_rows() -> list[dict[str, Any]]:
    raw = _load_json("users.json")
    rows: list[dict[str, Any]] = []
    for u in raw.get("users") or []:
        rows.append(
            {
                "user_ref": u["user_ref"],
                "display_name": u["display_name"],
                "consent_ref": u["consent_ref"],
                "consent_cap_paise": int(u["consent_cap_paise"]),
                "instrument": u["instrument"],
            }
        )
    return rows


# Backward-compatible exports for core.app boot seed.
DEMO_MERCHANTS: list[dict[str, str]] = load_merchant_rows()
_USERS = load_user_rows()
DEMO_USER: dict[str, Any] = next(
    (u for u in _USERS if u["user_ref"] == "usr_demo_1"),
    _USERS[0] if _USERS else {
        "user_ref": "usr_demo_1",
        "display_name": "Demo User",
        "consent_ref": "rsv_test_abc",
        "consent_cap_paise": DEMO_CONSENT_CAP_PAISE,
        "instrument": "upi_reserve_pay:tok_x",
    },
)


async def _upsert_merchants_and_users(session) -> tuple[int, int]:
    merchants = load_merchant_rows()
    users = load_user_rows()

    for m in merchants:
        existing = await session.get(MerchantRef, m["merchant_id"])
        if existing is None:
            session.add(MerchantRef(**m))
        else:
            existing.display_name = m["display_name"]
            existing.category = m["category"]
            existing.account_ref = m["account_ref"]
            existing.taint = m["taint"]

    for u in users:
        user = await session.get(DemoUser, u["user_ref"])
        if user is None:
            session.add(DemoUser(**u))
        else:
            user.display_name = u["display_name"]
            user.consent_ref = u["consent_ref"]
            user.consent_cap_paise = u["consent_cap_paise"]
            user.instrument = u["instrument"]

    await session.commit()
    n_m = len((await session.execute(select(MerchantRef))).scalars().all())
    n_u = len((await session.execute(select(DemoUser))).scalars().all())
    return n_m, n_u


async def seed_history(*, database_url: str | None = None) -> None:
    """Create a few dashboard episodes via force_mock demo journeys.

    Defense-only: uses scripted journeys (benign ADMIT, R6 DENY, quarantine).
    Skips if history episodes already exist (idempotent).
    """
    from core.api.demo_journeys import run_demo_journey
    from core.config import get_settings, reset_settings_cache
    from core.exec.razorpay_client import RazorpayClient

    reset_engine()
    reset_settings_cache()
    engine = get_engine(url=database_url) if database_url else get_engine()
    await init_db(engine=engine)
    factory = async_session_factory(engine=engine)

    async with factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(Episode))
        ).scalar_one()
        if int(count or 0) >= 3:
            print(f"History seed skipped — {count} episodes already present")
            return

    settings = get_settings()
    client = RazorpayClient(
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        mock_mode=True,
    )

    journeys = (
        ("benign", "pramana"),
        ("fragmentation", "pramana"),
        ("fault", "pramana"),
    )
    async with factory() as session:
        for journey, mode in journeys:
            result = await run_demo_journey(
                session, settings, client, journey=journey, mode=mode
            )
            await session.commit()
            verdict = result.get("verdict") or "?"
            status = result.get("status") or "?"
            print(
                f"  history:{journey} episode={result.get('episode_id')} "
                f"verdict={verdict} status={status} ok={result.get('ok')}"
            )


async def seed_demo(
    *,
    database_url: str | None = None,
    with_history: bool = False,
) -> None:
    reset_engine()
    engine = get_engine(url=database_url) if database_url else get_engine()
    await init_db(engine=engine)
    factory = async_session_factory(engine=engine)

    async with factory() as session:
        n_m, n_u = await _upsert_merchants_and_users(session)
        merchants = (await session.execute(select(MerchantRef))).scalars().all()
        users = (await session.execute(select(DemoUser))).scalars().all()
        print(f"Seeded {n_m} merchant refs, {n_u} demo users")
        for mr in merchants:
            print(f"  - {mr.merchant_id}: {mr.account_ref} ({mr.category})")
        for u in users:
            print(
                f"  user {u.user_ref} consent_cap_paise={u.consent_cap_paise} "
                f"({u.consent_ref})"
            )

    if with_history:
        print("Seeding dashboard history (force_mock journeys)…")
        await seed_history(database_url=database_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pramana DB seed")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed merchants + demo users from seed_data/*.json",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Also create benign / R6-deny / quarantine episodes (MOCK)",
    )
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    args = parser.parse_args(argv)
    if not args.demo:
        parser.print_help()
        return 2
    asyncio.run(seed_demo(database_url=args.database_url, with_history=args.history))
    return 0


if __name__ == "__main__":
    sys.exit(main())

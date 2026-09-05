"""Unit tests — executor: mock pay, faults, idempotency."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.db.models import Base, Decision, Episode
from core.db.session import normalize_database_url
from core.exec.executor import execute_decision, idempotency_key_for
from core.exec.razorpay_client import LiveKeyRefusedError, RazorpayClient, assert_not_live_key
from core.exec.reconciler import reconcile_execution
from core.ledger.service import get_ledger_state


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def normalize_url():
    assert normalize_database_url("postgresql://u:p@h/db").startswith("postgresql+psycopg://")
    assert normalize_database_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    assert normalize_database_url("sqlite+aiosqlite:///./x.db").startswith("sqlite")


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_admit(
    session: AsyncSession,
    *,
    episode_id: str = "ep_test_1",
    decision_id: str = "dec_test_1",
    amount_paise: int = 45000,
    payee: str = "swiggy",
) -> None:
    now = _utcnow()
    session.add(
        Episode(
            id=episode_id,
            user_ref="usr_demo_1",
            agent_id="agt_claude_demo",
            status="OPEN",
            envelope={"sie_version": "1.0", "constraints": {"episode_total_max_paise": 60000}},
            envelope_sig="sig",
            envelope_kid="seal-2026-09",
            ctx_ledger_head="sha256:0",
            seal_index=0,
            mode="PRAMANA_ON",
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
    )
    session.add(
        Decision(
            id=decision_id,
            episode_id=episode_id,
            action={
                "kind": "PAYMENT",
                "amount_paise": amount_paise,
                "currency": "INR",
                "payee": {"merchant_id": payee, "account_ref": "acc_swiggy_settle"},
            },
            provenance={},
            verdict="ADMIT",
            rule_id=None,
            rule_trace=[],
            ledger_before={"exposure_paise": 0},
            latency_ms=1,
            prev_hash="0" * 64,
            hash="a" * 64,
            created_at=now,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_mock_execute_success(session_factory):
    client = RazorpayClient(key_id="rzp_test_mock", mock_mode=True)
    async with session_factory() as session:
        await _seed_admit(session)
        result = await execute_decision(session, "dec_test_1", client=client)
        await session.commit()

        assert result.state == "SUCCEEDED"
        assert result.replayed is False
        assert result.rzp_order_id and result.rzp_order_id.startswith("order_mock_")
        assert result.rzp_payment_id and result.rzp_payment_id.startswith("pay_mock_")
        assert result.idempotency_key == hashlib.sha256(b"dec_test_1").hexdigest()

        state = await get_ledger_state(session, "ep_test_1")
        assert state.held_paise == 0
        assert state.committed_paise == 45000
        assert state.exposure_paise == 45000
        assert state.txn_count == 1


@pytest.mark.asyncio
async def test_fault_timeout_ambiguous_keeps_hold(session_factory):
    client = RazorpayClient(key_id="rzp_test_mock", mock_mode=True)
    async with session_factory() as session:
        await _seed_admit(session, decision_id="dec_to", episode_id="ep_to")
        result = await execute_decision(
            session, "dec_to", client=client, fault="timeout"
        )
        await session.commit()

        assert result.state == "AMBIGUOUS"
        assert result.rzp_order_id  # order id recorded for reconcile
        from core.db.models import Episode

        ep = await session.get(Episode, "ep_to")
        assert ep is not None
        assert ep.status == "QUARANTINED"

        state = await get_ledger_state(session, "ep_to")
        assert state.held_paise == 45000
        assert state.committed_paise == 0
        assert state.exposure_paise == 45000


@pytest.mark.asyncio
async def test_fault_http500_releases_hold(session_factory):
    client = RazorpayClient(key_id="rzp_test_mock", mock_mode=True)
    async with session_factory() as session:
        await _seed_admit(session, decision_id="dec_5", episode_id="ep_5")
        result = await execute_decision(
            session, "dec_5", client=client, fault="http500"
        )
        await session.commit()

        assert result.state == "FAILED"
        state = await get_ledger_state(session, "ep_5")
        assert state.held_paise == 0
        assert state.exposure_paise == 0
        assert state.txn_count == 0

        ep = await session.get(Episode, "ep_5")
        assert ep is not None
        assert ep.status == "OPEN"


@pytest.mark.asyncio
async def test_idempotency_second_execute_no_extra_rzp_call(session_factory):
    client = RazorpayClient(key_id="rzp_test_mock", mock_mode=True)
    async with session_factory() as session:
        await _seed_admit(session, decision_id="dec_idem", episode_id="ep_idem")
        r1 = await execute_decision(session, "dec_idem", client=client)
        await session.commit()
        calls_after_first = client.call_count

        r2 = await execute_decision(session, "dec_idem", client=client)
        await session.commit()

        assert r1.state == "SUCCEEDED"
        assert r2.replayed is True
        assert r2.rzp_payment_id == r1.rzp_payment_id
        assert client.call_count == calls_after_first  # no second Razorpay call

        state = await get_ledger_state(session, "ep_idem")
        assert state.committed_paise == 45000
        assert state.txn_count == 1


@pytest.mark.asyncio
async def test_idempotency_key_is_sha256_decision_id():
    assert idempotency_key_for("dec_abc") == hashlib.sha256(b"dec_abc").hexdigest()


def test_refuse_live_key():
    with pytest.raises(LiveKeyRefusedError):
        assert_not_live_key("rzp_live_should_fail")
    with pytest.raises(LiveKeyRefusedError):
        RazorpayClient(key_id="rzp_live_abc", key_secret="x")


@pytest.mark.asyncio
async def test_reconciler_releases_ambiguous_with_no_payment(session_factory):
    client = RazorpayClient(key_id="rzp_test_mock", mock_mode=True)
    async with session_factory() as session:
        await _seed_admit(session, decision_id="dec_rec", episode_id="ep_rec")
        await execute_decision(session, "dec_rec", client=client, fault="timeout")
        await session.commit()

        state = await get_ledger_state(session, "ep_rec")
        assert state.held_paise == 45000

        rec = await reconcile_execution(session, "dec_rec", client=client)
        await session.commit()

        assert rec.resolved is True
        assert rec.new_state == "FAILED"
        state = await get_ledger_state(session, "ep_rec")
        assert state.held_paise == 0
        assert state.exposure_paise == 0

        ep = await session.get(Episode, "ep_rec")
        assert ep is not None
        assert ep.status == "OPEN"

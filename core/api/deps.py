"""FastAPI dependencies — settings, DB session, Razorpay client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.db.session import async_session_factory
from core.exec.razorpay_client import RazorpayClient


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def settings_dep() -> Settings:
    return get_settings()


def razorpay_client(request: Request) -> RazorpayClient:
    client = getattr(request.app.state, "razorpay", None)
    if client is None:
        settings = get_settings()
        client = RazorpayClient(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
            mock_mode=settings.mock_mode or settings.effective_mock,
        )
        request.app.state.razorpay = client
    return client


def apply_request_llm_keys(
    gemini: Annotated[str | None, Header(alias="X-Pramana-Gemini-Key")] = None,
    anthropic: Annotated[str | None, Header(alias="X-Pramana-Anthropic-Key")] = None,
) -> dict[str, str | None]:
    """Judges paste keys in the console; forwarded per-request (not persisted).

    WARNING: writing into ``os.environ`` is process-global. Concurrent tenants can
    bleed keys across requests if we always overwrite. Prefer keys already set from
    ``.env`` / process env; only populate from headers when the slot is empty.
    """
    import os

    if gemini and not (os.environ.get("GEMINI_API_KEY") or "").strip():
        os.environ["GEMINI_API_KEY"] = gemini
    if anthropic and not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        os.environ["ANTHROPIC_API_KEY"] = anthropic
    return {"gemini": gemini, "anthropic": anthropic}


DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(settings_dep)]
RzpClient = Annotated[RazorpayClient, Depends(razorpay_client)]

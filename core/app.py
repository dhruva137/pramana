"""Pramana FastAPI application — boot, CORS, routers, lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings, get_settings, reset_settings_cache
from core.db.session import get_engine, init_db, reset_engine
from core.exec.razorpay_client import RazorpayClient, assert_not_live_key

logger = logging.getLogger("pramana")


def _boot_assertions(settings: Settings) -> None:
    assert_not_live_key(settings.razorpay_key_id)
    # Settings validator already refused non-rzp_test_ and ensured 32-byte keys.
    assert settings.pramana_seal_sk and settings.pramana_proof_sk
    assert len(settings.seal_sk_raw()) == 32
    assert len(settings.proof_sk_raw()) == 32
    if settings.ephemeral_keys:
        logger.warning(
            "PRAMANA_SEAL_SK / PRAMANA_PROOF_SK empty — using ephemeral demo keys "
            "(JWKS rotates on restart; fine for Render demo)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    reset_settings_cache()
    settings = get_settings()
    _boot_assertions(settings)

    # Sync env for sealer / razorpay helpers that still read os.environ
    import os

    os.environ.setdefault("MOCK_MODE", "true" if settings.mock_mode else "false")
    os.environ["PRAMANA_SEAL_SK"] = settings.pramana_seal_sk
    os.environ["PRAMANA_PROOF_SK"] = settings.pramana_proof_sk
    os.environ["PRAMANA_SEAL_KID"] = settings.pramana_seal_kid
    os.environ["PRAMANA_PROOF_KID"] = settings.pramana_proof_kid
    if settings.database_url:
        os.environ["DATABASE_URL"] = settings.database_url

    reset_engine()
    engine = get_engine()
    await init_db(engine=engine)

    if settings.seed_demo_on_boot:
        try:
            from sqlalchemy import select

            from core.db.models import DemoUser, MerchantRef
            from core.db.seed import DEMO_MERCHANTS, DEMO_USER
            from core.db.session import async_session_factory

            factory = async_session_factory()
            async with factory() as session:
                for m in DEMO_MERCHANTS:
                    existing = await session.get(MerchantRef, m["merchant_id"])
                    if existing is None:
                        session.add(MerchantRef(**m))
                user = await session.get(DemoUser, DEMO_USER["user_ref"])
                if user is None:
                    session.add(DemoUser(**DEMO_USER))
                await session.commit()
                n = len((await session.execute(select(MerchantRef))).scalars().all())
                logger.info("demo seed: %s merchant refs", n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("demo seed skipped: %s", exc)

    app.state.settings = settings
    app.state.razorpay = RazorpayClient(
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        mock_mode=settings.mock_mode or settings.effective_mock,
    )
    yield
    await engine.dispose()
    reset_engine()


def create_app(*, settings: Settings | None = None) -> FastAPI:
    if settings is not None:
        reset_settings_cache()
        # Force cache to this instance by patching get_settings — tests pass env instead.
        pass

    cfg = settings or get_settings()

    app = FastAPI(
        title="Pramana",
        description="Intent custody and admission control for agentic UPI payments",
        version="0.1.0",
        lifespan=lifespan,
    )

    origins = cfg.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from core.api.router import router as api_router
    from merchants.service import router as merchants_router

    app.include_router(api_router)
    # merchants.service.router already has prefix="/sandbox"
    app.include_router(merchants_router)

    # Single-service Render demo: serve the Vite build from the same origin.
    console_dist = Path(__file__).resolve().parent.parent / "console" / "dist"
    if console_dist.is_dir():
        assets = console_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="console-assets")

        _API_PREFIXES = (
            "v1/",
            "sandbox/",
            "healthz",
            "docs",
            "redoc",
            "openapi.json",
            ".well-known/",
        )

        # include_in_schema=False + no FileResponse return annotation: otherwise
        # FastAPI OpenAPI generation crashes on FileResponse ForwardRef when the
        # SPA is mounted (integrators cannot export /openapi.json).
        @app.get("/", include_in_schema=False)
        async def console_index():
            return FileResponse(console_dist / "index.html")

        @app.get("/{spa_path:path}", include_in_schema=False)
        async def console_spa(spa_path: str):
            if any(spa_path == p.rstrip("/") or spa_path.startswith(p) for p in _API_PREFIXES):
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not found")
            candidate = console_dist / spa_path
            if spa_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(console_dist / "index.html")

    return app


app = create_app()

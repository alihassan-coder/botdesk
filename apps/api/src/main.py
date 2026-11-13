"""The FastAPI app. Run it with `pnpm dev:api` (from the repo root)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.v1.router import api_router
from src.core.config import Settings, get_settings
from src.core.database import Base, create_engine, create_sessionmaker, is_in_memory
from src.core.errors import AppError
from src.core.secrets import build_secret_box
from src.runtime.memory import build_memory
from src.runtime.runner import run_manager
from src.services.email_service import build_email_sender
from src.services.model_catalog import ModelCatalog

# Calls to outside services (email, model lists) give up quickly; model lists set shorter timeouts.
OUTBOUND_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _show_app_logs() -> None:
    """uvicorn sets up only its own loggers; show the app's INFO lines (e.g. "Email sent") too."""
    app_logger = logging.getLogger("src")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)


def create_app(settings: Settings | None = None, *, outbound: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """`outbound` replaces the network for calls to other services (tests pass an httpx.MockTransport)."""
    settings = settings or get_settings()
    _show_app_logs()
    secrets = build_secret_box(settings)  # production stops here without SECRET_KEY

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.sqlalchemy_url)
        if is_in_memory(settings.sqlalchemy_url):
            # A brand-new in-memory database (the tests' default) has no tables yet.
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        async with (
            httpx.AsyncClient(timeout=OUTBOUND_TIMEOUT, transport=outbound) as http,
            run_manager(settings, app.state.sessionmaker, build_memory(settings), secrets) as runs,
        ):
            app.state.email = build_email_sender(settings, http)
            app.state.models = ModelCatalog(http, allow_private_urls=settings.private_model_urls_allowed)
            app.state.runs = runs
            yield
        await engine.dispose()

    app = FastAPI(
        title="BotDesk API",
        version="0.1.0",
        lifespan=lifespan,
        # API docs at /api/docs, outside production.
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.state.settings = settings
    app.state.secrets = secrets

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,  # the web app sends the session cookie
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.exception_handler(AppError)
    async def app_error(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse({"detail": error.message}, status_code=error.status_code)

    app.include_router(api_router)
    return app


app = create_app()

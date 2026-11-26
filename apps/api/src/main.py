"""The FastAPI app. Run it with `pnpm dev:api` (from the repo root)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.api.v1.router import api_router
from src.core.access_log import redact_access_log
from src.core.config import Settings, get_settings
from src.core.database import Base, create_engine, create_sessionmaker, is_in_memory
from src.core.errors import AppError, TooManyRequests
from src.core.rate_limit import RateLimiter
from src.core.secrets import build_secret_box
from src.core.url_guard import GuardedTransport
from src.jobs.background import background
from src.runtime.memory import build_memory
from src.services import mcp_server_service
from src.services.credential_vault import CredentialVault
from src.services.email_service import build_email_sender
from src.services.memory_router import OrgMemory
from src.services.model_catalog import ModelCatalog
from src.services.oauth_flow import OAuth

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
    redact_access_log()  # no OAuth code or state in uvicorn's access log
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
        allow_private = settings.allow_private_model_urls
        # Custom model servers are addresses people type in: their calls connect only to
        # checked public addresses and never follow redirects (SSRF guard, core/url_guard.py).
        custom_transport = outbound or GuardedTransport(allow_private=allow_private)
        async with (
            httpx.AsyncClient(timeout=OUTBOUND_TIMEOUT, transport=outbound) as http,
            httpx.AsyncClient(timeout=OUTBOUND_TIMEOUT, transport=custom_transport, follow_redirects=False) as custom,
        ):
            app.state.email = build_email_sender(settings, http)
            # One catalog: Models & keys and runs (OpenRouter's prices) share its cache.
            app.state.models = ModelCatalog(http, allow_private_urls=allow_private, custom_http=custom)
            # Runs and other background jobs (ADR 0013): a worker in this process, unless
            # WORKER_MODE=separate on Postgres (then `python -m src.worker` runs them).
            async with background(
                settings,
                app.state.sessionmaker,
                # Each organization's memory: its own memory key, else the server's (Settings → Memory).
                OrgMemory(build_memory(settings), app.state.sessionmaker, settings, app.state.vault),
                secrets,
                app.state.models,
            ) as jobs:
                app.state.runs = jobs.runs
                # Signing in with OAuth apps (ADR 0010 §5): the same plugins and vault as the runs.
                app.state.oauth = OAuth(settings, app.state.vault, jobs.runs.registry, transport=outbound)
                # MCP servers' sign-ins come back to the same callback (slice 7.3); read `runs.mcp`
                # when they do, so a test's network swap applies.
                app.state.oauth.mcp_finish = lambda db, flow, code, iss, user: mcp_server_service.finish_sign_in(
                    db, app.state.runs.mcp, flow, code, iss, user
                )
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
    app.state.outbound = outbound
    app.state.secrets = secrets
    app.state.vault = CredentialVault.from_settings(settings)  # connections' credentials (ADR 0010)
    app.state.limiter = RateLimiter()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,  # the web app sends the session cookie
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    # The client's address and scheme from X-Forwarded-For / -Proto, only when the connection
    # comes from a proxy in FORWARDED_ALLOW_IPS. Done here (uvicorn runs with --no-proxy-headers)
    # so the rule is in one place and the same under any server and in tests.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.forwarded_allow_ips)

    @app.exception_handler(AppError)
    async def app_error(_: Request, error: AppError) -> JSONResponse:
        headers = {"Retry-After": str(error.retry_after_seconds)} if isinstance(error, TooManyRequests) else None
        return JSONResponse({"detail": error.message}, status_code=error.status_code, headers=headers)

    app.include_router(api_router)
    return app


app = create_app()

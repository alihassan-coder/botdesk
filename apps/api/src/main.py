"""The FastAPI app. Run it with `pnpm dev:api` (from the repo root)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.v1.router import api_router
from src.core.config import Settings, get_settings
from src.core.database import create_engine, create_sessionmaker
from src.core.errors import AppError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.sqlalchemy_url)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,  # the web app sends the session cookie
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.exception_handler(AppError)
    async def app_error(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse({"detail": error.message}, status_code=error.status_code)

    app.include_router(api_router)
    return app


app = create_app()

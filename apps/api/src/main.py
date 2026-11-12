"""The FastAPI app. Run it with `pnpm dev:api` (from the repo root)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.v1.router import api_router
from src.core.config import Settings, get_settings
from src.core.database import Base, create_engine, create_sessionmaker, is_in_memory
from src.core.errors import AppError
from src.runtime.memory import build_memory
from src.runtime.runner import run_manager


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.sqlalchemy_url)
        if is_in_memory(settings.sqlalchemy_url):
            # A brand-new in-memory database (the tests' default) has no tables yet.
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        async with run_manager(settings, app.state.sessionmaker, build_memory(settings)) as runs:
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

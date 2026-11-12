"""Test fixtures.

- `client`: a fresh app on an in-memory SQLite database. No network, runs anywhere in seconds.
  Bots don't reply here (runs are created but not started): these tests are about the API.
- `pg`: a fresh app on real Postgres (TEST_DATABASE_URL), with bots replying. Everything that
  depends on Postgres (runs, checkpoints, the one-run-per-chat guard, JSONB) is tested here.
  Skipped, with a reason, when TEST_DATABASE_URL isn't set.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from src.core.config import Settings
from src.core.database import Base, create_engine
from src.main import create_app
from src.runtime.runner import RunManager
from src.services.email_service import EmailMessage

TEST_SETTINGS = Settings(environment="test", database_url="sqlite+aiosqlite://", _env_file=None)

PASSWORD = "correct-horse-battery"

# TEST_DATABASE_URL comes from the environment (CI) or apps/api/.env (your machine).
_local = Settings()
TEST_DATABASE_URL = _local.test_database_url
if TEST_DATABASE_URL and TEST_DATABASE_URL in (_local.database_url, _local.database_url_direct):
    raise RuntimeError("TEST_DATABASE_URL must be a separate database: the Postgres tests wipe it.")


def pytest_asyncio_loop_factories(config: pytest.Config, item: pytest.Item) -> Mapping[str, Callable[[], Any]]:
    """psycopg's async driver can't use Windows' default event loop; the selector loop works everywhere."""
    return {"selector": asyncio.SelectorEventLoop}


async def _client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class FakeEmailSender:
    """Records emails instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


@pytest.fixture
def outbox() -> FakeEmailSender:
    """The emails the `client` app sent (background tasks finish before the response returns)."""
    return FakeEmailSender()


@pytest.fixture
async def client(outbox: FakeEmailSender) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(TEST_SETTINGS)
    async with app.router.lifespan_context(app):
        app.state.runs.enabled = False
        app.state.email = outbox
        async with await _client_for(app) as http:
            yield http


@dataclass
class Postgres:
    client: httpx.AsyncClient
    runs: RunManager


_tables_created = False


async def _empty_database(url: str) -> None:
    """Create the tables once per test session (from the models), then empty them before each test."""
    global _tables_created
    engine = create_engine(Settings(database_url=url, _env_file=None).sqlalchemy_url)
    async with engine.begin() as connection:
        if not _tables_created:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
            _tables_created = True
        else:
            tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
            await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def pg() -> AsyncIterator[Postgres]:
    if not TEST_DATABASE_URL:
        pytest.skip("Postgres test: set TEST_DATABASE_URL to run it (see docs/backend/README.md)")
    await _empty_database(TEST_DATABASE_URL)
    settings = Settings(environment="test", database_url=TEST_DATABASE_URL, _env_file=None)
    app = create_app(settings)
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        yield Postgres(client=http, runs=app.state.runs)


async def sign_up(client: httpx.AsyncClient, name: str = "Ali Hassan", email: str = "ali@acme.dev") -> dict[str, Any]:
    response = await client.post("/api/v1/auth/sign-up", json={"name": name, "email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    me: dict[str, Any] = response.json()
    return me

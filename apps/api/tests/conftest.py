"""Test fixtures.

- `client`: a fresh app on an in-memory SQLite database. No network, runs anywhere in seconds.
  Bots don't reply here (runs are created but not started): these tests are about the API.
  Calls to model providers go to `providers` (a `FakeProviders`), never to the internet.
- `pg`: a fresh app on real Postgres (TEST_DATABASE_URL), with bots replying. Everything that
  depends on Postgres (runs, checkpoints, the one-run-per-chat guard, JSONB) is tested here.
  Skipped, with a reason, when TEST_DATABASE_URL isn't set.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

# `src.main` builds an app when imported, and without an explicit ENVIRONMENT that app refuses to
# start without SECRET_KEY (it fails closed). Tests are a test environment; CI sets nothing.
os.environ.setdefault("ENVIRONMENT", "test")

from src.core.config import Settings
from src.core.database import Base, create_engine
from src.main import create_app
from src.runtime.runner import RunManager
from src.services.email_service import EmailMessage

# Custom servers in these tests live on "localhost" (answered by FakeProviders, never the
# network), so the SSRF guard is opted out of here, as on a developer's machine. The guard
# itself is tested in test_model_providers.py and test_url_guard.py.
TEST_SETTINGS = Settings(
    environment="test", database_url="sqlite+aiosqlite://", allow_private_model_urls=True, _env_file=None
)

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


Answer = Callable[[httpx.Request], httpx.Response]


class FakeProviders:
    """Stands in for every model provider's HTTP API: `answer(host, …)` says how a host replies.
    Hosts with no answer refuse the connection, like a server that's down."""

    def __init__(self) -> None:
        self.answers: dict[str, Answer] = {}
        self.requests: list[httpx.Request] = []

    def answer(self, host: str, body: Any = None, *, status: int = 200, handler: Answer | None = None) -> None:
        self.answers[host] = handler or (lambda _request: httpx.Response(status, json=body))

    def calls_to(self, host: str) -> int:
        return sum(1 for request in self.requests if request.url.host == host)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if answer := self.answers.get(request.url.host):
            return answer(request)
        raise httpx.ConnectError("connection refused", request=request)


@pytest.fixture
def providers() -> FakeProviders:
    return FakeProviders()


@asynccontextmanager
async def api_client(
    settings: Settings, providers: FakeProviders, outbox: FakeEmailSender | None = None
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    """A fresh app on `settings` with fake providers; runs are created but never start."""
    app = create_app(settings, outbound=httpx.MockTransport(providers.handle))
    async with app.router.lifespan_context(app):
        app.state.runs.enabled = False
        app.state.email = outbox or FakeEmailSender()
        async with await _client_for(app) as http:
            yield app, http


@pytest.fixture
async def client(outbox: FakeEmailSender, providers: FakeProviders) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(TEST_SETTINGS, providers, outbox) as (_, http):
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

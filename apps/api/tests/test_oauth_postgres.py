"""OAuth on real Postgres: the sign-in's `DELETE … RETURNING` and JSONB scopes, and the refresh
lease: two tool calls refreshing one connection at once make exactly one token request."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import update

from src.core.database import utcnow
from src.main import create_app
from src.models import Connection
from src.runtime.runner import RunManager
from src.services.tool_execution_service import RunRef
from tests.conftest import TEST_DATABASE_URL, _client_for, _empty_database, pg_settings, sign_up
from tests.test_oauth import CLIENT_ID, CLIENT_SECRET, PROFILE, FakeGoogle, _gmail_tool


class SlowGoogle(FakeGoogle):
    """Takes its time over each token request, so concurrent refreshes overlap."""

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            await asyncio.sleep(0.5)
        return await super().handle(request)


@pytest.fixture
async def world() -> AsyncIterator[tuple[httpx.AsyncClient, RunManager, SlowGoogle, str]]:
    if not TEST_DATABASE_URL:
        pytest.skip("Postgres test: set TEST_DATABASE_URL to run it (see docs/backend/README.md)")
    await _empty_database(TEST_DATABASE_URL)
    google = SlowGoogle()
    settings = pg_settings(
        plugins="demo,gmail",
        google_oauth_client_id=CLIENT_ID,
        google_oauth_client_secret=SecretStr(CLIENT_SECRET),
    )
    app = create_app(settings, outbound=httpx.MockTransport(google.handle))
    async with app.router.lifespan_context(app), await _client_for(app) as client:
        app.state.runs.tool_access.transport = httpx.MockTransport(google.handle)
        ali = await sign_up(client)
        yield client, app.state.runs, google, ali["organizations"][0]["id"]


async def _connect(client: httpx.AsyncClient, org_id: str) -> dict[str, Any]:
    org = f"/api/v1/orgs/{org_id}"
    started = await client.post(f"{org}/connections/oauth/start", json={"connectorId": "gmail", "ownerKind": "org"})
    assert started.status_code == 200, started.text
    state = parse_qs(urlsplit(started.json()["authorizeUrl"]).query)["state"][0]
    back = await client.get(
        "/api/v1/oauth/callback", params={"state": state, "code": "4/CODE", "iss": "https://accounts.google.com"}
    )
    assert back.headers["location"].endswith("result=connected&connector=gmail")
    again = await client.get(
        "/api/v1/oauth/callback", params={"state": state, "code": "4/CODE", "iss": "https://accounts.google.com"}
    )
    assert again.headers["location"].endswith("result=error&code=expired")  # used once
    (gmail,) = (await client.get(f"{org}/connections")).json()
    connection: dict[str, Any] = gmail
    return connection


async def test_two_refreshes_at_once_make_one_token_request(
    world: tuple[httpx.AsyncClient, RunManager, SlowGoogle, str],
) -> None:
    client, runs, google, org_id = world
    gmail = await _connect(client, org_id)
    assert gmail["scopes"] == ["https://www.googleapis.com/auth/gmail.modify"]
    connection_id = uuid.UUID(gmail["id"])
    async with runs.sessionmaker() as db:
        await db.execute(
            update(Connection)
            .where(Connection.id == connection_id)
            .values(access_expires_at=utcnow() + timedelta(seconds=10))
        )
        await db.commit()
    run = RunRef(run_id=uuid.uuid4(), org_id=uuid.UUID(org_id), thread_id=uuid.uuid4(), bot_id=uuid.uuid4())

    async def call(name: str) -> None:
        async with runs.tool_access.open(run, _gmail_tool(), name, connection_id=connection_id, timeout_seconds=5) as a:
            await a.http.request("GET", PROFILE)

    await asyncio.gather(call("call-1"), call("call-2"))

    assert len(google.to("/token")) == 2  # the code exchange, then ONE refresh
    assert google.forms("/token")[1]["grant_type"] == "refresh_token"
    profiles = google.to("/gmail/v1/users/me/profile")[1:]  # after the account lookup
    assert [request.headers["authorization"] for request in profiles] == ["Bearer ya29.ACCESS-2"] * 2
    async with runs.sessionmaker() as db:
        row = await db.get(Connection, connection_id)
        assert row is not None and row.refresh_lease_until is None
        assert row.access_expires_at is not None and row.access_expires_at > utcnow() + timedelta(minutes=50)


async def test_the_lease_is_taken_again_after_the_winner_crashes(
    world: tuple[httpx.AsyncClient, RunManager, SlowGoogle, str],
) -> None:
    client, runs, google, org_id = world
    connection_id = uuid.UUID((await _connect(client, org_id))["id"])

    async def expire(lease: Any = None) -> None:
        async with runs.sessionmaker() as db:
            await db.execute(
                update(Connection)
                .where(Connection.id == connection_id)
                .values(access_expires_at=utcnow() + timedelta(seconds=10), refresh_lease_until=lease)
            )
            await db.commit()

    run = RunRef(run_id=uuid.uuid4(), org_id=uuid.UUID(org_id), thread_id=uuid.uuid4(), bot_id=uuid.uuid4())

    async def call(name: str) -> str:
        async with runs.tool_access.open(run, _gmail_tool(), name, connection_id=connection_id, timeout_seconds=5) as a:
            await a.http.request("GET", PROFILE)
        return google.to("/gmail/v1/users/me/profile")[-1].headers["authorization"]

    await expire()
    google.token_fault = RuntimeError("the winner crashed")
    results = await asyncio.gather(call("call-1"), call("call-2"), return_exceptions=True)
    assert sum(isinstance(result, RuntimeError) for result in results) == 1
    assert "Bearer ya29.ACCESS-1" in results  # the other call went on with the token it had
    assert len(google.to("/token")) == 2  # the code exchange and the one (crashed) refresh
    async with runs.sessionmaker() as db:
        row = await db.get(Connection, connection_id)
        assert row is not None and row.refresh_lease_until is None  # given back at once

    google.token_fault = None
    await expire(lease=utcnow() - timedelta(seconds=1))  # a worker that died holding it
    assert await call("call-3") == "Bearer ya29.ACCESS-2"
    assert len(google.to("/token")) == 3

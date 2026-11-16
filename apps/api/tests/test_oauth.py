"""OAuth connections (ADR 0010 §5-§6, ADR 0011 §7, slice 5.3), on SQLite: Connect apps' connector
list, `oauth/start`, the callback and every result code it can send the browser back with,
reconnecting, refreshing a token (and `invalid_grant`), and revoking at Google on disconnect.

Google (sign-in, token, revoke) and the Gmail API are `FakeGoogle`, answering through
`httpx.MockTransport`. Two concurrent refreshes are in test_oauth_postgres.py.
"""

import asyncio
import base64
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from botdesk_plugin_sdk import NoArgs, ToolContext, ToolSpec
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import delete, select, update

from src.core.access_log import RedactOAuthCallback
from src.core.config import Settings
from src.core.database import utcnow
from src.core.url_guard import GuardedTransport, UnsafeUrl
from src.main import create_app
from src.models import AuditEntry, BotTool, Connection, Membership, OAuthFlow
from src.plugins.registry import RegisteredTool
from src.runtime.runner import RunManager
from src.services import oauth_flow
from src.services.tool_execution_service import RunRef
from tests.conftest import PASSWORD, sign_up

CLIENT_ID = "1234-botdesk.apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-CLIENT-SECRET-0001"
READ = "https://www.googleapis.com/auth/gmail.readonly"
MODIFY = "https://www.googleapis.com/auth/gmail.modify"
PROFILE = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
CALLBACK = "/api/v1/oauth/callback"
WEB = "http://localhost:3000"
ISSUER = "https://accounts.google.com"
MISSING = object()

GOOGLE_SETTINGS = Settings(
    environment="test",
    database_url="sqlite+aiosqlite://",
    plugins="demo,gmail",
    google_oauth_client_id=CLIENT_ID,
    google_oauth_client_secret=SecretStr(CLIENT_SECRET),
    api_public_url="https://api.botdesk.test",
    web_app_url=WEB,
    _env_file=None,
)


@dataclass
class FakeGoogle:
    """Google's token and revoke endpoints and Gmail's profile. Each token answer hands out a
    new pair of tokens (ACCESS-n, REFRESH-n), unless `token_answer` says otherwise."""

    email: str = "Ali@Acme.dev"
    granted: str | None = MODIFY  # the token response's `scope`; None: no `scope` in it
    send_refresh_token: bool = True
    token_status: int = 200
    token_error: str = ""
    profile_status: int = 200
    revoke_status: int = 200
    expires_in: Any = 3599  # MISSING: no `expires_in` in the answer
    token_fault: BaseException | None = None  # raised instead of answering /token (a guard refusal, a bug)
    token_delay: float = 0.0  # seconds before /token answers
    on_token: Callable[[], Awaitable[None]] | None = None  # runs while /token is answering
    requests: list[httpx.Request] = field(default_factory=list)
    issued: int = 0

    def to(self, path: str) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path == path]

    def forms(self, path: str) -> list[dict[str, str]]:
        return [{k: v[0] for k, v in parse_qs(r.content.decode()).items()} for r in self.to(path)]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if host == "oauth2.googleapis.com" and path == "/token":
            if self.token_delay:
                await asyncio.sleep(self.token_delay)
            if self.on_token is not None:
                await self.on_token()
            if self.token_fault is not None:
                raise self.token_fault
            if self.token_status != 200:
                return httpx.Response(
                    self.token_status,
                    json={"error": self.token_error, "error_description": "Token has been expired or revoked."},
                )
            self.issued += 1
            body: dict[str, Any] = {"access_token": f"ya29.ACCESS-{self.issued}", "token_type": "Bearer"}
            if self.expires_in is not MISSING:
                body["expires_in"] = self.expires_in
            if self.granted is not None:
                body["scope"] = self.granted
            if self.send_refresh_token:
                body["refresh_token"] = f"1//REFRESH-{self.issued}"
            return httpx.Response(200, json=body)
        if host == "oauth2.googleapis.com" and path == "/revoke":
            return httpx.Response(self.revoke_status, json={})
        if host == "gmail.googleapis.com" and path == "/gmail/v1/users/me/profile":
            if self.profile_status != 200:
                return httpx.Response(self.profile_status, json={"error": {"message": "nope"}})
            return httpx.Response(200, json={"emailAddress": self.email, "messagesTotal": 12})
        raise httpx.ConnectError("no such fake", request=request)


@dataclass
class Team:
    app: FastAPI
    client: httpx.AsyncClient
    google: FakeGoogle
    org: str
    org_id: str
    bot_id: str  # Scout, made by Ali (the owner)

    async def sign_in(self, email: str) -> None:
        self.client.cookies.clear()
        response = await self.client.post("/api/v1/auth/sign-in", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text

    async def start(self, expect: int = 200, **body: Any) -> dict[str, Any]:
        payload = {"connectorId": "gmail", "ownerKind": "member", **body}
        response = await self.client.post(f"{self.org}/connections/oauth/start", json=payload)
        assert response.status_code == expect, response.text
        data: dict[str, Any] = response.json()
        return data

    async def authorize(self, **body: Any) -> dict[str, str]:
        """Start a flow and return the authorize URL's query (state, code_challenge…)."""
        url = (await self.start(**body))["authorizeUrl"]
        return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}

    async def callback(self, **params: str | None) -> dict[str, str]:
        """Come back from Google; returns the web callback page's query (result, code, connector).
        Google's `iss` comes along unless the test passes `iss=None`."""
        query = {key: value for key, value in {"iss": ISSUER, **params}.items() if value is not None}
        response = await self.client.get(CALLBACK, params=query)
        assert response.status_code == 303, response.text
        location = response.headers["location"]
        assert location.startswith(f"{WEB}/apps/callback?"), location
        return {key: values[0] for key, values in parse_qs(urlsplit(location).query).items()}

    async def connect_gmail(self, **body: Any) -> dict[str, str]:
        query = await self.authorize(**body)
        return await self.callback(state=query["state"], code="4/CODE-ONE", scope=MODIFY)

    async def connections(self) -> list[dict[str, Any]]:
        response = await self.client.get(f"{self.org}/connections")
        assert response.status_code == 200, response.text
        data: list[dict[str, Any]] = response.json()
        return data

    async def actions(self) -> list[str]:
        async with self.app.state.sessionmaker() as db:
            return list(await db.scalars(select(AuditEntry.action).order_by(AuditEntry.created_at)))


@asynccontextmanager
async def acme(settings: Settings = GOOGLE_SETTINGS) -> AsyncIterator[Team]:
    """Ali owns Acme and made Scout; Sara is a member. Ali is signed in."""
    google = FakeGoogle()
    settings = settings.model_copy()  # a test may change it (the client removed mid-flow)
    app = create_app(settings, outbound=httpx.MockTransport(google.handle))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        app.state.runs.enabled = False
        app.state.runs.tool_access.transport = httpx.MockTransport(google.handle)
        ali = await sign_up(client)
        org_id = ali["organizations"][0]["id"]
        org = f"/api/v1/orgs/{org_id}"
        invite = await client.post(f"{org}/invitations", json={"email": "sara@acme.dev", "role": "member"})
        bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
        await sign_up(client, name="Sara", email="sara@acme.dev")
        token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
        assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
        team = Team(app=app, client=client, google=google, org=org, org_id=org_id, bot_id=bot["id"])
        await team.sign_in("ali@acme.dev")
        yield team


@pytest.fixture
async def team() -> AsyncIterator[Team]:
    async with acme() as world:
        yield world


# Connectors (Connect apps)


async def test_connectors_say_how_each_app_connects_and_whether_it_is_set_up(team: Team) -> None:
    response = await team.client.get(f"{team.org}/connectors")
    assert response.status_code == 200, response.text
    by_id = {connector["id"]: connector for connector in response.json()}
    gmail, demo = by_id["gmail"], by_id["demo"]
    assert gmail["authType"] == "oauth2" and gmail["setup"] == "ready"
    assert gmail["accessLevels"] == ["read", "full"] and gmail["defaultAccess"] == "full"
    assert gmail["tools"] == [] and gmail["name"] == "Gmail" and gmail["version"] == "0.1.0"
    assert demo["authType"] == "api_key" and demo["setup"] == "ready"
    assert demo["accessLevels"] == [] and demo["defaultAccess"] is None
    assert {"name": "demo.send_email", "risk": "external-send"}.items() <= next(
        tool for tool in demo["tools"] if tool["name"] == "demo.send_email"
    ).items()
    assert (await team.client.get(f"{team.org}/plugins")).status_code == 200  # still there


async def test_gmail_is_not_set_up_without_both_halves_of_the_google_client() -> None:
    no_secret = GOOGLE_SETTINGS.model_copy(update={"google_oauth_client_secret": SecretStr("")})
    async with acme(no_secret) as team:
        (gmail,) = [c for c in (await team.client.get(f"{team.org}/connectors")).json() if c["id"] == "gmail"]
        assert gmail["setup"] == "not-configured"
        refused = await team.start(expect=400)
        assert refused["detail"] == "Gmail isn't set up on this server yet."


# Start


async def test_start_sends_the_browser_to_google_with_pkce_and_offline_access(team: Team) -> None:
    url = (await team.start(access="read"))["authorizeUrl"]
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert query["response_type"] == "code"
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == "https://api.botdesk.test/api/v1/oauth/callback"
    assert query["scope"] == READ
    assert query["code_challenge_method"] == "S256" and len(query["code_challenge"]) == 43
    assert (query["access_type"], query["prompt"], query["include_granted_scopes"]) == ("offline", "consent", "true")
    assert len(query["state"]) >= 43
    assert "client_secret" not in query and CLIENT_SECRET not in url
    async with team.app.state.sessionmaker() as db:
        flow = await db.scalar(select(OAuthFlow))
    assert flow is not None
    assert flow.state_hash == hashlib.sha256(query["state"].encode()).hexdigest()  # only the hash is kept
    assert flow.scopes == [READ] and flow.access == "read"
    assert timedelta(minutes=9) < flow.expires_at - utcnow() <= timedelta(minutes=10)


async def test_start_refuses_what_it_cannot_do(team: Team) -> None:
    await team.start(expect=404, connectorId="nope")
    assert (await team.start(expect=400, connectorId="demo"))["detail"]  # an API-key app
    await team.start(expect=400, access="everything")
    await team.start(expect=400, ownerKind="bot")  # which bot?
    await team.start(expect=404, ownerKind="bot", botId=str(uuid.uuid4()))
    await team.sign_in("sara@acme.dev")
    await team.start(expect=403, ownerKind="org")
    await team.start(expect=403, ownerKind="bot", botId=team.bot_id)  # Ali made Scout
    await team.start(ownerKind="member")


# Finish: the callback


async def test_connecting_gmail_stores_the_account_and_sends_the_browser_back(team: Team) -> None:
    query = await team.authorize()
    back = await team.callback(state=query["state"], code="4/CODE-ONE", scope=MODIFY)
    assert back == {"result": "connected", "connector": "gmail"}

    (token_form,) = team.google.forms("/token")
    assert token_form["grant_type"] == "authorization_code"
    assert token_form["code"] == "4/CODE-ONE"
    assert token_form["redirect_uri"] == "https://api.botdesk.test/api/v1/oauth/callback"
    assert (token_form["client_id"], token_form["client_secret"]) == (CLIENT_ID, CLIENT_SECRET)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(token_form["code_verifier"].encode()).digest())
    assert challenge.decode().rstrip("=") == query["code_challenge"]  # PKCE: the verifier matches
    (profile,) = team.google.to("/gmail/v1/users/me/profile")
    assert profile.headers["authorization"] == "Bearer ya29.ACCESS-1"

    (gmail,) = await team.connections()
    assert gmail["connectorId"] == "gmail" and gmail["authType"] == "oauth2"
    assert gmail["accountLabel"] == "Ali@Acme.dev" and gmail["ownerKind"] == "member"
    assert gmail["scopes"] == [MODIFY] and gmail["status"] == "active"
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, uuid.UUID(gmail["id"]))
        assert row is not None and row.account_ref == "ali@acme.dev"
        assert row.access_expires_at is not None and row.access_expires_at > utcnow() + timedelta(minutes=50)
        assert await db.scalar(select(OAuthFlow)) is None  # used up
    assert await team.actions() == ["connection.created"]


async def test_a_bot_owned_and_an_org_owned_account(team: Team) -> None:
    assert (await team.connect_gmail(ownerKind="bot", botId=team.bot_id))["result"] == "connected"
    team.google.granted = None  # no `scope` in the answer: what was asked for
    assert (await team.connect_gmail(ownerKind="org", access="read"))["result"] == "connected"
    bot, org = await team.connections()
    assert (bot["ownerKind"], bot["ownerBotId"]) == ("bot", team.bot_id)
    assert (org["ownerKind"], org["ownerUserId"], org["scopes"]) == ("org", None, [READ])


async def test_the_person_cancelling_at_google_is_denied_and_the_state_is_used_up(team: Team) -> None:
    query = await team.authorize()
    back = await team.callback(state=query["state"], error="access_denied")
    assert back == {"result": "error", "code": "denied"}
    assert await team.callback(state=query["state"], code="4/LATE") == {"result": "error", "code": "expired"}
    assert team.google.to("/token") == []


async def test_a_state_works_once(team: Team) -> None:
    query = await team.authorize()
    assert (await team.callback(state=query["state"], code="4/CODE-ONE"))["result"] == "connected"
    assert await team.callback(state=query["state"], code="4/CODE-ONE") == {"result": "error", "code": "expired"}
    assert len(team.google.to("/token")) == 1


async def test_an_unknown_or_missing_state_is_expired(team: Team) -> None:
    assert await team.callback(state="made-up", code="4/X") == {"result": "error", "code": "expired"}
    assert await team.callback(code="4/X") == {"result": "error", "code": "expired"}


async def test_a_state_older_than_ten_minutes_is_expired(team: Team) -> None:
    query = await team.authorize()
    async with team.app.state.sessionmaker() as db:
        await db.execute(update(OAuthFlow).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "expired"}
    assert team.google.to("/token") == []


async def test_a_state_started_by_someone_else_is_expired_and_stays_theirs(team: Team) -> None:
    query = await team.authorize()  # Ali's
    await team.sign_in("sara@acme.dev")
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "expired"}
    await team.sign_in("ali@acme.dev")
    assert (await team.callback(state=query["state"], code="4/X"))["result"] == "connected"


async def test_no_session_is_signed_out(team: Team) -> None:
    query = await team.authorize()
    team.client.cookies.clear()
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "signed-out"}


async def test_a_client_removed_after_the_start_is_not_configured(team: Team) -> None:
    query = await team.authorize()
    team.app.state.settings.google_oauth_client_id = ""
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "not-configured"}
    assert team.google.to("/token") == []


async def test_someone_who_left_the_organization_is_forbidden(team: Team) -> None:
    await team.sign_in("sara@acme.dev")
    query = await team.authorize()
    async with team.app.state.sessionmaker() as db:
        await db.execute(delete(Membership).where(Membership.role == "member"))
        await db.commit()
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "forbidden"}
    assert team.google.to("/token") == []


async def test_an_admin_made_a_member_mid_flow_is_forbidden_an_org_account(team: Team) -> None:
    query = await team.authorize(ownerKind="org")
    async with team.app.state.sessionmaker() as db:
        await db.execute(update(Membership).where(Membership.role == "owner").values(role="member"))
        await db.commit()
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "forbidden"}


async def test_google_refusing_the_code_or_the_profile_is_failed_without_its_words(team: Team) -> None:
    team.google.token_status, team.google.token_error = 400, "invalid_grant"
    query = await team.authorize()
    response = await team.client.get(CALLBACK, params={"state": query["state"], "code": "4/BAD", "iss": ISSUER})
    assert response.headers["location"] == f"{WEB}/apps/callback?result=error&code=failed"
    team.google.token_status = 200
    team.google.profile_status = 500
    query = await team.authorize()
    assert await team.callback(state=query["state"], code="4/X") == {"result": "error", "code": "failed"}
    assert await team.connections() == []


async def test_reconnecting_updates_the_same_connection(team: Team) -> None:
    await team.connect_gmail(access="read")
    async with team.app.state.sessionmaker() as db:  # Google said the sign-in was revoked
        await db.execute(update(Connection).values(status="needs_reconnect", status_reason="Revoked at Google."))
        await db.commit()
    team.google.email = "ali@acme.DEV"  # the same mailbox
    await team.connect_gmail(access="full")
    (gmail,) = await team.connections()
    assert gmail["status"] == "active" and gmail["statusReason"] is None
    assert gmail["scopes"] == [MODIFY]
    assert await team.actions() == ["connection.created", "connection.reconnected"]


async def test_a_scope_left_unticked_is_not_granted(team: Team) -> None:
    team.google.granted = "openid"  # the person unticked Gmail on Google's consent screen
    assert (await team.connect_gmail())["result"] == "connected"
    (gmail,) = await team.connections()
    assert gmail["scopes"] == ["openid"]  # the toolset offers no Gmail tool through it


async def test_no_secret_reaches_a_response_a_log_line_or_a_redirect(
    team: Team, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    seen: list[str] = []
    url = (await team.start())["authorizeUrl"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    response = await team.client.get(CALLBACK, params={"state": state, "code": "4/CODE-SECRET", "iss": ISSUER})
    seen += [response.headers["location"], response.text]
    team.google.token_status, team.google.token_error = 400, "invalid_grant"
    url = (await team.start())["authorizeUrl"]
    response = await team.client.get(
        CALLBACK, params={"state": parse_qs(urlsplit(url).query)["state"][0], "code": "4/C2", "iss": ISSUER}
    )
    seen += [response.headers["location"], (await team.client.get(f"{team.org}/connections")).text]
    (verifier,) = {form["code_verifier"] for form in team.google.forms("/token")[:1]}
    async with team.app.state.sessionmaker() as db:
        details = [str(entry.details) for entry in await db.scalars(select(AuditEntry))]
    everything = "\n".join([*seen, caplog.text, *details])
    for secret in ("ya29.ACCESS-1", "1//REFRESH-1", "4/CODE-SECRET", verifier, CLIENT_SECRET, "expired or revoked"):
        assert secret not in everything, secret
    assert response.headers.get("referrer-policy") == "no-referrer"


# Refresh


def _gmail_tool() -> RegisteredTool:
    async def handler(_args: NoArgs, _ctx: ToolContext) -> dict[str, Any]:
        return {}

    spec = ToolSpec(
        name="profile", title="Profile", description="Who.", args_model=NoArgs, risk="read", handler=handler
    )
    return RegisteredTool("gmail", spec)


async def _gmail_id(team: Team) -> uuid.UUID:
    (gmail,) = [c for c in await team.connections() if c["connectorId"] == "gmail"]
    return uuid.UUID(gmail["id"])


async def _expire(team: Team, connection_id: uuid.UUID) -> None:
    async with team.app.state.sessionmaker() as db:
        await db.execute(
            update(Connection)
            .where(Connection.id == connection_id)
            .values(access_expires_at=utcnow() + timedelta(seconds=30))
        )
        await db.commit()


async def _call_profile(team: Team, connection_id: uuid.UUID) -> str:
    """A tool call on the connection: the Authorization header Gmail saw, or the refusal."""
    runs: RunManager = team.app.state.runs
    run = RunRef(
        run_id=uuid.uuid4(), org_id=uuid.UUID(team.org_id), thread_id=uuid.uuid4(), bot_id=uuid.UUID(team.bot_id)
    )
    before = len(team.google.to("/gmail/v1/users/me/profile"))
    async with runs.tool_access.open(
        run, _gmail_tool(), "call-1", connection_id=connection_id, timeout_seconds=5
    ) as access:
        try:
            await access.http.request("GET", PROFILE)
        except Exception as error:
            return str(error)
    return team.google.to("/gmail/v1/users/me/profile")[before].headers["authorization"]


async def test_a_token_about_to_expire_is_refreshed_before_the_call(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-1"  # still fresh: no refresh
    assert len(team.google.to("/token")) == 1
    await _expire(team, connection_id)
    team.google.send_refresh_token = False  # Google often keeps the refresh token as it was
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-2"
    refresh = team.google.forms("/token")[1]
    assert refresh == {
        "grant_type": "refresh_token",
        "refresh_token": "1//REFRESH-1",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    await _expire(team, connection_id)
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-3"
    assert team.google.forms("/token")[2]["refresh_token"] == "1//REFRESH-1"  # the old one was kept
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, connection_id)
        assert row is not None and row.refresh_lease_until is None and row.last_refreshed_at is not None


async def test_invalid_grant_marks_the_connection_needs_reconnect(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)
    team.google.token_status, team.google.token_error = 400, "invalid_grant"
    refusal = await _call_profile(team, connection_id)
    assert refusal == "Ali@Acme.dev needs reconnecting (Connect apps)."
    (gmail,) = await team.connections()
    assert gmail["status"] == "needs_reconnect" and gmail["statusReason"]
    assert "expired or revoked" not in gmail["statusReason"]  # Google's words stay out
    assert await team.actions() == ["connection.created", "connection.needs_reconnect"]
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, connection_id)
        assert row is not None and row.refresh_lease_until is None


async def test_reconnecting_after_a_refresh_token_was_kept_still_refreshes(team: Team) -> None:
    await team.connect_gmail()
    team.google.send_refresh_token = False  # a reconnect that brings no new refresh token
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-3"
    assert team.google.forms("/token")[2]["refresh_token"] == "1//REFRESH-1"


# Disconnect


async def test_disconnecting_revokes_at_google_after_forgetting_the_token(team: Team) -> None:
    await team.connect_gmail(ownerKind="org")
    connection_id = await _gmail_id(team)
    async with team.app.state.sessionmaker() as db:
        db.add(
            BotTool(
                org_id=uuid.UUID(team.org_id),
                bot_id=uuid.UUID(team.bot_id),
                plugin_id="gmail",
                connection_id=connection_id,
            )
        )
        await db.commit()
    response = await team.client.delete(f"{team.org}/connections/{connection_id}")
    assert response.status_code == 204, response.text
    (revoke,) = team.google.forms("/revoke")
    assert revoke == {"token": "1//REFRESH-1"}
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, connection_id)
        assert row is not None and (row.status, row.encrypted_secret) == ("revoked", None)
        binding = await db.scalar(select(BotTool).where(BotTool.plugin_id == "gmail"))
        assert binding is not None and binding.connection_id is None


async def test_google_failing_to_revoke_still_disconnects(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    team.google.revoke_status = 503
    assert (await team.client.delete(f"{team.org}/connections/{connection_id}")).status_code == 204
    (gmail,) = await team.connections()
    assert gmail["status"] == "revoked"


async def test_a_callback_naming_another_issuer_is_failed(team: Team) -> None:
    query = await team.authorize()
    back = await team.callback(state=query["state"], code="4/X", iss="https://evil.example")
    assert back == {"result": "error", "code": "failed"}
    assert team.google.to("/token") == []
    query = await team.authorize()
    back = await team.callback(state=query["state"], code="4/X", iss="https://accounts.google.com")
    assert back["result"] == "connected"


async def test_disconnecting_answers_204_even_when_the_guard_refuses_the_revoke(team: Team) -> None:
    async def nowhere(_host: str) -> list[str]:
        raise OSError("no DNS")

    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    team.app.state.oauth.transport = GuardedTransport(allow_private=False, resolve=nowhere)
    response = await team.client.delete(f"{team.org}/connections/{connection_id}")
    assert response.status_code == 204, response.text
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, connection_id)
        assert row is not None and (row.status, row.encrypted_secret) == ("revoked", None)


# Refresh failures


async def _lease(team: Team, connection_id: uuid.UUID) -> Any:
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, connection_id, populate_existing=True)
        assert row is not None
        return row.refresh_lease_until


async def test_a_guard_refusing_the_token_endpoint_goes_on_with_the_old_token(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)
    team.google.token_fault = UnsafeUrl("We couldn't find oauth2.googleapis.com.")
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-1"
    lease = await _lease(team, connection_id)
    assert lease is None or lease <= utcnow() + oauth_flow.BACKOFF  # backing off, not holding the lease
    (gmail,) = await team.connections()
    assert gmail["status"] == "active"


async def test_a_bug_inside_a_refresh_gives_the_lease_back(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)
    team.google.token_fault = RuntimeError("a bug")
    with pytest.raises(RuntimeError):
        await _call_profile(team, connection_id)
    assert await _lease(team, connection_id) is None
    team.google.token_fault = None
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-2"  # the next call refreshes


async def test_a_slow_token_endpoint_is_given_up_on_before_the_lease_ends(
    team: Team, monkeypatch: pytest.MonkeyPatch
) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)
    monkeypatch.setattr(oauth_flow, "TOKEN_CALL_BUDGET", timedelta(seconds=0.2))
    team.google.token_delay = 2.0
    started = utcnow()
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-1"
    assert utcnow() - started < timedelta(seconds=1.5)
    assert oauth_flow.TOKEN_CALL_BUDGET < oauth_flow.LEASE - oauth_flow.BACKOFF


async def test_a_failed_refresh_backs_off_instead_of_every_call_retrying(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)
    team.google.token_status = 503
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-1"
    started = utcnow()
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-1"  # no second request, no wait
    assert utcnow() - started < timedelta(seconds=1)
    assert len(team.google.to("/token")) == 2  # the code exchange and ONE refresh
    async with team.app.state.sessionmaker() as db:  # the backoff is over
        await db.execute(update(Connection).values(refresh_lease_until=utcnow() - timedelta(seconds=1)))
        await db.commit()
    team.google.token_status = 200
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-2"


async def test_a_refresh_finishing_after_a_disconnect_leaves_the_row_revoked(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    await _expire(team, connection_id)

    async def disconnect() -> None:  # while the refresh waits for Google
        team.google.on_token = None
        response = await team.client.delete(f"{team.org}/connections/{connection_id}")
        assert response.status_code == 204, response.text

    team.google.on_token = disconnect
    refusal = await _call_profile(team, connection_id)
    assert refusal == "Ali@Acme.dev was disconnected. Connect it again in Connect apps."
    assert len(team.google.to("/token")) == 2  # the refresh did get a token: it was thrown away
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, connection_id, populate_existing=True)
        assert row is not None and (row.status, row.encrypted_secret) == ("revoked", None)
        assert row.refresh_lease_until is None


# The callback's `iss` (RFC 9207)


async def test_a_google_callback_without_iss_is_failed(team: Team) -> None:
    query = await team.authorize()
    back = await team.callback(state=query["state"], code="4/X", iss=None)
    assert back == {"result": "error", "code": "failed"}
    assert team.google.to("/token") == []


def test_only_a_provider_that_advertises_iss_requires_it() -> None:
    assert oauth_flow.ISSUERS == {"google": "https://accounts.google.com"}  # its discovery document says so


# `expires_in`


@pytest.mark.parametrize(
    ("expires_in", "seconds"),
    [(3599, 3599), (3599.0, 3599), ("3599", 3599), ("3599.5", 3599), (MISSING, 3600), ("soon", 3600), (-5, 3600)],
)
async def test_the_token_lifetime_is_read_from_any_number_google_sends(expires_in: Any, seconds: int) -> None:
    async with acme() as team:
        team.google.expires_in = expires_in
        before = utcnow()
        assert (await team.connect_gmail())["result"] == "connected"
        async with team.app.state.sessionmaker() as db:
            row = await db.get(Connection, await _gmail_id(team))
        assert row is not None and row.access_expires_at is not None
        lifetime = row.access_expires_at - before
        assert timedelta(seconds=seconds - 5) < lifetime <= timedelta(seconds=seconds + 1)


# Fake Google servers only in tests


async def test_fake_google_addresses_are_ignored_outside_the_test_environment() -> None:
    development = GOOGLE_SETTINGS.model_copy(
        update={
            "environment": "development",
            "google_oauth_base_url": "http://127.0.0.1:9999",
            "gmail_api_base_url": "http://127.0.0.1:9998",
        }
    )
    async with acme(development) as team:
        url = (await team.start())["authorizeUrl"]
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        assert (await team.callback(state=query["state"], code="4/X"))["result"] == "connected"
        assert {(r.url.scheme, r.url.host) for r in team.google.requests} == {
            ("https", "oauth2.googleapis.com"),
            ("https", "gmail.googleapis.com"),
        }


async def test_connectors_never_show_the_google_client(team: Team) -> None:
    response = await team.client.get(f"{team.org}/connectors")
    assert CLIENT_ID not in response.text and CLIENT_SECRET not in response.text
    (gmail,) = [c for c in response.json() if c["id"] == "gmail"]
    assert set(gmail) == {
        "id",
        "name",
        "description",
        "version",
        "authType",
        "setup",
        "accessLevels",
        "defaultAccess",
        "tools",
    }


# Reconnecting


async def _secret(team: Team, connection_id: str) -> tuple[str, str | None]:
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, uuid.UUID(connection_id), populate_existing=True)
        assert row is not None
        return row.status, row.encrypted_secret


async def test_reconnecting_leaves_other_owners_of_the_same_account_alone(team: Team) -> None:
    await team.connect_gmail(ownerKind="org")
    await team.sign_in("sara@acme.dev")
    await team.connect_gmail()  # Sara's own connection to the same mailbox
    await team.sign_in("ali@acme.dev")
    await team.connect_gmail()
    org, sara, ali = await team.connections()
    assert (org["ownerKind"], sara["ownerKind"], ali["ownerKind"]) == ("org", "member", "member")
    before = {c["id"]: await _secret(team, c["id"]) for c in (org, sara)}
    await team.connect_gmail()  # Ali reconnects his own
    assert len(await team.connections()) == 3
    assert {c["id"]: await _secret(team, c["id"]) for c in (org, sara)} == before
    assert (await team.actions()).count("connection.reconnected") == 1


async def test_connecting_a_disconnected_account_again_brings_the_row_back(team: Team) -> None:
    await team.connect_gmail()
    connection_id = await _gmail_id(team)
    assert (await team.client.delete(f"{team.org}/connections/{connection_id}")).status_code == 204
    assert (await team.connect_gmail())["result"] == "connected"
    (gmail,) = await team.connections()
    assert gmail["id"] == str(connection_id) and gmail["status"] == "active" and gmail["statusReason"] is None
    await _expire(team, connection_id)
    assert await _call_profile(team, connection_id) == "Bearer ya29.ACCESS-3"
    assert team.google.forms("/token")[2]["refresh_token"] == "1//REFRESH-2"  # the new sign-in's
    assert await team.actions() == ["connection.created", "connection.disconnected", "connection.reconnected"]


# Access log


def test_the_access_log_hides_the_callback_query() -> None:
    def access_line(path: str) -> str:
        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            "",
            0,
            '%s - "%s %s HTTP/%s" %d',
            ("1.2.3.4:5", "GET", path, "1.1", 303),
            None,
        )
        assert RedactOAuthCallback().filter(record)
        return record.getMessage()

    line = access_line("/api/v1/oauth/callback?state=STATE-SECRET&code=4/CODE-SECRET&iss=x")
    assert "STATE-SECRET" not in line and "CODE-SECRET" not in line
    assert "/api/v1/oauth/callback?<redacted>" in line
    assert "/api/v1/orgs?x=1" in access_line("/api/v1/orgs?x=1")  # everything else as it was
    assert any(isinstance(f, RedactOAuthCallback) for f in logging.getLogger("uvicorn.access").filters)

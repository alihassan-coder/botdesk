"""Signing in to an MCP server with OAuth 2.1 (slice 7.3, ADR 0012 §3), end to end on SQLite.

The MCP server is real (the SDK's server side on 127.0.0.1, behind a bearer check that answers
401 with a `WWW-Authenticate` challenge). The authorization server is fake (`FakeAuthServer`,
through `httpx.MockTransport`): Protected Resource Metadata, RFC 8414 metadata, dynamic
registration and a token endpoint that checks PKCE and the `resource`. The browser's trip to the
sign-in page is played by the test; the callback is the real `/api/v1/oauth/callback`.
"""

import base64
import hashlib
import json
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select, update
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.database import utcnow
from src.mcp.client import McpNetwork
from src.mcp.oauth import McpSignInError, parse_challenge
from src.models import Connection, McpServer, Membership
from src.runtime.runner import RunManager
from src.services.mcp_server_service import McpRuntime
from tests.test_mcp_client import _free_port
from tests.test_mcp_servers import _bind_and_ask, _call
from tests.test_oauth import Team, acme

ISSUER = "https://auth.example"
SECRET_MARK = "zq9tok"  # every token and client secret here contains it: none may leak


# The MCP server: tools only for a bearer token the authorization server issued.


@dataclass
class Guarded:
    port: int
    accepted: set[str] = field(default_factory=set)
    seen: list[str] = field(default_factory=list)  # Authorization headers that reached it

    @property
    def origin(self) -> str:
        return f"http://mcp.test:{self.port}"

    @property
    def url(self) -> str:
        return f"{self.origin}/mcp"


@pytest.fixture(scope="module")
def guarded() -> Iterator[Guarded]:
    server = MCPServer("botdesk-7-3")

    @server.tool(description="Echoes text.", structured_output=False)
    def echo(text: str) -> str:
        return f"echo: {text}"

    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    state = Guarded(port=_free_port())

    def bearer_only(inner: ASGIApp) -> ASGIApp:
        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
                auth = headers.get("authorization", "")
                state.seen.append(auth)
                if auth.removeprefix("Bearer ") not in state.accepted:
                    challenge = (
                        f'Bearer resource_metadata="{state.origin}/.well-known/oauth-protected-resource/mcp", '
                        'scope="tracker.read"'
                    )
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 401,
                            "headers": [(b"www-authenticate", challenge.encode())],
                        }
                    )
                    await send({"type": "http.response.body", "body": b""})
                    return
            await inner(scope, receive, send)

        return wrapped

    uv = uvicorn.Server(uvicorn.Config(bearer_only(app), host="127.0.0.1", port=state.port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        assert time.monotonic() < deadline, "test MCP server didn't start"
        time.sleep(0.05)
    yield state
    uv.should_exit = True
    thread.join(timeout=5)


# The authorization server.


@dataclass
class FakeAuthServer:
    mcp: Guarded
    registrations: list[dict[str, Any]] = field(default_factory=list)
    token_forms: list[dict[str, str]] = field(default_factory=list)
    token_headers: list[dict[str, str]] = field(default_factory=list)
    codes: dict[str, str] = field(default_factory=dict)  # code → PKCE challenge
    refresh_tokens: set[str] = field(default_factory=set)
    refuse_refresh: bool = False
    issued: int = 0

    def sign_in(self, authorize_url: str) -> tuple[str, str]:
        """The person signs in on the authorization server's page: (state, code) come back."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(authorize_url).query).items()}
        code = f"code-{len(self.codes)}"
        self.codes[code] = query["code_challenge"]
        return query["state"], code

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{self.mcp.origin}/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(
                200,
                json={
                    "resource": self.mcp.url,
                    "authorization_servers": [ISSUER],
                    "scopes_supported": ["tracker.read"],
                },
            )
        if url == f"{ISSUER}/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "registration_endpoint": f"{ISSUER}/register",
                    "code_challenge_methods_supported": ["S256"],
                    "authorization_response_iss_parameter_supported": True,
                },
            )
        if url == f"{ISSUER}/register":
            self.registrations.append(json.loads(request.content))
            return httpx.Response(201, json={"client_id": "dyn-client"})
        if url == f"{ISSUER}/token":
            return self._token(request)
        return httpx.Response(404)

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_forms.append(form)
        self.token_headers.append(dict(request.headers))
        if form.get("resource") != self.mcp.url:
            return httpx.Response(400, json={"error": "invalid_target"})
        if form["grant_type"] == "authorization_code":
            challenge = self.codes.pop(form["code"], None)
            verified = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).decode()
            if challenge is None or verified.rstrip("=") != challenge:
                return httpx.Response(400, json={"error": "invalid_grant"})
        elif self.refuse_refresh or form["refresh_token"] not in self.refresh_tokens:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "token revoked"})
        self.issued += 1
        access, refresh = f"mcp-access-{SECRET_MARK}-{self.issued}", f"mcp-refresh-{SECRET_MARK}-{self.issued}"
        self.mcp.accepted.add(access)
        self.refresh_tokens.add(refresh)
        body = {"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": 3600}
        return httpx.Response(200, json=body)


async def _anywhere(host: str) -> list[str]:
    return ["127.0.0.1"]


TEST_NETWORK = McpNetwork(allow_private=True, allow_http=True, resolve=_anywhere)


@asynccontextmanager
async def acme_with_sign_in(guarded: Guarded) -> AsyncIterator[tuple[Team, FakeAuthServer]]:
    guarded.accepted.clear()
    fake = FakeAuthServer(mcp=guarded)
    async with acme() as team:
        runs: RunManager = team.app.state.runs
        runs.mcp = replace(runs.mcp, network=TEST_NETWORK, oauth_transport=httpx.MockTransport(fake.handle))
        yield team, fake


async def _callback(team: Team, **params: str) -> dict[str, str]:
    response = await team.client.get("/api/v1/oauth/callback", params=params)
    assert response.status_code == 303, response.text
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}


async def _signed_in(team: Team, fake: FakeAuthServer, guarded: Guarded, **body: Any) -> dict[str, Any]:
    added = await team.client.post(f"{team.org}/mcp-servers", json={"name": "Tracker", "url": guarded.url, **body})
    assert added.status_code == 201, added.text
    state, code = fake.sign_in(added.json()["authorizeUrl"])
    assert await _callback(team, state=state, code=code, iss=ISSUER) == {
        "result": "connected",
        "connector": added.json()["pluginId"],
    }
    (server,) = (await team.client.get(f"{team.org}/mcp-servers")).json()
    return cast(dict[str, Any], server)


# Adding and signing in


async def test_a_server_that_answers_401_is_signed_in_to_and_its_tools_listed(
    guarded: Guarded, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    async with acme_with_sign_in(guarded) as (team, fake):
        added = await team.client.post(f"{team.org}/mcp-servers", json={"name": "Tracker", "url": guarded.url})

        assert added.status_code == 201, added.text
        body = added.json()
        assert (body["authKind"], body["status"], body["tools"]) == ("oauth", "needs_sign_in", [])
        authorize = urlsplit(body["authorizeUrl"])
        query = {k: v[0] for k, v in parse_qs(authorize.query).items()}
        assert f"{authorize.scheme}://{authorize.netloc}{authorize.path}" == f"{ISSUER}/authorize"
        assert query["client_id"] == "dyn-client"  # registered dynamically: no client id was given
        assert query["code_challenge_method"] == "S256" and query["resource"] == guarded.url
        assert query["scope"] == "tracker.read"  # from the 401's challenge
        assert query["redirect_uri"].endswith("/api/v1/oauth/callback")
        assert fake.registrations[0]["redirect_uris"] == [query["redirect_uri"]]
        assert fake.registrations[0]["token_endpoint_auth_method"] == "none"

        state, code = fake.sign_in(body["authorizeUrl"])
        assert await _callback(team, state=state, code=code, iss=ISSUER) == {
            "result": "connected",
            "connector": body["pluginId"],
        }

        (server,) = (await team.client.get(f"{team.org}/mcp-servers")).json()
        assert server["status"] == "active" and [t["serverName"] for t in server["tools"]] == ["echo"]
        assert fake.token_forms[0]["grant_type"] == "authorization_code"
        assert f"Bearer mcp-access-{SECRET_MARK}-1" in guarded.seen
        async with team.app.state.sessionmaker() as db:
            connection = await db.scalar(select(Connection).where(Connection.connector_id == body["pluginId"]))
            row = await db.scalar(select(McpServer))
        assert connection is not None and connection.owner_kind == "org" and connection.status == "active"
        assert connection.encrypted_secret and SECRET_MARK not in connection.encrypted_secret
        assert row is not None and SECRET_MARK not in json.dumps(row.oauth)
        # No token in an API answer or a log line.
        assert SECRET_MARK not in (await team.client.get(f"{team.org}/mcp-servers")).text
        assert SECRET_MARK not in (await team.client.get(f"{team.org}/connections")).text
        assert SECRET_MARK not in caplog.text


async def test_a_pre_registered_client_skips_registration_and_its_secret_stays_sealed(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        secret = f"client-{SECRET_MARK}"
        server = await _signed_in(team, fake, guarded, oauthClientId="pasted-client", oauthClientSecret=secret)

        assert fake.registrations == []
        assert fake.token_forms[0]["client_id"] == "pasted-client"
        assert fake.token_forms[0]["client_secret"] == secret
        assert SECRET_MARK not in json.dumps(server)
        async with team.app.state.sessionmaker() as db:
            row = await db.scalar(select(McpServer))
        assert row is not None and row.encrypted_auth and secret not in row.encrypted_auth
        assert SECRET_MARK not in json.dumps(row.oauth)

        half = await team.client.post(
            f"{team.org}/mcp-servers", json={"name": "X", "url": guarded.url, "oauthClientSecret": "s"}
        )
        assert half.status_code == 422


# Using and refreshing the token


async def _expire_sign_in(team: Team, plugin_id: str) -> None:
    async with team.app.state.sessionmaker() as db:
        await db.execute(
            update(Connection).where(Connection.connector_id == plugin_id).values(access_expires_at=utcnow())
        )
        await db.commit()


async def test_a_call_sends_the_token_and_an_expiring_one_is_refreshed_first(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        server = await _signed_in(team, fake, guarded)
        plugin = server["pluginId"]
        run = await _bind_and_ask(team, plugin)
        await _expire_sign_in(team, plugin)

        _, outcome = await _call(team, run, f"{plugin}__echo", {"text": "hi"}, level="autonomous")

        assert "echo: hi" in outcome.text
        refresh = fake.token_forms[-1]
        assert refresh["grant_type"] == "refresh_token" and refresh["refresh_token"] == f"mcp-refresh-{SECRET_MARK}-1"
        assert refresh["resource"] == guarded.url
        assert guarded.seen[-1] == f"Bearer mcp-access-{SECRET_MARK}-2"


async def test_a_refused_refresh_needs_reconnecting_and_reconnect_signs_in_again(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        server = await _signed_in(team, fake, guarded)
        plugin = server["pluginId"]
        run = await _bind_and_ask(team, plugin)
        await _expire_sign_in(team, plugin)
        fake.refuse_refresh = True

        _, outcome = await _call(team, run, f"{plugin}__echo", {"text": "hi"}, level="autonomous")

        assert "needs signing in again" in outcome.text
        (listed,) = (await team.client.get(f"{team.org}/mcp-servers")).json()
        assert listed["status"] == "needs_reconnect"
        assert "connection.needs_reconnect" in await team.actions()

        reconnect = await team.client.post(f"{team.org}/mcp-servers/{server['id']}/sign-in")
        assert reconnect.status_code == 200, reconnect.text
        state, code = fake.sign_in(reconnect.json()["authorizeUrl"])
        assert (await _callback(team, state=state, code=code, iss=ISSUER))["result"] == "connected"
        (listed,) = (await team.client.get(f"{team.org}/mcp-servers")).json()
        assert listed["status"] == "active"
        async with team.app.state.sessionmaker() as db:
            rows = list(await db.scalars(select(Connection).where(Connection.connector_id == plugin)))
        assert len(rows) == 1 and rows[0].status == "active"  # the same connection, reconnected
        _, works = await _call(team, run, f"{plugin}__echo", {"text": "again"}, level="autonomous")
        assert "echo: again" in works.text


async def test_a_token_the_server_stops_accepting_needs_reconnecting(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        server = await _signed_in(team, fake, guarded)
        plugin = server["pluginId"]
        run = await _bind_and_ask(team, plugin)
        guarded.accepted.clear()  # revoked on the server's side

        _, outcome = await _call(team, run, f"{plugin}__echo", {"text": "hi"}, level="autonomous")

        assert "needs signing in" in outcome.text
        (listed,) = (await team.client.get(f"{team.org}/mcp-servers")).json()
        assert listed["status"] == "needs_reconnect"


# Who may, and what the callback refuses


async def test_only_owners_and_admins_sign_in_to_a_server(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        added = (await team.client.post(f"{team.org}/mcp-servers", json={"name": "Tracker", "url": guarded.url})).json()
        state, code = fake.sign_in(added["authorizeUrl"])
        await team.sign_in("sara@acme.dev")

        assert (await team.client.post(f"{team.org}/mcp-servers/{added['id']}/sign-in")).status_code == 403
        mine = await team.client.post(f"{team.org}/mcp-servers", json={"name": "M", "url": guarded.url, "signIn": True})
        assert mine.status_code == 403
        # Ali's state isn't Sara's.
        assert (await _callback(team, state=state, code=code, iss=ISSUER)) == {"result": "error", "code": "expired"}


async def test_an_admin_demoted_mid_sign_in_is_forbidden(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        added = (await team.client.post(f"{team.org}/mcp-servers", json={"name": "Tracker", "url": guarded.url})).json()
        state, code = fake.sign_in(added["authorizeUrl"])
        async with team.app.state.sessionmaker() as db:  # Ali loses the role while on the sign-in page
            await db.execute(
                update(Membership).where(Membership.org_id == uuid.UUID(team.org_id)).values(role="member")
            )
            await db.commit()

        assert await _callback(team, state=state, code=code, iss=ISSUER) == {"result": "error", "code": "forbidden"}
        assert fake.token_forms == []  # refused before the code was used


async def test_a_callback_with_a_missing_or_other_issuer_fails(guarded: Guarded) -> None:
    async with acme_with_sign_in(guarded) as (team, fake):
        added = (await team.client.post(f"{team.org}/mcp-servers", json={"name": "Tracker", "url": guarded.url})).json()
        state, code = fake.sign_in(added["authorizeUrl"])
        assert await _callback(team, state=state, code=code, iss="https://evil.example") == {
            "result": "error",
            "code": "failed",
        }
        again = (await team.client.post(f"{team.org}/mcp-servers/{added['id']}/sign-in")).json()
        state, code = fake.sign_in(again["authorizeUrl"])
        assert (await _callback(team, state=state, code=code))["code"] == "failed"  # it promised `iss`
        assert fake.token_forms == []


# Discovery and the SSRF guard, without a server


async def _public(host: str) -> list[str]:
    return ["93.184.216.34"]


def _runtime(handler: Any, *, allow_private: bool = False) -> McpRuntime:
    return McpRuntime(
        vault=cast(Any, None),
        network=McpNetwork(allow_private=allow_private, resolve=_public),
        oauth_transport=httpx.MockTransport(handler),
    )


def _metadata(**overrides: Any) -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "code_challenge_methods_supported": ["S256"],
        **overrides,
    }


async def _discover(handler: Any, url: str = "https://mcp.example/mcp", **runtime: Any) -> dict[str, Any]:
    from src.mcp.oauth import Challenge, discover

    rt = _runtime(handler, **runtime)
    async with rt.http() as http:
        return await discover(http, url, Challenge(), rt.guard)


def _serving(prm: dict[str, Any] | None, metadata: dict[str, Any]) -> Any:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "oauth-protected-resource" in path:
            return httpx.Response(200, json=prm) if prm is not None else httpx.Response(404)
        if path == "/.well-known/oauth-authorization-server":
            return httpx.Response(200, json=metadata)
        return httpx.Response(404)

    return handle


PRM = {"resource": "https://mcp.example/mcp", "authorization_servers": [ISSUER]}


async def test_discovery_finds_the_authorization_server_and_the_resource() -> None:
    found = await _discover(_serving(PRM, _metadata(registration_endpoint=f"{ISSUER}/register")))

    assert found["issuer"] == ISSUER and found["resource"] == "https://mcp.example/mcp"
    assert found["tokenEndpoint"] == f"{ISSUER}/token" and found["registrationEndpoint"] == f"{ISSUER}/register"


async def test_a_server_without_metadata_is_its_own_authorization_server() -> None:
    found = await _discover(_serving(None, _metadata(issuer="https://mcp.example")))

    assert found["issuer"] == "https://mcp.example" and found["resource"] == "https://mcp.example/mcp"


@pytest.mark.parametrize(
    ("prm", "metadata", "message"),
    [
        ({**PRM, "authorization_servers": ["https://10.0.0.7"]}, _metadata(), "private network"),
        (PRM, _metadata(token_endpoint="http://auth.example/token"), "must be public https"),
        (PRM, _metadata(token_endpoint="https://192.168.1.4/token"), "private network"),
        (PRM, _metadata(issuer="https://other.example"), "another one"),
        (PRM, _metadata(code_challenge_methods_supported=["plain"]), "PKCE"),
        ({**PRM, "resource": "https://other.example/mcp"}, _metadata(), "another address"),
    ],
)
async def test_discovery_refuses_unsafe_or_inconsistent_metadata(
    prm: dict[str, Any], metadata: dict[str, Any], message: str
) -> None:
    with pytest.raises(McpSignInError, match=message):
        await _discover(_serving(prm, metadata))


async def test_a_private_mcp_server_address_is_refused_unless_allowed() -> None:
    with pytest.raises(McpSignInError, match="private network"):
        await _discover(_serving(PRM, _metadata()), "https://10.0.0.5/mcp")
    found = await _discover(
        _serving({**PRM, "resource": "https://10.0.0.5/mcp"}, _metadata()), "https://10.0.0.5/mcp", allow_private=True
    )
    assert found["resource"] == "https://10.0.0.5/mcp"


def test_the_challenge_is_read_from_www_authenticate() -> None:
    challenge = parse_challenge(
        'Bearer error="invalid_token", resource_metadata="https://m.example/.well-known/x", scope="a b"'
    )

    assert challenge.resource_metadata == "https://m.example/.well-known/x"
    assert (challenge.scope, challenge.error) == ("a b", "invalid_token")
    assert parse_challenge('Basic realm="x"').resource_metadata is None
    assert parse_challenge(None).scope is None

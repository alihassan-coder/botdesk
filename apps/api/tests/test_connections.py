"""Connections (ADR 0010, slices 5.1-5.2), on SQLite: the credential vault, who may create, see and
disconnect which connection (§3), the audit log, and the demo API-key tool end to end through the
run's toolset and the tool pipeline. Requests tools make are answered by httpx.MockTransport."""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from src.core.config import Settings
from src.core.secrets import CONNECTIONS_PURPOSE, SecretBox, build_secret_box
from src.main import create_app
from src.models import AuditEntry, Connection, RunEvent, ToolExecution
from src.models.bot import SecurityLevel
from src.runtime import tool_pipeline, toolset
from src.runtime.reporter import RunReporter
from src.runtime.runner import RunManager
from src.runtime.tool_pipeline import ExecuteDeps, ToolCallRequest
from src.services.credential_vault import CredentialUnavailable, CredentialVault, api_key_secret
from src.services.tool_execution_service import RunRef
from tests.conftest import PASSWORD, TEST_SETTINGS, sign_up

DEMO_KEY = "demo-key-TOPSECRET-0000000000001"
STRONG = "a-long-random-secret-for-the-connection-tests-000001"

# The vault


def _row(**changes: Any) -> Connection:
    row = Connection(
        org_id=uuid.uuid4(),
        connector_id="demo",
        owner_kind="org",
        auth_type="api_key",
        account_label="Demo",
        account_ref="demo",
        status="active",
    )
    for key, value in changes.items():
        setattr(row, key, value)
    return row


def _auth() -> Any:
    from botdesk_plugin_sdk import ApiKeyAuth

    return ApiKeyAuth(header="X-Api-Key")


def test_the_vault_round_trips_a_credential_and_never_prints_it() -> None:
    vault = CredentialVault(SecretBox(STRONG, purpose=CONNECTIONS_PURPOSE))
    row = _row()
    vault.save(row, api_key_secret(DEMO_KEY, _auth()))
    assert row.encrypted_secret and DEMO_KEY not in row.encrypted_secret
    credential = vault.open(row)
    assert credential.auth_headers() == {"X-Api-Key": DEMO_KEY}
    assert DEMO_KEY not in repr(credential) and DEMO_KEY not in str(credential)
    assert "hidden" in repr(vault)


def test_a_model_key_box_cannot_open_a_connection_and_back() -> None:
    connections = CredentialVault(SecretBox(STRONG, purpose=CONNECTIONS_PURPOSE))
    row = _row()
    connections.save(row, api_key_secret(DEMO_KEY, _auth()))
    with pytest.raises(CredentialUnavailable, match="can't be read"):
        CredentialVault(SecretBox(STRONG)).open(row)  # same SECRET_KEY, the model keys' purpose
    pasted = _row(encrypted_secret=SecretBox(STRONG).encrypt('{"kind":"api_key","api_key":"x","header":"A"}'))
    with pytest.raises(CredentialUnavailable):
        connections.open(pasted)  # a model key's ciphertext copied into a connection row


def test_rotation_old_credentials_still_open_and_a_save_moves_them_to_the_new_key() -> None:
    old_secret = "the-previous-secret-key-for-rotation-tests-0000002"
    row = _row()
    CredentialVault(SecretBox(old_secret, purpose=CONNECTIONS_PURPOSE)).save(row, api_key_secret(DEMO_KEY, _auth()))
    settings = Settings(secret_key=SecretStr(STRONG), secret_key_old=SecretStr(old_secret), _env_file=None)
    rotated = CredentialVault.from_settings(settings)
    assert rotated.open(row).auth_headers() == {"X-Api-Key": DEMO_KEY}
    rotated.save(row, api_key_secret(DEMO_KEY, _auth()))
    assert CredentialVault(SecretBox(STRONG, purpose=CONNECTIONS_PURPOSE)).open(row).auth_headers()
    with pytest.raises(CredentialUnavailable):
        CredentialVault(SecretBox(old_secret, purpose=CONNECTIONS_PURPOSE)).open(row)


def test_a_revoked_or_reconnect_needing_connection_is_refused() -> None:
    vault = CredentialVault(build_secret_box(TEST_SETTINGS, purpose=CONNECTIONS_PURPOSE))
    row = _row()
    vault.save(row, api_key_secret(DEMO_KEY, _auth()))
    row.status = "needs_reconnect"
    with pytest.raises(CredentialUnavailable, match="needs reconnecting"):
        vault.open(row)
    vault.revoke(row, reason="Disconnected")
    assert (row.status, row.encrypted_secret) == ("revoked", None)
    with pytest.raises(CredentialUnavailable, match="disconnected"):
        vault.open(row)


# Over HTTP: who may do what


@dataclass
class Team:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    org_id: str
    bot_id: str  # created by Ali (the owner)

    async def sign_in(self, email: str) -> None:
        self.client.cookies.clear()
        response = await self.client.post("/api/v1/auth/sign-in", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text

    async def connect(self, expect: int = 201, **body: Any) -> dict[str, Any]:
        payload = {"connectorId": "demo", "apiKey": DEMO_KEY, **body}
        response = await self.client.post(f"{self.org}/connections", json=payload)
        assert response.status_code == expect, response.text
        data: dict[str, Any] = response.json()
        return data

    async def bind(
        self, connection_id: str | None, *, plugin: str = "demo", enabled: bool = True, expect: int = 200
    ) -> dict[str, Any]:
        """Choose the account Scout's `plugin` works through (PUT /bots/{bot}/tools)."""
        body = {"plugins": [{"pluginId": plugin, "enabled": enabled, "connectionId": connection_id}]}
        response = await self.client.put(f"{self.org}/bots/{self.bot_id}/tools", json=body)
        assert response.status_code == expect, response.text
        data: dict[str, Any] = response.json()
        return data

    async def labels(self) -> list[str]:
        response = await self.client.get(f"{self.org}/connections")
        assert response.status_code == 200, response.text
        return [c["accountLabel"] for c in response.json()]


@pytest.fixture
async def team() -> AsyncIterator[Team]:
    async with acme() as world:
        yield world


@asynccontextmanager
async def acme() -> AsyncIterator[Team]:
    """Ali owns Acme and made the bot Scout; Sara is a member. Ali is signed in."""
    app = create_app(TEST_SETTINGS)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        app.state.runs.enabled = False
        ali = await sign_up(client)
        org_id = ali["organizations"][0]["id"]
        org = f"/api/v1/orgs/{org_id}"
        invite = await client.post(f"{org}/invitations", json={"email": "sara@acme.dev", "role": "member"})
        bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
        await sign_up(client, name="Sara", email="sara@acme.dev")
        token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
        assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
        world = Team(app=app, client=client, org=org, org_id=org_id, bot_id=bot["id"])
        await world.sign_in("ali@acme.dev")
        yield world


async def test_a_member_connects_their_own_account_and_the_key_never_comes_back(
    team: Team, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    created = await team.connect(accountLabel="My demo")
    assert created["ownerKind"] == "member" and created["status"] == "active"
    assert created["authType"] == "api_key" and created["scopes"] == []
    listed = await team.client.get(f"{team.org}/connections")
    one = await team.client.get(f"{team.org}/connections/{created['id']}")
    for text in (str(created), listed.text, one.text, caplog.text):
        assert DEMO_KEY not in text
    assert "encryptedSecret" not in created and "apiKey" not in created


async def test_connecting_the_same_account_again_replaces_the_key_not_adds_a_row(team: Team) -> None:
    first = await team.connect(accountLabel="Acme demo")
    again = await team.connect(accountLabel="acme DEMO", apiKey="a-new-key-0000000000000002")
    assert again["id"] == first["id"]
    assert await team.labels() == ["acme DEMO"]
    async with team.app.state.sessionmaker() as db:
        actions = list(await db.scalars(select(AuditEntry.action).order_by(AuditEntry.created_at)))
    assert actions == ["connection.created", "connection.reconnected"]


async def test_bad_requests_are_refused(team: Team) -> None:
    await team.connect(expect=404, connectorId="gmail")  # not loaded on this server
    await team.connect(expect=422, apiKey="line one\nX-Evil: 1")  # header injection
    await team.connect(expect=422, apiKey="   ")
    await team.connect(expect=400, ownerKind="bot")  # which bot?
    await team.connect(expect=404, ownerKind="bot", botId=str(uuid.uuid4()))


async def test_who_may_create_bot_and_org_connections(team: Team) -> None:
    await team.sign_in("sara@acme.dev")
    await team.connect(expect=403, ownerKind="org")
    await team.connect(expect=403, ownerKind="bot", botId=team.bot_id)  # Ali made Scout
    mine = await team.connect(ownerKind="member", accountLabel="Sara's")
    assert mine["ownerUserId"] is not None
    await team.sign_in("ali@acme.dev")
    org = await team.connect(ownerKind="org", accountLabel="Shared")
    bot = await team.connect(ownerKind="bot", botId=team.bot_id, accountLabel="Scout's own")
    assert (org["ownerUserId"], org["ownerBotId"]) == (None, None)
    assert bot["ownerBotId"] == team.bot_id


async def test_member_connections_are_private_to_their_member_but_admins_see_they_exist(team: Team) -> None:
    await team.sign_in("sara@acme.dev")
    saras = await team.connect(accountLabel="Sara's")
    await team.sign_in("ali@acme.dev")
    alis = await team.connect(accountLabel="Ali's")
    await team.connect(ownerKind="org", accountLabel="Shared")
    assert sorted(await team.labels()) == ["Ali's", "Sara's", "Shared"]  # Ali is the owner
    await team.sign_in("sara@acme.dev")
    assert sorted(await team.labels()) == ["Sara's", "Shared"]
    assert (await team.client.get(f"{team.org}/connections/{alis['id']}")).status_code == 404
    assert (await team.client.delete(f"{team.org}/connections/{alis['id']}")).status_code == 404
    assert (await team.client.get(f"{team.org}/connections/{saras['id']}")).status_code == 200


async def test_another_organizations_connection_is_not_found(team: Team) -> None:
    shared = await team.connect(ownerKind="org")
    await sign_up(team.client, name="Omar", email="omar@other.dev")  # owns a different org
    me = (await team.client.get("/api/v1/auth/me")).json()
    other = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    assert (await team.client.get(f"{other}/connections/{shared['id']}")).status_code == 404
    assert (await team.client.delete(f"{other}/connections/{shared['id']}")).status_code == 404
    assert (await team.client.get(f"{team.org}/connections")).status_code == 404  # not a member there


async def test_who_may_disconnect(team: Team) -> None:
    shared = await team.connect(ownerKind="org")
    scouts = await team.connect(ownerKind="bot", botId=team.bot_id)
    await team.sign_in("sara@acme.dev")
    saras = await team.connect(accountLabel="Sara's")
    assert (await team.client.delete(f"{team.org}/connections/{shared['id']}")).status_code == 403
    assert (await team.client.delete(f"{team.org}/connections/{scouts['id']}")).status_code == 403
    assert (await team.client.delete(f"{team.org}/connections/{saras['id']}")).status_code == 204
    await team.sign_in("ali@acme.dev")  # an owner may disconnect anything, a member's too
    assert (await team.client.delete(f"{team.org}/connections/{scouts['id']}")).status_code == 204
    assert (await team.client.delete(f"{team.org}/connections/{scouts['id']}")).status_code == 204  # again: no-op

    gone = (await team.client.get(f"{team.org}/connections/{scouts['id']}")).json()
    assert gone["status"] == "revoked"
    async with team.app.state.sessionmaker() as db:
        row = await db.get(Connection, uuid.UUID(scouts["id"]))
        assert row is not None and row.encrypted_secret is None
        actions = list(await db.scalars(select(AuditEntry.action).where(AuditEntry.target_id == row.id)))
    assert actions == ["connection.created", "connection.disconnected"]


# The demo API-key tool, end to end through the tool pipeline


class FakeDemoApi:
    """postman-echo.com, answering only requests that carry the connected key."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("x-api-key") != DEMO_KEY:
            return httpx.Response(401, json={"error": "no key"})
        return httpx.Response(200, json={"headers": dict(request.headers)})  # echoes the key back


async def _run_tool(
    team: Team, tool: str, args: dict[str, Any] | None = None, *, level: SecurityLevel = "ask-before-acting"
) -> tuple[Any, Any]:
    """The signed-in member's DM with Scout, a (never started) run, and one call of `tool` through
    the run's toolset and prepare → record → execute, as the graph does."""
    client = team.client
    thread = (await client.post(f"{team.org}/threads/dm", json={"botId": team.bot_id})).json()
    sent = (await client.post(f"{team.org}/threads/{thread['id']}/messages", json={"text": "Hi"})).json()
    runs: RunManager = team.app.state.runs
    run = RunRef(
        run_id=uuid.UUID(sent["runIds"][0]),
        org_id=uuid.UUID(team.org_id),
        thread_id=uuid.UUID(thread["id"]),
        bot_id=uuid.UUID(team.bot_id),
    )
    async with runs.sessionmaker() as db:
        tools = await toolset.load(db, runs.registry, run.run_id)
    call = tool_pipeline.prepare(
        tools,
        ToolCallRequest(f"call-{uuid.uuid4().hex[:6]}", tool, args or {}),
        level=level,
        tainted=False,
        connections=tools.connections,
    )
    async with runs.sessionmaker() as db:
        recorded = await tool_pipeline.record(db, run, call, tainted=False, approval_expiry=timedelta(hours=1))
        await db.commit()
    if call.decision != "auto":
        return call, None
    reporter = RunReporter(runs.sessionmaker, runs.bus, run.org_id, run.thread_id, run.run_id)
    deps = ExecuteDeps(
        runs.sessionmaker,
        tools,
        reporter,
        run,
        timeout_seconds=5,
        access=runs.tool_access,
        connection_ids=tools.connection_ids,
    )
    return call, await tool_pipeline.execute(deps, recorded.execution.id)


async def test_the_demo_tool_calls_its_host_with_the_key_the_tool_never_sees(
    team: Team, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    api = FakeDemoApi()
    team.app.state.runs.tool_access.transport = httpx.MockTransport(api.handle)
    shared = await team.connect(ownerKind="org", accountLabel="Acme demo")
    await team.bind(shared["id"])

    call, outcome = await _run_tool(team, "demo__call_api")
    assert call.decision == "auto"  # a read: the policy is unchanged by connections
    assert call.trace.endswith(" · via=demo:Acme demo (org)")
    assert '"calledHost": "postman-echo.com"' in outcome.text and '"status": 200' in outcome.text
    assert '"account": "Acme demo"' in outcome.text
    (request,) = api.requests
    assert request.url.host == "postman-echo.com" and request.headers["x-api-key"] == DEMO_KEY

    async with team.app.state.sessionmaker() as db:
        execution = await db.scalar(select(ToolExecution).where(ToolExecution.tool_name == "demo.call_api"))
        connection = await db.get(Connection, uuid.UUID(shared["id"]))
        events = list(await db.scalars(select(RunEvent.payload)))
    assert execution is not None and connection is not None
    assert execution.connection_id == connection.id and connection.last_used_at is not None
    for text in (outcome.text, str(execution.result), str(events), caplog.text):
        assert DEMO_KEY not in text


async def test_without_a_connection_the_tool_fails_with_a_reason_and_the_run_goes_on(team: Team) -> None:
    api = FakeDemoApi()
    team.app.state.runs.tool_access.transport = httpx.MockTransport(api.handle)
    await team.connect(ownerKind="org")  # connected, but not chosen in Scout's Tools: never used
    _, outcome = await _run_tool(team, "demo__call_api")
    assert "Demo isn't connected for this bot" in outcome.text
    assert api.requests == []


async def _demo_binding(team: Team) -> dict[str, Any]:
    tools = (await team.client.get(f"{team.org}/bots/{team.bot_id}/tools")).json()
    demo: dict[str, Any] = next(plugin for plugin in tools["plugins"] if plugin["pluginId"] == "demo")
    return demo


async def test_disconnecting_the_bound_account_leaves_the_plugin_on_with_no_account(team: Team) -> None:
    api = FakeDemoApi()
    team.app.state.runs.tool_access.transport = httpx.MockTransport(api.handle)
    shared = await team.connect(ownerKind="org")
    await team.bind(shared["id"])
    assert (await team.client.delete(f"{team.org}/connections/{shared['id']}")).status_code == 204
    demo = await _demo_binding(team)
    assert (demo["enabled"], demo["connectionId"]) == (True, None)
    _, outcome = await _run_tool(team, "demo__call_api")
    assert "isn't connected" in outcome.text
    assert api.requests == []


async def test_the_bound_connection_is_the_one_used(team: Team) -> None:
    api = FakeDemoApi()
    team.app.state.runs.tool_access.transport = httpx.MockTransport(api.handle)
    await team.connect(ownerKind="org", accountLabel="Shared", apiKey="the-org-key-0000000000000003")
    own = await team.connect(ownerKind="bot", botId=team.bot_id, accountLabel="Scout's own")
    await team.bind(own["id"])
    _, outcome = await _run_tool(team, "demo__call_api")
    assert '"account": "Scout\'s own"' in outcome.text
    assert api.requests[0].headers["x-api-key"] == DEMO_KEY


async def test_a_members_connection_works_only_in_their_own_dm(team: Team) -> None:
    api = FakeDemoApi()
    team.app.state.runs.tool_access.transport = httpx.MockTransport(api.handle)
    alis = await team.connect(accountLabel="Ali's")
    await team.bind(alis["id"])
    _, outcome = await _run_tool(team, "demo__call_api")  # Ali, in his DM with Scout
    assert '"account": "Ali\'s"' in outcome.text
    await team.sign_in("sara@acme.dev")
    call, outcome = await _run_tool(team, "demo__call_api")  # Sara, in hers: the plugin is dropped
    assert call.decision == "invalid" and outcome is None
    assert len(api.requests) == 1


async def test_approvals_are_unaffected_risky_demo_tools_still_ask(team: Team) -> None:
    call, outcome = await _run_tool(team, "demo__send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    assert (call.decision, outcome) == ("ask", None)
    call, _ = await _run_tool(team, "demo__call_api", level="read-only")
    assert call.decision == "auto"

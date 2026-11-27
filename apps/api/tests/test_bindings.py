"""Bindings: each bot's Tools (slice 5.2), over HTTP on SQLite. GET/PUT /bots/{bot}/tools, who may
choose which connection (ADR 0010 §3), the audit lines, new bots' defaults, and the approval rule
for calls through a member's own connection."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from botdesk_plugin_sdk import NoArgs, OAuth2Auth, PluginManifest, ToolContext, ToolSpec
from sqlalchemy import select

from src.models import Approval, AuditEntry, Connection, Run, ThreadParticipant, ToolExecution, User
from src.runtime import tool_pipeline, toolset
from src.runtime.reporter import RunReporter
from src.runtime.runner import RunManager
from src.runtime.tool_pipeline import ACCOUNT_CHANGED, ExecuteDeps
from src.services.tool_execution_service import RunRef
from tests.test_connections import Team, _run_tool, acme


@pytest.fixture
async def team() -> AsyncIterator[Team]:
    """Ali owns Acme and made the bot Scout; Sara is a member. Ali is signed in."""
    async with acme() as world:
        yield world


def _tools_url(team: Team, bot_id: str | None = None) -> str:
    return f"{team.org}/bots/{bot_id or team.bot_id}/tools"


async def _tools(team: Team, bot_id: str | None = None) -> dict[str, dict[str, Any]]:
    response = await team.client.get(_tools_url(team, bot_id))
    assert response.status_code == 200, response.text
    return {plugin["pluginId"]: plugin for plugin in response.json()["plugins"]}


async def test_a_new_bot_has_every_plugin_that_doesnt_sign_in_with_oauth(team: Team) -> None:
    demo = (await _tools(team))["demo"]
    assert (demo["enabled"], demo["connectionId"], demo["authType"]) == (True, None, "api_key")
    assert demo["name"] == "Demo" and demo["description"]
    tool = next(t for t in demo["tools"] if t["name"] == "demo.send_email")
    assert set(tool) == {"name", "title", "description", "risk"} and tool["risk"] == "external-send"


async def _handler(_args: NoArgs, _ctx: ToolContext) -> dict[str, str]:
    return {}


MAIL = PluginManifest(
    id="mail",
    name="Mail",
    version="1",
    description="Mail",
    tools=(
        ToolSpec(name="search", title="Search", description="Search", args_model=NoArgs, risk="read", handler=_handler),
    ),
    auth=OAuth2Auth(
        provider="google",
        authorize_url="https://auth.example/authorize",
        token_url="https://auth.example/token",
        scope_sets={"full": ("mail.all",)},
    ),
    egress=("mail.example",),
)


async def test_oauth_plugins_start_off_and_are_listed_off_for_bots_without_a_binding(team: Team) -> None:
    runs: RunManager = team.app.state.runs
    runs.registry.register(MAIL)
    try:
        bot = (await team.client.post(f"{team.org}/bots", json={"name": "Inbox"})).json()
        tools = await _tools(team, bot["id"])
        assert tools["demo"]["enabled"] is True
        assert (tools["mail"]["enabled"], tools["mail"]["connectionId"], tools["mail"]["authType"]) == (
            False,
            None,
            "oauth2",
        )
    finally:
        runs.registry.unregister("mail")


async def test_any_member_switches_plugins_and_only_the_plugins_sent_change(team: Team) -> None:
    await team.sign_in("sara@acme.dev")  # a member, not Scout's creator
    off = await team.bind(None, enabled=False)
    # The core plugins are listed first, on by default (ADR 0014, 0017, 0020); only demo was sent.
    assert [(p["pluginId"], p["enabled"]) for p in off["plugins"]] == [
        ("team", True),
        ("files", True),
        ("browser", True),
        ("computer", True),
        ("demo", False),
    ]
    assert (await _tools(team))["demo"]["enabled"] is False
    response = await team.client.put(_tools_url(team), json={"plugins": []})
    assert response.status_code == 200 and response.json()["plugins"][4]["enabled"] is False
    assert (await team.bind(None))["plugins"][4]["enabled"] is True


async def test_bad_bindings_are_refused(team: Team) -> None:
    await team.bind(None, plugin="gmail", expect=404)  # not loaded on this server
    await team.bind(str(uuid.uuid4()), expect=404)
    response = await team.client.put(f"{team.org}/bots/{uuid.uuid4()}/tools", json={"plugins": []})
    assert response.status_code == 404
    twice = {"pluginId": "demo", "enabled": True, "connectionId": None}
    assert (await team.client.put(_tools_url(team), json={"plugins": [twice, twice]})).status_code == 400
    missing = {"pluginId": "demo", "enabled": True}  # connectionId is required (null: no account)
    assert (await team.client.put(_tools_url(team), json={"plugins": [missing]})).status_code == 422

    async with team.app.state.sessionmaker() as db:
        other = Connection(
            org_id=uuid.UUID(team.org_id),
            connector_id="gmail",
            owner_kind="org",
            auth_type="oauth2",
            account_label="ali@acme.dev",
            account_ref="1",
            scopes=[],
        )
        db.add(other)
        await db.commit()
    wrong = await team.bind(str(other.id), expect=400)
    assert wrong["detail"] == "That account is for another app."

    gone = await team.connect(ownerKind="org", accountLabel="Old")
    assert (await team.client.delete(f"{team.org}/connections/{gone['id']}")).status_code == 204
    await team.bind(gone["id"], expect=400)


async def test_who_may_choose_which_connection(team: Team) -> None:
    shared = await team.connect(ownerKind="org", accountLabel="Shared")
    scouts = await team.connect(ownerKind="bot", botId=team.bot_id, accountLabel="Scout's own")
    alis = await team.connect(accountLabel="Ali's")
    inbox = (await team.client.post(f"{team.org}/bots", json={"name": "Inbox"})).json()
    inboxs = await team.connect(ownerKind="bot", botId=inbox["id"], accountLabel="Inbox's own")
    await team.sign_in("sara@acme.dev")
    saras = await team.connect(accountLabel="Sara's")

    await team.bind(shared["id"], expect=403)  # the organization's: owners and admins
    await team.bind(scouts["id"], expect=403)  # Scout's own: owners, admins and its creator (Ali)
    await team.bind(alis["id"], expect=404)  # another member's: she can't even see it
    await team.bind(saras["id"])  # her own

    await team.sign_in("ali@acme.dev")
    await team.bind(saras["id"], enabled=False)  # leaving the connection as it is: never refused
    await team.bind(inboxs["id"], expect=400)  # another bot's own account
    await team.bind(shared["id"])
    await team.bind(saras["id"], expect=403)  # an owner sees Sara's connection but can't use it
    await team.bind(scouts["id"])
    assert (await _tools(team))["demo"]["connectionId"] == scouts["id"]

    await team.sign_in("sara@acme.dev")
    await team.bind(scouts["id"], enabled=False)  # unchanged connection, any member may switch
    await team.bind(None, expect=403)  # removing Scout's own account needs the right to choose it


async def test_replacing_or_removing_an_account_needs_the_right_to_that_account(team: Team) -> None:
    """A member can't knock out an account someone else chose: putting their own over the
    organization's would take the app away from everyone else's runs."""
    shared = await team.connect(ownerKind="org", accountLabel="Shared")
    await team.bind(shared["id"])
    await team.sign_in("sara@acme.dev")
    saras = await team.connect(accountLabel="Sara's")

    await team.bind(saras["id"], expect=403)  # over the organization's account
    await team.bind(None, expect=403)  # clearing it
    await team.bind(shared["id"], enabled=False)  # switching the app off is still anyone's call
    assert (await _tools(team))["demo"]["connectionId"] == shared["id"]

    await team.sign_in("ali@acme.dev")
    await team.bind(None)  # an owner may clear it
    await team.sign_in("sara@acme.dev")
    await team.bind(saras["id"])  # an empty slot is free to fill with her own
    await team.bind(None)  # and her own she may take back out

    await team.bind(saras["id"])
    await team.sign_in("ali@acme.dev")
    await team.bind(shared["id"])  # owners and admins may replace a member's account (offboarding)
    assert (await _tools(team))["demo"]["connectionId"] == shared["id"]


async def test_choosing_an_account_writes_bound_and_unbound_lines(team: Team) -> None:
    first = await team.connect(ownerKind="org", accountLabel="First")
    second = await team.connect(ownerKind="org", accountLabel="Second")
    await team.bind(first["id"])
    await team.bind(second["id"])
    await team.bind(second["id"], enabled=False)  # no account change: no line
    await team.bind(None)
    async with team.app.state.sessionmaker() as db:
        lines = (
            await db.execute(
                select(AuditEntry.action, AuditEntry.target_id, AuditEntry.details)
                .where(AuditEntry.action.in_(("connection.bound", "connection.unbound")))
                .order_by(AuditEntry.created_at, AuditEntry.id)
            )
        ).all()
    first_id, second_id = uuid.UUID(first["id"]), uuid.UUID(second["id"])
    assert [(action, target) for action, target, _ in lines] == [
        ("connection.bound", first_id),
        ("connection.unbound", first_id),
        ("connection.bound", second_id),
        ("connection.unbound", second_id),
    ]
    assert lines[0][2] == {"connector": "demo", "botId": team.bot_id}


async def test_runs_act_for_the_member_whose_message_started_them(team: Team) -> None:
    thread = (await team.client.post(f"{team.org}/threads/dm", json={"botId": team.bot_id})).json()
    sent = (await team.client.post(f"{team.org}/threads/{thread['id']}/messages", json={"text": "Hi"})).json()
    async with team.app.state.sessionmaker() as db:
        run = await db.get(Run, uuid.UUID(sent["runIds"][0]))
        ali = await db.scalar(select(User.id).where(User.email == "ali@acme.dev"))
    assert run is not None and run.requester_id == ali


async def test_only_the_owner_decides_a_call_through_their_own_connection(team: Team) -> None:
    alis = await team.connect(accountLabel="Ali's")
    await team.bind(alis["id"])
    call, _ = await _run_tool(team, "demo__send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    assert call.decision == "ask" and call.connection is not None
    async with team.app.state.sessionmaker() as db:
        approval = await db.scalar(select(Approval))
        sara = await db.scalar(select(User.id).where(User.email == "sara@acme.dev"))
        assert approval is not None and approval.connection_id == uuid.UUID(alis["id"])
        # However Sara came to be in the chat, the call acts as Ali: she can't decide it.
        db.add(ThreadParticipant(thread_id=approval.thread_id, participant_type="user", participant_id=sara))
        await db.commit()
    url = f"{team.org}/approvals/{approval.id}/decide"
    await team.sign_in("sara@acme.dev")
    refused = await team.client.post(url, json={"decision": "approve"})
    assert refused.status_code == 403, refused.text
    await team.sign_in("ali@acme.dev")
    assert (await team.client.post(url, json={"decision": "deny"})).status_code == 200


async def test_calls_through_an_org_connection_keep_the_chats_rule(team: Team) -> None:
    shared = await team.connect(ownerKind="org", accountLabel="Shared")
    await team.bind(shared["id"])
    call, _ = await _run_tool(team, "demo__send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    assert call.decision == "ask"
    async with team.app.state.sessionmaker() as db:
        approval = await db.scalar(select(Approval))
        sara = await db.scalar(select(User.id).where(User.email == "sara@acme.dev"))
        assert approval is not None
        db.add(ThreadParticipant(thread_id=approval.thread_id, participant_type="user", participant_id=sara))
        await db.commit()
    await team.sign_in("sara@acme.dev")
    decided = await team.client.post(f"{team.org}/approvals/{approval.id}/decide", json={"decision": "deny"})
    assert decided.status_code == 200, decided.text


async def _approve_then_execute(team: Team, change: Callable[[], Awaitable[Any]]) -> str:
    """Ask for a risky call in Ali's DM, approve it, `change` Scout's Tools, then run the call as
    the resumed run does: with the toolset read again. Returns what the model would read."""
    call, _ = await _run_tool(team, "demo__send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    async with team.app.state.sessionmaker() as db:
        execution = await db.scalar(select(ToolExecution).where(ToolExecution.tool_call_id == call.request.id))
        approval = await db.scalar(select(Approval).where(Approval.tool_execution_id == execution.id))
        run = await db.get(Run, approval.run_id)
    assert execution is not None and approval is not None and run is not None
    decided = await team.client.post(f"{team.org}/approvals/{approval.id}/decide", json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    await change()
    runs: RunManager = team.app.state.runs
    ref = RunRef(run_id=run.id, org_id=run.org_id, thread_id=run.thread_id, bot_id=run.bot_id)
    async with runs.sessionmaker() as db:
        tools = await toolset.load(db, runs.registry, run.id)
    reporter = RunReporter(runs.sessionmaker, runs.bus, ref.org_id, ref.thread_id, ref.run_id)
    deps = ExecuteDeps(runs.sessionmaker, tools, reporter, ref, timeout_seconds=5, connection_ids=tools.connection_ids)
    return (await tool_pipeline.execute(deps, execution.id)).text


async def test_a_tool_switched_off_while_its_run_waited_is_refused_on_resume(team: Team) -> None:
    text = await _approve_then_execute(team, lambda: team.bind(None, enabled=False))
    assert text == "The tool failed: This tool isn't available any more."


async def test_an_approved_call_never_runs_on_an_account_chosen_after_the_decision(team: Team) -> None:
    first = await team.connect(ownerKind="org", accountLabel="First")
    second = await team.connect(ownerKind="org", accountLabel="Second")
    await team.bind(first["id"])
    text = await _approve_then_execute(team, lambda: team.bind(second["id"]))
    assert text == f"The tool failed: {ACCOUNT_CHANGED}"

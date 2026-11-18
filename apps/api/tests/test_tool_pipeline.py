"""The tool pipeline and approvals, on SQLite: pipeline decisions, the registry, the stand-in's
`/tool` command, "runs at most once", and deciding an approval exactly once over HTTP.
The real pause and resume (LangGraph + Postgres checkpoints) is in test_approvals_postgres.py.
"""

import asyncio
import dataclasses
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from botdesk_demo import demo_plugin
from botdesk_plugin_sdk import NotDone, PluginManifest, RiskClass, ToolContext, ToolSpec
from fastapi import FastAPI
from langchain_core.messages import BaseMessage
from pydantic import BaseModel
from sqlalchemy import select, update

from src.core.database import utcnow
from src.main import create_app
from src.models import Approval, Run, RunEvent, ToolExecution
from src.models.bot import SecurityLevel
from src.plugins.registry import ToolRegistry, build_registry
from src.runtime import tool_pipeline
from src.runtime.chat_model import StandInModel, parse_tool_command
from src.runtime.prompt import HistoryLine, build_prompt
from src.runtime.reporter import RunReporter
from src.runtime.runner import RunManager
from src.runtime.tool_pipeline import ExecuteDeps, NeedsAttention, ToolCallRequest
from src.services import tool_execution_service
from src.services.tool_execution_service import RunRef
from tests.conftest import TEST_SETTINGS, sign_up

# Pure: the registry, the stand-in model and the pipeline's decisions


def test_the_demo_plugin_registers_its_tools_under_full_names() -> None:
    registry = build_registry(["demo"])
    names = {tool.name for tool in registry.tools()}
    assert {"demo.current_time", "demo.create_note", "demo.draft_email", "demo.send_email", "demo.read_inbox"} <= names
    send = registry.get("demo__send_email")  # the model's spelling maps back
    assert send is not None and send.name == "demo.send_email"
    assert send.for_model()["function"]["name"] == "demo__send_email"
    assert send.for_model()["function"]["parameters"]["required"] == ["to", "subject"]


def test_the_demo_manifest_covers_the_interesting_risk_classes() -> None:
    manifest = demo_plugin().to_json()
    risks = {tool["name"]: tool["risk"] for tool in manifest["tools"]}
    assert risks["create_note"] == "write-internal"
    assert risks["draft_email"] == "write-external"
    assert risks["send_email"] == "external-send"
    assert [t["name"] for t in manifest["tools"] if t["untrustedOutput"]] == ["read_inbox"]


def test_a_plugin_cannot_be_registered_twice_and_unknown_plugins_are_refused() -> None:
    registry = build_registry(["demo"])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(demo_plugin())
    with pytest.raises(ValueError, match="no such plugin"):
        build_registry(["no-such-plugin"])


def test_the_stand_in_reads_a_tool_command() -> None:
    assert parse_tool_command('@scout /tool demo.create_note title="Q3 plan" pinned=true n=3') == (
        "demo.create_note",
        {"title": "Q3 plan", "pinned": True, "n": 3},
    )
    assert parse_tool_command('/tool demo.send_email {"to": "a@b.dev", "subject": "Hi"}') == (
        "demo.send_email",
        {"to": "a@b.dev", "subject": "Hi"},
    )
    assert parse_tool_command("/tool demo.current_time") == ("demo.current_time", {})
    assert parse_tool_command("no command here") is None
    assert parse_tool_command("/toolbox is not a command") is None


def test_the_stand_in_calls_the_tool_then_reports_the_result() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    model = StandInModel(provider="anthropic")
    first = model.invoke([HumanMessage(content="/tool demo.current_time")])
    assert first.tool_calls[0]["name"] == "demo__current_time"
    after = model.invoke([ToolMessage(content='{"utc": "now"}', tool_call_id="1", name="demo.current_time")])
    assert after.text == 'Finished demo.current_time: {"utc": "now"}'
    assert not after.tool_calls


def test_the_stand_in_runs_tool_commands_only_from_people() -> None:
    model = StandInModel(provider="anthropic")
    reader_reply = "You can still try tools: send `/tool demo.send_email to=sara@acme.dev subject=Hi`."

    def last_line(author_type: str, author: str, text: str) -> list[BaseMessage]:
        line = HistoryLine(from_this_bot=False, text=text, author_type=author_type, author=author)
        return build_prompt(bot_name="Auto", instructions="", memories=[], history=[line], group=True)

    from_a_bot = model.invoke(last_line("bot", "Reader (@reader)", reader_reply))
    assert not from_a_bot.tool_calls
    from_a_person = model.invoke(last_line("user", "Sara (@sara)", "@auto /tool demo.current_time"))
    assert from_a_person.tool_calls[0]["name"] == "demo__current_time"


@pytest.mark.parametrize(
    ("level", "tool", "tainted", "expected"),
    [
        ("ask-before-acting", "demo.current_time", False, "auto"),
        ("ask-before-acting", "demo.create_note", False, "auto"),
        ("ask-before-acting", "demo.draft_email", False, "ask"),
        ("ask-before-acting", "demo.send_email", False, "ask"),
        ("autonomous", "demo.send_email", False, "auto"),
        ("autonomous", "demo.send_email", True, "ask"),
        ("autonomous", "demo.draft_email", True, "ask"),
        ("autonomous", "demo.create_note", True, "auto"),
        ("read-only", "demo.send_email", False, "deny"),
        ("read-only", "demo.create_note", True, "auto"),
    ],
)
def test_the_pipeline_decides_by_level_risk_and_taint(
    level: SecurityLevel, tool: str, tainted: bool, expected: str
) -> None:
    args = {"title": "x"} if tool == "demo.create_note" else {}
    if "email" in tool:
        args = {"to": "sara@acme.dev", "subject": "Hi"}
    call = tool_pipeline.prepare(
        build_registry(["demo"]), ToolCallRequest("c1", tool, args), level=level, tainted=tainted
    )
    assert call.decision == expected
    assert (call.refusal is not None) == (expected == "deny")


def test_bad_arguments_and_unknown_tools_never_reach_the_policy() -> None:
    registry = build_registry(["demo"])
    bad = tool_pipeline.prepare(
        registry, ToolCallRequest("c1", "demo__send_email", {"to": "not an email"}), level="autonomous", tainted=False
    )
    assert bad.decision == "invalid"
    assert bad.refusal and "arguments for demo.send_email are wrong" in bad.refusal
    unknown = tool_pipeline.prepare(registry, ToolCallRequest("c2", "rm_rf", {}), level="autonomous", tainted=False)
    assert unknown.decision == "invalid"
    assert unknown.refusal == "There is no tool called rm_rf."


# On SQLite: recording, running at most once, and approvals over HTTP


class CountArgs(BaseModel):
    text: str = "hi"


@dataclass
class Calls:
    count: int = 0


def counting_plugin(calls: Calls) -> PluginManifest:
    """A test plugin whose tools count how often they really run."""

    async def run(args: CountArgs, _ctx: ToolContext) -> dict[str, Any]:
        calls.count += 1
        return {"echo": args.text, "count": calls.count}

    def spec(name: str, *, idempotent: bool) -> ToolSpec:
        return ToolSpec(
            name=name,
            title=name,
            description=name,
            args_model=CountArgs,
            risk="external-send",
            handler=run,
            idempotent=idempotent,
        )

    return PluginManifest(
        id="count",
        name="Count",
        version="1",
        description="test",
        tools=(spec("send", idempotent=False), spec("lookup", idempotent=True)),
    )


@dataclass
class World:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    run: RunRef
    calls: Calls

    @property
    def runs(self) -> RunManager:
        runs: RunManager = self.app.state.runs
        return runs

    @property
    def registry(self) -> ToolRegistry:
        return self.runs.registry

    def execute_deps(self) -> ExecuteDeps:
        reporter = RunReporter(
            self.runs.sessionmaker, self.runs.bus, self.run.org_id, self.run.thread_id, self.run.run_id
        )
        return ExecuteDeps(self.runs.sessionmaker, self.registry, reporter, self.run, timeout_seconds=5)

    async def record(self, tool: str, args: dict[str, Any], *, level: SecurityLevel = "ask-before-acting") -> Any:
        call = tool_pipeline.prepare(
            self.registry, ToolCallRequest(f"call-{uuid.uuid4().hex[:6]}", tool, args), level=level, tainted=False
        )
        async with self.runs.sessionmaker() as db:
            recorded = await tool_pipeline.record(db, self.run, call, tainted=False, approval_expiry=timedelta(hours=1))
            await db.commit()
        return recorded


@pytest.fixture
async def world() -> AsyncIterator[World]:
    """An app on in-memory SQLite with one bot chat and one (never started) run."""
    app = create_app(TEST_SETTINGS)
    async with app.router.lifespan_context(app):
        app.state.runs.enabled = False
        calls = Calls()
        app.state.runs.registry.register(counting_plugin(calls))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            me = await sign_up(client)
            org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
            bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
            thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
            sent = (await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Hi"})).json()
            run = RunRef(
                run_id=uuid.UUID(sent["runIds"][0]),
                org_id=uuid.UUID(me["organizations"][0]["id"]),
                thread_id=uuid.UUID(thread["id"]),
                bot_id=uuid.UUID(bot["id"]),
            )
            yield World(app=app, client=client, org=org, run=run, calls=calls)


async def test_recording_the_same_call_twice_keeps_one_row(world: World) -> None:
    call = tool_pipeline.prepare(
        world.registry,
        ToolCallRequest("same-id", "demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"}),
        level="ask-before-acting",
        tainted=False,
    )
    async with world.runs.sessionmaker() as db:
        first = await tool_pipeline.record(db, world.run, call, tainted=False, approval_expiry=timedelta(hours=1))
        second = await tool_pipeline.record(db, world.run, call, tainted=False, approval_expiry=timedelta(hours=1))
        await db.commit()
    assert first.created and not second.created
    assert first.execution.id == second.execution.id
    assert first.approval is not None and second.approval is not None
    assert first.approval.id == second.approval.id
    assert first.execution.status == "waiting_approval"
    assert first.execution.args_hash == second.execution.args_hash


async def test_a_tool_call_runs_at_most_once(world: World) -> None:
    recorded = await world.record("count.send", {"text": "once"}, level="autonomous")

    first = await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)
    again = await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)

    assert world.calls.count == 1
    assert first.text == again.text == '{"echo": "once", "count": 1}'
    async with world.runs.sessionmaker() as db:
        row = await db.get(ToolExecution, recorded.execution.id)
    assert row is not None and row.status == "succeeded"
    assert row.result == {"echo": "once", "count": 1}


async def test_a_call_left_started_needs_a_person_unless_the_tool_is_idempotent(world: World) -> None:
    risky = await world.record("count.send", {}, level="autonomous")
    safe = await world.record("count.lookup", {}, level="autonomous")
    async with world.runs.sessionmaker() as db:
        await db.execute(update(ToolExecution).values(status="started"))
        await db.commit()

    with pytest.raises(NeedsAttention, match="can't tell whether it finished"):
        await tool_pipeline.execute(world.execute_deps(), risky.execution.id)
    await tool_pipeline.execute(world.execute_deps(), safe.execution.id)

    assert world.calls.count == 1  # only the idempotent one ran again


async def test_a_call_waiting_for_approval_never_runs(world: World) -> None:
    recorded = await world.record("count.send", {})
    assert recorded.execution.status == "waiting_approval"
    with pytest.raises(RuntimeError, match="can't run while waiting_approval"):
        await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)
    assert world.calls.count == 0


async def test_a_tool_that_returns_outside_text_taints_the_run(world: World) -> None:
    recorded = await world.record("demo.read_inbox", {})

    outcome = await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)

    assert outcome.tainted
    assert outcome.text.startswith('<untrusted-content source="demo.read_inbox">')
    async with world.runs.sessionmaker() as db:
        run = await db.get(Run, world.run.run_id)
    assert run is not None and run.tainted


async def test_pending_approvals_are_listed_with_what_the_card_needs(world: World) -> None:
    await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Launch"})

    listed = (await world.client.get(f"{world.org}/approvals")).json()

    assert len(listed) == 1
    approval = listed[0]
    assert approval["tool"] == "demo.send_email"
    assert approval["title"] == "Send an email"
    assert approval["summary"] == "Send an email to sara@acme.dev: Launch"
    assert approval["riskClass"] == "external-send"
    assert approval["status"] == "pending"
    assert approval["reason"] == "level=Ask before acting · risk=external-send · tainted=no → ask"
    assert approval["preview"] == [
        {"label": "To", "value": "sara@acme.dev"},
        {"label": "Subject", "value": "Launch"},
        {"label": "Body", "value": ""},
    ]
    assert approval["argsSchema"]["required"] == ["to", "subject"]
    assert approval["runId"] == str(world.run.run_id)
    assert approval["decidedBy"] is None
    one = (await world.client.get(f"{world.org}/approvals/{approval['id']}")).json()
    assert one == approval
    filtered = await world.client.get(f"{world.org}/approvals", params={"botId": str(uuid.uuid4())})
    assert filtered.json() == []
    by_thread = await world.client.get(f"{world.org}/approvals", params={"threadId": str(world.run.thread_id)})
    assert len(by_thread.json()) == 1


async def test_a_card_shows_characters_that_would_hide_or_reorder_text(world: World) -> None:
    # Any tool's card (an MCP server's too): a person never approves text that reads differently
    # from what is sent. Emoji keep their joiners; line breaks stay line breaks.
    override, zero_width, joiner = chr(0x202E), chr(0x200B), chr(0x200D)
    technologist = chr(0x1F469) + joiner + chr(0x1F4BB)
    args = {"to": "sara@acme.dev", "subject": f"Pay {override}4321", "body": f"Hi{zero_width}\n{technologist}"}
    await world.record("demo.send_email", args)

    (approval,) = (await world.client.get(f"{world.org}/approvals")).json()

    assert approval["summary"] == "Send an email to sara@acme.dev: Pay [U+202E]4321"
    assert approval["preview"] == [
        {"label": "To", "value": "sara@acme.dev"},
        {"label": "Subject", "value": "Pay [U+202E]4321"},
        {"label": "Body", "value": f"Hi[U+200B]\n{technologist}"},
    ]
    assert approval["args"]["subject"] == f"Pay {override}4321"  # what runs is unchanged


async def test_an_approval_can_be_decided_only_once(world: World) -> None:
    recorded = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    decide = f"{world.org}/approvals/{recorded.approval.id}/decide"

    first = await world.client.post(decide, json={"decision": "approve"})
    second = await world.client.post(decide, json={"decision": "deny"})

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "approved"
    assert first.json()["decidedBy"]["name"] == "Ali Hassan"
    assert second.status_code == 409
    assert second.json() == {"detail": "This approval was already decided."}
    async with world.runs.sessionmaker() as db:
        execution = await db.get(ToolExecution, recorded.execution.id)
    assert execution is not None and execution.status == "ready"
    assert (await world.client.get(f"{world.org}/approvals")).json() == []
    everything = (await world.client.get(f"{world.org}/approvals", params={"status": "all"})).json()
    assert [a["status"] for a in everything] == ["approved"]


async def test_editing_runs_the_edited_arguments(world: World) -> None:
    recorded = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    decide = f"{world.org}/approvals/{recorded.approval.id}/decide"

    bad = await world.client.post(decide, json={"decision": "approve", "editedArgs": {"to": "nope"}})
    assert bad.status_code == 400
    assert bad.json()["detail"].startswith("Those changes don't fit this action:")

    edited = {"to": "omar@acme.dev", "subject": "Hello", "body": "Hi Omar"}
    approved = await world.client.post(decide, json={"decision": "approve", "editedArgs": edited})

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "edited"
    assert approved.json()["finalArgs"] == edited
    assert approved.json()["args"] == {"to": "sara@acme.dev", "subject": "Hi", "body": ""}
    # The summary describes what will run, built the same way as when it was asked for.
    assert approved.json()["summary"] == "Send an email to omar@acme.dev: Hello"
    listed = (await world.client.get(f"{world.org}/approvals/{recorded.approval.id}")).json()
    assert listed["summary"] == "Send an email to omar@acme.dev: Hello"
    assert [line["value"] for line in listed["preview"]] == ["omar@acme.dev", "Hello", "Hi Omar"]
    async with world.runs.sessionmaker() as db:
        execution = await db.get(ToolExecution, recorded.execution.id)
    assert execution is not None and execution.args == edited


async def test_denying_marks_the_call_denied(world: World) -> None:
    recorded = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})

    denied = await world.client.post(f"{world.org}/approvals/{recorded.approval.id}/decide", json={"decision": "deny"})

    assert denied.json()["status"] == "denied"
    assert denied.json()["finalArgs"] is None
    async with world.runs.sessionmaker() as db:
        execution = await db.get(ToolExecution, recorded.execution.id)
    assert execution is not None and execution.status == "denied"


async def test_an_expired_approval_cannot_be_approved(world: World) -> None:
    recorded = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    async with world.runs.sessionmaker() as db:
        await db.execute(update(Approval).values(expires_at=utcnow() - timedelta(minutes=1)))
        await db.commit()

    response = await world.client.post(
        f"{world.org}/approvals/{recorded.approval.id}/decide", json={"decision": "approve"}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This approval expired, so the bot didn't do it."}
    one = (await world.client.get(f"{world.org}/approvals/{recorded.approval.id}")).json()
    assert one["status"] == "expired"


async def test_people_outside_the_chat_cannot_see_or_decide_its_approvals(world: World) -> None:
    recorded = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    world.client.cookies.clear()
    await sign_up(world.client, name="Mallory", email="mallory@evil.dev")

    assert (await world.client.get(f"{world.org}/approvals")).status_code == 404  # not in this org
    decide = await world.client.post(
        f"{world.org}/approvals/{recorded.approval.id}/decide", json={"decision": "approve"}
    )
    assert decide.status_code == 404


async def test_stopping_a_run_that_waits_for_approval_expires_the_approval(world: World) -> None:
    recorded = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    async with world.runs.sessionmaker() as db:
        await db.execute(update(Run).values(status="waiting_approval"))
        await db.commit()

    stopped = (await world.client.post(f"{world.org}/runs/{world.run.run_id}/cancel")).json()

    assert stopped["status"] == "cancelled"
    one = (await world.client.get(f"{world.org}/approvals/{recorded.approval.id}")).json()
    assert one["status"] == "expired"
    late = await world.client.post(f"{world.org}/approvals/{recorded.approval.id}/decide", json={"decision": "approve"})
    assert late.status_code == 409


async def test_a_restart_during_a_tool_call_asks_a_person_instead_of_failing_blindly(world: World) -> None:
    recorded = await world.record("count.send", {}, level="autonomous")
    async with world.runs.sessionmaker() as db:
        await db.execute(update(Run).values(status="running"))
        await db.execute(
            update(ToolExecution).where(ToolExecution.id == recorded.execution.id).values(status="started")
        )
        await db.commit()

    await world.runs.recover_after_restart()

    run = (await world.client.get(f"{world.org}/runs/{world.run.run_id}")).json()
    assert run["status"] == "needs_attention"
    assert run["error"].startswith("The API restarted while count.send was running")
    # A chat opened later sees it, with the reason, so it can offer Stop.
    thread = f"{world.org}/threads/{world.run.thread_id}"
    (active,) = (await world.client.get(f"{thread}/runs", params={"active": True})).json()["runs"]
    assert (active["id"], active["status"], active["error"]) == (str(world.run.run_id), "needs_attention", run["error"])


async def test_the_reply_keeps_each_call_as_a_card_in_the_order_they_were_made(world: World) -> None:
    ran = await world.record("count.lookup", {}, level="autonomous")
    await tool_pipeline.execute(world.execute_deps(), ran.execution.id)
    refused = await world.record("count.send", {}, level="read-only")
    approved = await world.record("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    await world.client.post(f"{world.org}/approvals/{approved.approval.id}/decide", json={"decision": "approve"})
    await tool_pipeline.execute(world.execute_deps(), approved.execution.id)
    denied = await world.record("demo.send_email", {"to": "omar@acme.dev", "subject": "Hi"})
    await world.client.post(f"{world.org}/approvals/{denied.approval.id}/decide", json={"decision": "deny"})

    async with world.runs.sessionmaker() as db:
        cards = await tool_execution_service.reply_cards(db, world.run.run_id)

    assert cards == [
        {"type": "tool-call", "toolExecutionId": str(ran.execution.id), "tool": "count.lookup", "status": "succeeded"},
        {
            "type": "tool-call",
            "toolExecutionId": str(refused.execution.id),
            "tool": "count.send",
            "status": "denied",
            "error": refused.execution.error,
        },
        {"type": "approval", "approvalId": str(approved.approval.id)},
        {
            "type": "tool-call",
            "toolExecutionId": str(approved.execution.id),
            "tool": "demo.send_email",
            "status": "succeeded",
        },
        # Denied by a person: the card says so, no tool line repeats it.
        {"type": "approval", "approvalId": str(denied.approval.id)},
    ]


def odd_plugin(returns: Any) -> PluginManifest:
    """A plugin whose one tool returns whatever it's given (after doing its side effect)."""

    async def run(_args: CountArgs, _ctx: ToolContext) -> Any:
        return returns

    spec = ToolSpec(
        name="odd", title="Odd", description="odd", args_model=CountArgs, risk="write-internal", handler=run
    )
    return PluginManifest(id="odd", name="Odd", version="1", description="test", tools=(spec,))


@pytest.mark.parametrize(
    ("returns", "why"),
    [
        ({"when": datetime(2026, 11, 13, tzinfo=UTC)}, "couldn't be saved as JSON"),
        ({"id": uuid.uuid4()}, "couldn't be saved as JSON"),
        (["not", "a", "dict"], "returned a list"),
        (None, "returned None"),
    ],
)
async def test_a_tool_that_returns_something_unusable_fails_cleanly(world: World, returns: Any, why: str) -> None:
    world.registry.register(odd_plugin(returns))
    recorded = await world.record("odd.odd", {}, level="autonomous")

    outcome = await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)

    assert outcome.text.startswith("The tool failed: odd.odd ")
    assert why in outcome.text
    async with world.runs.sessionmaker() as db:
        row = await db.get(ToolExecution, recorded.execution.id)
    assert row is not None and row.status == "failed"
    assert row.error is not None and why in row.error


# A call whose outcome is unknown (ADR 0004 §2): a tool that isn't idempotent and failed after it
# may have reached the other app stays `started`, and the run stops for a person. Telling the
# model "the tool failed" would make it try again: a second email, with nobody asked.


def slow_plugin(calls: Calls) -> PluginManifest:
    """Tools with no web access that take longer than the pipeline waits."""

    async def run(_args: CountArgs, _ctx: ToolContext) -> dict[str, Any]:
        calls.count += 1
        await asyncio.sleep(5)
        return {"done": True}

    def spec(name: str, *, idempotent: bool) -> ToolSpec:
        return ToolSpec(
            name=name,
            title=name,
            description=name,
            args_model=CountArgs,
            risk="external-send",
            handler=run,
            idempotent=idempotent,
        )

    return PluginManifest(
        id="slow",
        name="Slow",
        version="1",
        description="test",
        tools=(spec("send", idempotent=False), spec("lookup", idempotent=True)),
    )


async def _row(world: World, execution_id: uuid.UUID) -> ToolExecution:
    async with world.runs.sessionmaker() as db:
        row = await db.get(ToolExecution, execution_id)
    assert row is not None
    return row


async def _tool_events(world: World, execution_id: uuid.UUID) -> list[dict[str, Any]]:
    async with world.runs.sessionmaker() as db:
        events = await db.scalars(
            select(RunEvent).where(RunEvent.run_id == world.run.run_id, RunEvent.kind == "tool_finished")
        )
        return [event.payload for event in events if event.payload["toolExecutionId"] == str(execution_id)]


async def test_a_send_that_timed_out_may_have_gone_so_a_person_checks_and_it_never_runs_again(world: World) -> None:
    world.registry.register(slow_plugin(world.calls))
    risky = await world.record("slow.send", {}, level="autonomous")
    safe = await world.record("slow.lookup", {}, level="autonomous")
    deps = dataclasses.replace(world.execute_deps(), timeout_seconds=0.05)

    with pytest.raises(NeedsAttention, match="may have been done") as stopped:
        await tool_pipeline.execute(deps, risky.execution.id)
    # The run comes back to this call (a resume, a restart): it still isn't run again.
    with pytest.raises(NeedsAttention, match="can't tell whether it finished"):
        await tool_pipeline.execute(deps, risky.execution.id)
    timed_out = await tool_pipeline.execute(deps, safe.execution.id)

    assert world.calls.count == 2  # the send once, the lookup once
    assert "took longer than 0.05 seconds" in str(stopped.value)
    assert timed_out.text == "The tool failed: It took longer than 0.05 seconds."  # idempotent: as before
    row = await _row(world, risky.execution.id)
    assert (row.status, row.result, row.finished_at) == ("started", None, None)
    assert row.error == str(stopped.value)
    # The chat's tool line stops spinning and says it may have been done.
    unknown = await _tool_events(world, risky.execution.id)
    assert unknown and all(event["status"] == "unknown" and event["error"] for event in unknown)
    assert (await _row(world, safe.execution.id)).status == "failed"


Service = Callable[[httpx.Request], httpx.Response]


def web_plugin(calls: Calls, *, idempotent: bool = False) -> PluginManifest:
    """Tools that call a web service through `ctx.http`, the way Gmail's send does."""

    async def send(args: CountArgs, ctx: ToolContext) -> dict[str, Any]:
        calls.count += 1
        response = await ctx.http.request("POST", "https://api.example.com/send", json={"text": args.text})
        if not response.ok:
            raise RuntimeError(f"The service answered {response.status_code}.")
        if args.text == "unreadable":
            raise RuntimeError("The service's answer couldn't be read.")
        if args.text == "not done":
            raise NotDone("Nothing was sent.")  # it was: BotDesk saw the request go through
        return {"sent": True}

    async def checked_send(_args: CountArgs, ctx: ToolContext) -> dict[str, Any]:
        calls.count += 1
        response = await ctx.http.request("GET", "https://api.example.com/check")
        raise RuntimeError(f"The check answered {response.status_code}, so nothing was sent.")

    async def odd_send(args: CountArgs, ctx: ToolContext) -> Any:
        method = "POST" if args.text == "send" else "GET"
        await ctx.http.request(method, "https://api.example.com/send")
        return ["an answer", "that isn't an object"]

    def spec(name: str, handler: Any) -> ToolSpec:
        return ToolSpec(
            name=name,
            title=name,
            description=name,
            args_model=CountArgs,
            risk="external-send",
            handler=handler,
            idempotent=idempotent,
        )

    return PluginManifest(
        id="web",
        name="Web",
        version="1",
        description="test",
        tools=(spec("send", send), spec("checked_send", checked_send), spec("odd_send", odd_send)),
        egress=("api.example.com",),
    )


def answers(status: int) -> Service:
    return lambda _request: httpx.Response(status, json={})


def fails(error: type[httpx.TransportError]) -> Service:
    def service(request: httpx.Request) -> httpx.Response:
        raise error("the network", request=request)

    return service


async def _web_call(world: World, service: Service, *, tool: str = "web.send", text: str = "hi") -> Any:
    """Record a call of a `web_plugin` tool (autonomous: it runs without asking), with `service`
    answering its requests. Returns the record and the deps to run it with."""
    if world.registry.plugin("web") is None:
        world.registry.register(web_plugin(world.calls))
    world.runs.tool_access.transport = httpx.MockTransport(service)
    recorded = await world.record(tool, {"text": text}, level="autonomous")
    deps = dataclasses.replace(world.execute_deps(), access=world.runs.tool_access)
    return recorded, deps


@pytest.mark.parametrize(
    "service",
    [
        answers(500),  # Gmail's "backend error": the email may be out already
        answers(503),
        fails(httpx.ReadError),  # the connection dropped after the request left
        fails(httpx.RemoteProtocolError),
        fails(httpx.ReadTimeout),  # sent, and no answer in time
        fails(httpx.WriteError),  # dropped while it was being sent
    ],
    ids=["500", "503", "read-error", "protocol-error", "read-timeout", "write-error"],
)
async def test_a_send_whose_answer_was_lost_or_failed_on_the_server_needs_a_person(
    world: World, service: Service
) -> None:
    recorded, deps = await _web_call(world, service)

    with pytest.raises(NeedsAttention, match="may have been done"):
        await tool_pipeline.execute(deps, recorded.execution.id)
    with pytest.raises(NeedsAttention):  # never run again
        await tool_pipeline.execute(deps, recorded.execution.id)

    assert world.calls.count == 1
    assert (await _row(world, recorded.execution.id)).status == "started"
    # One line, said once: coming back to the call doesn't add another.
    assert [event["status"] for event in await _tool_events(world, recorded.execution.id)] == ["unknown"]


async def test_a_send_that_went_through_but_failed_afterwards_needs_a_person(world: World) -> None:
    # Saying "nothing was done" doesn't outweigh the request BotDesk saw go through.
    for text in ("unreadable", "not done"):
        recorded, deps = await _web_call(world, answers(200), text=text)
        with pytest.raises(NeedsAttention):
            await tool_pipeline.execute(deps, recorded.execution.id)
        assert (await _row(world, recorded.execution.id)).status == "started"


@pytest.mark.parametrize(
    ("service", "why"),
    [
        (answers(400), "answered 400"),  # refused: nothing was sent
        (answers(403), "answered 403"),
        (answers(404), "answered 404"),
        (answers(429), "answered 429"),
        (fails(httpx.ConnectError), "Couldn't reach api.example.com"),  # never connected
        (fails(httpx.ConnectTimeout), "took too long"),
    ],
    ids=["400", "403", "404", "429", "connect-error", "connect-timeout"],
)
async def test_a_send_that_certainly_did_not_go_fails_and_the_model_may_try_again(
    world: World, service: Service, why: str
) -> None:
    recorded, deps = await _web_call(world, service)

    outcome = await tool_pipeline.execute(deps, recorded.execution.id)

    assert outcome.text.startswith("The tool failed: ") and why in outcome.text
    row = await _row(world, recorded.execution.id)
    assert row.status == "failed" and row.error is not None and why in row.error
    assert [event["status"] for event in await _tool_events(world, recorded.execution.id)] == ["failed"]


async def test_a_tool_that_stops_after_only_reading_fails_even_when_the_read_failed(world: World) -> None:
    for service in (answers(200), answers(503), fails(httpx.ReadError)):
        recorded, deps = await _web_call(world, service, tool="web.checked_send")
        outcome = await tool_pipeline.execute(deps, recorded.execution.id)
        assert outcome.text.startswith("The tool failed: ")
        assert (await _row(world, recorded.execution.id)).status == "failed"


async def test_an_idempotent_tool_that_fails_fails_as_before(world: World) -> None:
    world.registry.register(web_plugin(world.calls, idempotent=True))
    recorded, deps = await _web_call(world, answers(503))

    outcome = await tool_pipeline.execute(deps, recorded.execution.id)

    assert outcome.text == "The tool failed: The service answered 503."
    assert (await _row(world, recorded.execution.id)).status == "failed"


def raising_plugin(risk: RiskClass, error: Exception) -> PluginManifest:
    """A tool with no web access that raises `error`."""

    async def run(_args: CountArgs, _ctx: ToolContext) -> dict[str, Any]:
        raise error

    spec = ToolSpec(name="act", title="Act", description="act", args_model=CountArgs, risk=risk, handler=run)
    return PluginManifest(id="raising", name="Raising", version="1", description="test", tools=(spec,))


@pytest.mark.parametrize(
    ("risk", "error", "unknown"),
    [
        ("external-send", RuntimeError("the outbox broke"), True),  # BotDesk can't see what it did
        ("external-send", NotDone("The draft changed, so nothing was sent."), False),  # the tool says so
        ("write-external", RuntimeError("halfway"), True),
        ("read", RuntimeError("lookup broke"), False),  # reading again changes nothing
        ("write-internal", RuntimeError("note broke"), False),  # inside BotDesk only
    ],
)
async def test_without_web_access_only_the_tool_can_say_nothing_was_done(
    world: World, risk: RiskClass, error: Exception, unknown: bool
) -> None:
    world.registry.register(raising_plugin(risk, error))
    recorded = await world.record("raising.act", {}, level="autonomous")
    assert recorded.approval is None  # autonomous: it runs without asking

    if unknown:
        with pytest.raises(NeedsAttention, match="may have been done"):
            await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)
        assert (await _row(world, recorded.execution.id)).status == "started"
    else:
        outcome = await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)
        assert outcome.text == f"The tool failed: {error}"
        assert (await _row(world, recorded.execution.id)).status == "failed"


async def test_a_send_that_returns_something_unusable_may_have_gone(world: World) -> None:
    async def run(_args: CountArgs, _ctx: ToolContext) -> Any:
        return ["sent", "maybe"]

    spec = ToolSpec(
        name="send", title="Send", description="send", args_model=CountArgs, risk="external-send", handler=run
    )
    world.registry.register(PluginManifest(id="odd-send", name="Odd", version="1", description="t", tools=(spec,)))
    recorded = await world.record("odd-send.send", {}, level="autonomous")

    with pytest.raises(NeedsAttention, match="returned a list"):
        await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)
    assert (await _row(world, recorded.execution.id)).status == "started"

    # Through ctx.http BotDesk can tell: after a POST it may have gone, after only a GET it didn't.
    sent, deps = await _web_call(world, answers(200), tool="web.odd_send", text="send")
    with pytest.raises(NeedsAttention, match="returned a list"):
        await tool_pipeline.execute(deps, sent.execution.id)
    looked, deps = await _web_call(world, answers(200), tool="web.odd_send", text="look")
    outcome = await tool_pipeline.execute(deps, looked.execution.id)
    assert outcome.text.startswith("The tool failed: web.odd_send returned a list")


async def test_a_send_stopped_midway_says_it_may_have_been_done_and_is_never_run_again(world: World) -> None:
    """Stop or the run's time limit cancels a call in flight: a cancellation carries nothing out,
    so the call says on the way that it may have happened (the runner then turns a run that ran
    out of time into needs_attention, and the chat's line stops spinning)."""
    world.registry.register(slow_plugin(world.calls))
    risky = await world.record("slow.send", {}, level="autonomous")
    safe = await world.record("slow.lookup", {}, level="autonomous")
    deps = world.execute_deps()  # the tool's own limit (5 s) is longer than the run's below

    for recorded in (risky, safe):
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):  # the run's time limit, or Stop
                await tool_pipeline.execute(deps, recorded.execution.id)

    row = await _row(world, risky.execution.id)
    assert row.status == "started" and row.error is not None and "stopped while it was running" in row.error
    assert [event["status"] for event in await _tool_events(world, risky.execution.id)] == ["unknown"]
    assert (await _row(world, safe.execution.id)).error is None  # idempotent: running it again is fine
    async with world.runs.sessionmaker() as db:
        assert await tool_execution_service.unknown_outcome(db, world.run.run_id) == row.error

    with pytest.raises(NeedsAttention, match="stopped while it was running"):
        await tool_pipeline.execute(deps, risky.execution.id)
    assert world.calls.count == 2  # each ran once
    assert len(await _tool_events(world, risky.execution.id)) == 1


async def test_arguments_that_no_longer_fit_fail_before_the_tool_runs(world: World) -> None:
    world.registry.register(raising_plugin("external-send", RuntimeError("it ran")))
    recorded = await world.record("raising.act", {}, level="autonomous")
    async with world.runs.sessionmaker() as db:
        await db.execute(
            update(ToolExecution).where(ToolExecution.id == recorded.execution.id).values(args={"text": 5})
        )
        await db.commit()

    outcome = await tool_pipeline.execute(world.execute_deps(), recorded.execution.id)

    assert outcome.text.startswith("The tool failed: The arguments don't fit raising.act any more")
    assert (await _row(world, recorded.execution.id)).status == "failed"

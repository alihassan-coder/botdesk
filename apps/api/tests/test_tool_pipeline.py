"""The tool pipeline and approvals, on SQLite: pipeline decisions, the registry, the stand-in's
`/tool` command, "runs at most once", and deciding an approval exactly once over HTTP.
The real pause and resume (LangGraph + Postgres checkpoints) is in test_approvals_postgres.py.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from botdesk_demo import demo_plugin
from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolSpec
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import update

from src.core.database import utcnow
from src.main import create_app
from src.models import Approval, Run, ToolExecution
from src.models.bot import SecurityLevel
from src.plugins.registry import ToolRegistry, build_registry
from src.runtime import tool_pipeline
from src.runtime.chat_model import StandInModel, parse_tool_command
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
        build_registry(["gmail"])


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

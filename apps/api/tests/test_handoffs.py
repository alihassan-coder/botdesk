"""Handoffs end to end (ADR 0014) on SQLite, with the in-process job queue and a scripted model
that plays every bot: a run hands tasks to teammates with `team.handoff`, pauses
(`waiting_handoff`), the children run one after another in the same chat, and the parent resumes
once with their results, writing a new message.

The Postgres-only cases (two children ending at the same instant, a worker restart while the
parent waits) are in `test_handoffs_postgres.py`."""

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import utcnow
from src.jobs.queue import JobEnv
from src.jobs.tasks import expire_tasks
from src.models import Message, Run, RunEvent, Task, ToolExecution, UsageRecord
from src.runtime.chat_model import StandInModel
from src.runtime.graph import build_graph
from src.runtime.memory import MemoryScope, NoMemory
from src.runtime.toolset import ConnectionRow, RunScope, usable
from src.services import run_service
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

ORGS = "/api/v1/orgs"
Step = tuple[str, list[tuple[str, dict[str, Any]]]]  # the text, then the tool calls of one model step


def handoff(bot: str, task: str, **extra: Any) -> tuple[str, dict[str, Any]]:
    return "team.handoff", {"bot": bot, "task": task, **extra}


class TeamModel(StandInModel):
    """Plays every bot, told apart by the name in its instructions ("You are Chief, …").
    `plans[name]` is that bot's steps; a bot past its plan (or without one) answers
    `replies[name]`, or "{name} finished: {the task}". Several tool calls in one step are fine."""

    plans: dict[str, list[Step]] = Field(default_factory=dict)
    replies: dict[str, str] = Field(default_factory=dict)
    prompts: dict[str, list[list[BaseMessage]]] = Field(default_factory=dict)

    @staticmethod
    def bot_of(messages: list[BaseMessage]) -> str:
        system = next((m.text for m in messages if isinstance(m, SystemMessage)), "")
        return system.removeprefix("You are ").split(",", 1)[0]

    def _plan(self, messages: list[BaseMessage]) -> tuple[str, list[dict[str, Any]]]:
        bot = self.bot_of(messages)
        self.prompts.setdefault(bot, []).append(messages)
        step = sum(1 for m in messages if isinstance(m, AIMessage) and m.tool_calls)
        plan = self.plans.get(bot, [])
        if step < len(plan):
            text, calls = plan[step]
            return text, [
                {"name": name.replace(".", "__", 1), "args": args, "id": f"call_{step}_{index}"}
                for index, (name, args) in enumerate(calls)
            ]
        if bot in self.replies:
            return self.replies[bot], []
        last_human = next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        if last_human.startswith("<task-results>"):
            return f"{bot} put the results together.", []  # never echo other bots' @handles
        return f"{bot} finished: {last_human}", []

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text, calls = self._plan(messages)
        message = AIMessage(content=text, tool_calls=[{**call, "type": "tool_call"} for call in calls])
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _chunks(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
        text, calls = self._plan(messages)
        if text:
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
        for index, call in enumerate(calls):
            chunk = tool_call_chunk(name=call["name"], args=json.dumps(call["args"]), id=call["id"], index=index)
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[chunk]))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._chunks(messages):
            yield chunk


class RecordingMemory(NoMemory):
    def __init__(self) -> None:
        self.remembered: list[MemoryScope] = []

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        self.remembered.append(scope)


@dataclass
class Org:
    app: FastAPI
    client: httpx.AsyncClient
    model: TeamModel
    memory: RecordingMemory
    path: str
    org_id: uuid.UUID
    user_id: uuid.UUID
    bots: dict[str, uuid.UUID]  # handle → id
    held: list[Run] = field(default_factory=list)  # children whose jobs are held back

    def db(self) -> AsyncSession:
        sessionmaker: async_sessionmaker[AsyncSession] = self.app.state.sessionmaker
        return sessionmaker()

    @property
    def runs(self) -> Any:
        return self.app.state.runs

    async def dm(self, handle: str) -> str:
        thread = (await self.client.post(f"{self.path}/threads/dm", json={"botId": str(self.bots[handle])})).json()
        return f"{self.path}/threads/{thread['id']}"

    async def group(self, *handles: str) -> str:
        body = {
            "title": "Launch",
            "botIds": [str(self.bots[h]) for h in handles],
            "leadBotId": str(self.bots[handles[0]]),
        }
        thread = (await self.client.post(f"{self.path}/threads/groups", json=body)).json()
        return f"{self.path}/threads/{thread['id']}"

    async def send(self, thread: str, text: str) -> uuid.UUID:
        sent = await self.client.post(f"{thread}/messages", json={"text": text})
        assert sent.status_code == 201, sent.text
        run_id = uuid.UUID(sent.json()["runIds"][0])
        await self.runs.wait_until_idle()
        return run_id

    def hold_children(self) -> None:
        """Children's jobs aren't deferred (as if lost): they stay queued until `release`."""
        start = self.runs.start

        async def holding(db: AsyncSession, runs: list[Run]) -> None:
            self.held.extend(run for run in runs if run.parent_run_id is not None and run.hop > 0)
            await start(db, [run for run in runs if run not in self.held])

        self.runs.start = holding

    async def release(self, run_id: uuid.UUID) -> None:
        async with self.db() as db:
            run = await db.get(Run, run_id)
            assert run is not None
            await self.runs.queue.defer(_job(run), db=db)
            await db.commit()
        await self.runs.wait_until_idle()

    async def run(self, run_id: uuid.UUID) -> Run:
        async with self.db() as db:
            run = await db.get(Run, run_id)
            assert run is not None
            return run

    async def tasks(self, parent: uuid.UUID) -> list[Task]:
        async with self.db() as db:
            rows = await db.scalars(select(Task).where(Task.parent_run_id == parent).order_by(Task.created_at))
            return list(rows)

    async def messages(self, thread: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = (await self.client.get(f"{thread}/messages")).json()
        return messages

    async def events(self, run_id: uuid.UUID | None = None) -> list[tuple[str, dict[str, Any], uuid.UUID | None]]:
        async with self.db() as db:
            query = select(RunEvent).order_by(RunEvent.id)
            if run_id is not None:
                query = query.where(RunEvent.run_id == run_id)
            return [(e.kind, e.payload, e.run_id) for e in await db.scalars(query)]

    async def stop(self, run_id: uuid.UUID) -> dict[str, Any]:
        response = await self.client.post(f"{self.path}/runs/{run_id}/cancel")
        assert response.status_code == 200, response.text
        await self.runs.wait_until_idle()
        body: dict[str, Any] = response.json()
        return body

    def prompt_text(self, bot: str, index: int = -1) -> str:
        return "\n".join(m.text for m in self.model.prompts[bot][index])


def _job(run: Run) -> Any:
    from src.runtime.runner import run_job

    return run_job(run.id, run.thread_id)


@pytest.fixture
async def org(providers: FakeProviders) -> AsyncIterator[Org]:
    """Ali's organization: Chief (autonomous), Sales and Research. Runs really run here."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        model, memory = TeamModel(), RecordingMemory()

        async def model_for(_org_id: uuid.UUID, _model_id: str) -> BaseChatModel:
            return model

        app.state.runs.enabled = True
        app.state.runs.model_for = model_for
        app.state.runs.memory = memory
        me = await sign_up(client)
        path = f"{ORGS}/{me['organizations'][0]['id']}"
        bots = {}
        for name, role in (("Chief", "Coordinator"), ("Sales", "Sales"), ("Research", "")):
            body = {"name": name, "role": role, "securityLevel": "autonomous"}
            bot = (await client.post(f"{path}/bots", json=body)).json()
            bots[bot["handle"]] = uuid.UUID(bot["id"])
        yield Org(
            app,
            client,
            model,
            memory,
            path,
            uuid.UUID(me["organizations"][0]["id"]),
            uuid.UUID(me["user"]["id"]),
            bots,
        )


TWO_TASKS: list[Step] = [
    ("I'll ask Sales and Research.", [handoff("@sales", "Draft openers"), handoff("research", "Pull numbers")])
]


async def test_chief_hands_off_two_tasks_and_resumes_once_with_both_results(org: Org) -> None:
    org.model.plans["Chief"] = TWO_TASKS
    org.model.replies["Chief"] = "Here is tonight's plan."
    thread = await org.dm("chief")

    parent = await org.send(thread, "Plan tonight's outreach")

    assert (await org.run(parent)).status == "succeeded"
    sales_task, research_task = await org.tasks(parent)
    assert (sales_task.status, research_task.status) == ("done", "done")
    sales = await org.run(sales_task.child_run_id)  # type: ignore[arg-type]
    assert (sales.hop, sales.parent_run_id, sales.trigger_message_id) == (1, parent, sales_task.message_id)

    # The chat: Ali, the handoff message, Sales's reply, Research's reply, then Chief's new answer.
    messages = await org.messages(thread)
    authors = [(m["author"]["type"], m["author"]["id"]) for m in messages]
    assert authors == [
        ("user", str(org.user_id)),
        ("bot", str(org.bots["chief"])),
        ("bot", str(org.bots["sales"])),
        ("bot", str(org.bots["research"])),
        ("bot", str(org.bots["chief"])),
    ]
    handoff_message, sales_reply, _research_reply, final = messages[1:]
    assert handoff_message["id"] == str(sales_task.message_id)
    assert handoff_message["parts"][0] == {"type": "text", "text": "I'll ask Sales and Research."}
    cards = handoff_message["parts"][1:]
    assert [(c["type"], c["taskId"], c["status"]) for c in cards] == [
        ("handoff", str(sales_task.id), "done"),
        ("handoff", str(research_task.id), "done"),
    ]
    assert cards[0]["resultMessageId"] == sales_reply["id"] == str(sales.reply_message_id)
    assert cards[0]["resultPreview"] == "Sales finished: Task from Chief (@chief): Draft openers"
    assert final["id"] == str((await org.run(parent)).reply_message_id)
    assert final["parts"] == [{"type": "text", "text": "Here is tonight's plan."}]  # no handoff tool line

    # Chief's last step read both results as other bots' output.
    results = org.model.prompts["Chief"][-1][-1]
    assert isinstance(results, HumanMessage) and results.text.startswith("<task-results>")
    assert '<task-result task="Draft openers" bot="Sales (@sales)" status="done">' in results.text
    assert "Sales finished: Task from Chief (@chief): Draft openers" in results.text
    assert results.text.endswith("Now continue with the person's request.")
    tool_results = [m for m in org.model.prompts["Chief"][-1] if isinstance(m, ToolMessage)]
    assert [json.loads(m.text)["bot"] for m in tool_results] == ["@sales", "@research"]
    assert json.loads(tool_results[0].text)["status"] == "queued"


async def test_the_events_of_a_handoff(org: Org) -> None:
    org.model.plans["Chief"] = TWO_TASKS
    thread = await org.dm("chief")

    parent = await org.send(thread, "Plan tonight's outreach")

    sales_task, research_task = await org.tasks(parent)
    events = await org.events()
    kinds = [(kind, run) for kind, _, run in events if kind != "message_delta"]
    paused = kinds.index(("run_waiting_handoff", parent))
    children_started = [i for i, (kind, run) in enumerate(kinds) if kind == "run_started" and run != parent]
    assert len(children_started) == 2 and paused < min(children_started)  # children run after the pause
    parent_kinds = [kind for kind, run in kinds if run == parent]
    assert parent_kinds == [
        "run_started",
        "message_saved",  # the handoff message, with Sales's card
        "task_updated",
        "message_saved",  # rewritten with Research's card
        "task_updated",
        "message_saved",  # save_progress
        "run_waiting_handoff",
        "task_updated",  # Sales working
        "task_updated",  # Sales done
        "task_updated",  # Research working
        "task_updated",  # Research done
        "run_resumed",
        "message_saved",  # the final answer
        "run_finished",
    ]
    waiting = next(data for kind, data, _ in events if kind == "run_waiting_handoff")
    assert waiting == {"status": "waiting_handoff", "taskIds": [str(sales_task.id), str(research_task.id)]}
    resumed = [data for kind, data, run in events if kind == "run_resumed"]
    assert resumed == [{"botId": str(org.bots["chief"]), "after": "tasks"}]
    updates = [data["task"] for kind, data, _ in events if kind == "task_updated"]
    assert [(u["id"], u["status"]) for u in updates] == [
        (str(sales_task.id), "queued"),
        (str(research_task.id), "queued"),
        (str(sales_task.id), "working"),
        (str(sales_task.id), "done"),
        (str(research_task.id), "working"),
        (str(research_task.id), "done"),
    ]
    assert all(u["status"] for u in updates)  # always the whole task
    assert not [kind for kind, data, _ in events if kind in ("tool_started", "tool_finished")]
    active = (await org.client.get(f"{thread}/runs", params={"active": True})).json()
    assert active["runs"] == []


async def test_a_handoff_and_a_risky_call_in_one_step(org: Org) -> None:
    await org.client.patch(f"{org.path}/bots/{org.bots['chief']}", json={"securityLevel": "ask-before-acting"})
    send = ("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})
    org.model.plans["Chief"] = [("On it.", [handoff("sales", "Draft openers"), send])]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Do both")

    # Paused for the approval; the child ran meanwhile.
    assert (await org.run(parent)).status == "waiting_approval"
    (task,) = await org.tasks(parent)
    assert task.status == "done"
    (approval,) = (await org.client.get(f"{org.path}/approvals")).json()
    decided = await org.client.post(f"{org.path}/approvals/{approval['id']}/decide", json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    await org.runs.wait_until_idle()

    # Then it paused for its task, and resume_if_ready resumed it at once.
    assert (await org.run(parent)).status == "succeeded"
    resumed = [data for kind, data, run in await org.events(parent) if kind == "run_resumed"]
    assert [data["after"] for data in resumed] == ["approval", "tasks"]
    handoff_message, final = (await org.messages(thread))[1], (await org.messages(thread))[-1]
    assert [p["type"] for p in handoff_message["parts"]] == ["approval", "tool-call", "text", "handoff"]
    assert all(p["type"] == "text" for p in final["parts"])  # its cards were shown before


async def test_nested_handoffs_resume_each_parent_in_turn(org: Org) -> None:
    org.model.plans["Chief"] = [("Asking Sales.", [handoff("sales", "Plan the outreach")])]
    org.model.plans["Sales"] = [("Asking Research.", [handoff("research", "Find accounts")])]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    (chief_task,) = await org.tasks(parent)
    (sales_task,) = await org.tasks(chief_task.child_run_id)  # type: ignore[arg-type]
    research = await org.run(sales_task.child_run_id)  # type: ignore[arg-type]
    assert research.hop == 2
    assert (chief_task.status, sales_task.status, (await org.run(parent)).status) == ("done", "done", "succeeded")
    sales_results = org.model.prompts["Sales"][-1][-1].text
    assert 'bot="Research (@research)" status="done"' in sales_results


# Refusals and the tool


async def test_a_refused_handoff_tells_the_model_and_makes_nothing(org: Org) -> None:
    org.model.plans["Chief"] = [("", [handoff("@marketing", "Write copy")])]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    assert (await org.run(parent)).status == "succeeded"
    assert await org.tasks(parent) == []
    tool_result = next(m for m in org.model.prompts["Chief"][-1] if isinstance(m, ToolMessage))
    assert tool_result.text == (
        "The tool failed: There's no bot @marketing in this organization. "
        "Your teammates are listed in your instructions."
    )
    async with org.db() as db:
        (execution,) = await db.scalars(select(ToolExecution))
    assert (execution.tool_name, execution.status) == ("team.handoff", "failed")
    assert [m["author"]["type"] for m in await org.messages(thread)] == ["user", "bot"]
    assert not [kind for kind, *_ in await org.events() if kind in ("task_updated", "run_waiting_handoff")]


async def test_a_bot_with_team_switched_off_isnt_offered_the_tool(org: Org) -> None:
    switched = await org.client.put(
        f"{org.path}/bots/{org.bots['chief']}/tools",
        json={"plugins": [{"pluginId": "team", "enabled": False, "connectionId": None}]},
    )
    assert switched.status_code == 200, switched.text
    org.model.plans["Chief"] = [("", [handoff("sales", "Draft openers")])]
    thread = await org.dm("chief")

    await org.send(thread, "Go")

    first_prompt = org.prompt_text("Chief", 0)
    assert "team__handoff" not in first_prompt
    tool_result = next(m for m in org.model.prompts["Chief"][-1] if isinstance(m, ToolMessage))
    assert tool_result.text == "There is no tool called team__handoff."


async def test_the_team_plugin_is_on_every_bots_tools_tab(org: Org) -> None:
    tools = (await org.client.get(f"{org.path}/bots/{org.bots['sales']}/tools")).json()["plugins"]
    team = next(p for p in tools if p["pluginId"] == "team")
    assert (team["name"], team["enabled"], team["authType"]) == ("Team", True, None)
    assert [t["title"] for t in team["tools"]] == ["Hand off"]
    plugins = (await org.client.get(f"{org.path}/plugins")).json()
    assert "team" not in [p["id"] for p in plugins]


async def test_the_prompt_lists_teammates_and_a_child_is_told_its_task(org: Org) -> None:
    org.model.plans["Chief"] = [("", [handoff("sales", "Draft openers", context="Top 5 accounts")])]
    thread = await org.dm("chief")

    await org.send(thread, "Go")

    chief = org.prompt_text("Chief", 0)
    assert "You can hand tasks to teammates with team__handoff." in chief
    assert "Teammates:\n- Research (@research)\n- Sales (@sales): Sales" in chief
    sales_system = org.model.prompts["Sales"][0][0].text
    assert (
        "Chief (@chief) handed you a task for Ali Hassan. Do it with your own tools, then reply with the result: "
        "your reply goes back to Chief automatically, so don't @mention it. If you can't do it, say why."
    ) in sales_system
    assert "guest" not in sales_system and "Another bot @mentioned you" not in sales_system
    trigger = org.model.prompts["Sales"][0][-1]
    assert isinstance(trigger, HumanMessage)
    assert trigger.text == "Task from Chief (@chief): Draft openers\n\nContext: Top 5 accounts"


# Safety


async def test_a_tainted_parent_starts_a_tainted_child_whose_risky_calls_ask(org: Org) -> None:
    org.model.plans["Chief"] = [("", [handoff("sales", "Send the email")])]
    org.model.plans["Sales"] = [("", [("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})])]
    thread = await org.dm("chief")
    org.hold_children()
    parent = await org.send(thread, "Go")
    async with org.db() as db:
        await db.execute(update(Run).where(Run.id == parent).values(tainted=True))
        await db.commit()
    (child,) = org.held
    # The parent's state was clean when it handed off, so mark the child as a tainted parent would.
    async with org.db() as db:
        await db.execute(update(Run).where(Run.id == child.id).values(tainted=True))
        await db.commit()

    await org.release(child.id)

    assert (await org.run(child.id)).status == "waiting_approval"  # external-send asks, even autonomous
    (approval,) = (await org.client.get(f"{org.path}/approvals")).json()
    assert approval["tainted"] is True


async def test_taint_goes_down_with_the_handoff(org: Org) -> None:
    org.model.plans["Chief"] = [
        ("", [("demo.read_inbox", {})]),
        ("", [handoff("sales", "Reply to it")]),
    ]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Read my inbox and get Sales to reply")

    (task,) = await org.tasks(parent)
    assert (await org.run(parent)).tainted is True
    assert (await org.run(task.child_run_id)).tainted is True  # type: ignore[arg-type]


async def test_a_tainted_child_taints_its_parent_and_the_handoff_message(org: Org) -> None:
    org.model.plans["Chief"] = [("", [handoff("sales", "Read the inbox")])]
    org.model.plans["Sales"] = [("", [("demo.read_inbox", {})])]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    (task,) = await org.tasks(parent)
    assert (await org.run(task.child_run_id)).tainted is True  # type: ignore[arg-type]
    assert (await org.run(parent)).tainted is True  # the row, after the resume
    results = org.model.prompts["Chief"][-1][-1].text
    assert 'status="done"' in results
    # A later run that reads the handoff message is tainted too.
    later = await org.send(thread, "Thanks")
    async with org.db() as db:
        context = await run_service.run_context(db, later)
    assert context.tainted is True
    assert '(handed @sales a task: "Read the inbox", done)' in [line.text for line in context.history][1]


async def test_a_child_is_never_looser_than_its_parent(org: Org) -> None:
    await org.client.patch(f"{org.path}/bots/{org.bots['chief']}", json={"securityLevel": "read-only"})
    org.model.plans["Chief"] = [("", [handoff("sales", "Send it")])]
    org.model.plans["Sales"] = [("", [("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})])]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    (task,) = await org.tasks(parent)
    child = await org.run(task.child_run_id)  # type: ignore[arg-type]
    assert child.security_level == "read-only"
    async with org.db() as db:
        assert (await run_service.run_context(db, child.id)).security_level == "read-only"
        send = await db.scalar(select(ToolExecution).where(ToolExecution.run_id == child.id))
    assert send is not None and (send.tool_name, send.decision, send.status) == ("demo.send_email", "deny", "denied")


async def test_a_child_inherits_the_requester_and_the_connections_rule_holds(org: Org) -> None:
    org.hold_children()
    org.model.plans["Chief"] = [("", [handoff("sales", "Use my mailbox")])]
    chief_dm = await org.dm("chief")
    parent = await org.send(chief_dm, "Go")
    (child,) = org.held
    assert child.requester_id == (await org.run(parent)).requester_id == org.user_id

    sara_mail = ConnectionRow(
        id=uuid.uuid4(),
        connector_id="demo",
        account_label="ali@acme.dev",
        owner_kind="member",
        owner_user_id=org.user_id,
        owner_bot_id=None,
        status="active",
    )

    def scope(run: Run, kind: str, thread_bot: uuid.UUID | None) -> RunScope:
        return RunScope(run.bot_id, run.requester_id, kind, org.user_id, thread_bot)

    # In Ali's DM with Chief, Sales isn't the DM's bot: no member connection.
    assert not usable(sara_mail, scope(child, "dm", org.bots["chief"]))
    # In a group: never.
    assert not usable(sara_mail, scope(child, "group", None))
    # In Ali's own DM with Sales (Chief handed back to Sales there): yes.
    assert usable(sara_mail, scope(child, "dm", org.bots["sales"]))
    org_owned = ConnectionRow(uuid.uuid4(), "demo", "Acme", "org", None, None, "active")
    sales_owned = ConnectionRow(uuid.uuid4(), "demo", "Sales", "bot", None, org.bots["sales"], "active")
    assert usable(org_owned, scope(child, "group", None)) and usable(sales_owned, scope(child, "group", None))


async def test_a_child_saves_no_memories(org: Org) -> None:
    org.model.plans["Chief"] = [("", [handoff("sales", "Draft openers")])]
    thread = await org.dm("chief")

    await org.send(thread, "Go")

    assert [scope.bot_id for scope in org.memory.remembered] == [org.bots["chief"]]


async def test_a_childs_reply_mentioning_its_parents_bot_starts_nothing(org: Org) -> None:
    org.model.plans["Chief"] = [("Asking @research too.", [handoff("sales", "Draft openers")])]
    org.model.replies["Sales"] = "Done, @chief."
    org.model.replies["Chief"] = "All set."
    thread = await org.group("chief", "sales", "research")

    parent = await org.send(thread, "@chief go")

    async with org.db() as db:
        runs = list(await db.scalars(select(Run).order_by(Run.created_at)))
    # Chief and its child only: the handoff message's @research and Sales's @chief start nothing.
    assert [run.bot_id for run in runs] == [org.bots["chief"], org.bots["sales"]]
    assert (await org.run(parent)).status == "succeeded"


async def test_in_a_dm_a_handed_off_bot_joins_like_a_guest(org: Org) -> None:
    org.model.plans["Chief"] = [("", [handoff("sales", "Draft openers")])]
    org.model.replies["Chief"] = "Thanks @sales, can you also send them?"
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    (task,) = await org.tasks(parent)
    async with org.db() as db:
        context = await run_service.run_context(db, task.child_run_id)  # type: ignore[arg-type]
        runs = list(await db.scalars(select(Run).where(Run.parent_run_id == parent).order_by(Run.created_at)))
    assert context.guest is False and context.task is not None
    # Sales is now one of the DM's bots, so Chief's final @mention reaches it (one hop on).
    assert [(run.bot_id, run.hop) for run in runs] == [(org.bots["sales"], 1), (org.bots["sales"], 1)]
    assert runs[1].trigger_message_id == (await org.run(parent)).reply_message_id


# Stop, timeouts, budgets, restarts


async def _waiting_with_held_children(org: Org, thread: str) -> tuple[uuid.UUID, list[Run]]:
    org.hold_children()
    org.model.plans["Chief"] = TWO_TASKS
    parent = await org.send(thread, "Plan tonight's outreach")
    assert (await org.run(parent)).status == "waiting_handoff"
    return parent, list(org.held)


async def test_stopping_a_waiting_parent_cancels_its_tasks_and_children(org: Org) -> None:
    thread = await org.dm("chief")
    parent, children = await _waiting_with_held_children(org, thread)
    active = (await org.client.get(f"{thread}/runs", params={"active": True})).json()
    tasks = await org.tasks(parent)
    assert [(r["id"], r["status"], r["taskIds"]) for r in active["runs"] if r["id"] == str(parent)] == [
        (str(parent), "waiting_handoff", [str(t.id) for t in tasks])
    ]
    assert active["replayFrom"] == active["lastEventId"]  # a paused run doesn't move the replay

    stopped = await org.stop(parent)

    assert stopped["status"] == "cancelled"
    assert [t.status for t in await org.tasks(parent)] == ["cancelled", "cancelled"]
    assert [(await org.run(c.id)).status for c in children] == ["cancelled", "cancelled"]
    assert not [kind for kind, *_ in await org.events(parent) if kind == "run_resumed"]
    task = (await org.tasks(parent))[0]
    assert task.error == "Cancelled: Chief stopped before it finished."


async def test_stopping_a_parent_cascades_to_grandchildren(org: Org) -> None:
    org.model.plans["Sales"] = [("", [handoff("research", "Find accounts")])]
    org.model.plans["Chief"] = [("", [handoff("sales", "Plan")])]
    thread = await org.dm("chief")
    start = org.runs.start
    held: list[Run] = []

    async def hold_grandchildren(db: AsyncSession, runs: list[Run]) -> None:
        held.extend(run for run in runs if run.hop == 2)
        await start(db, [run for run in runs if run.hop != 2])

    org.runs.start = hold_grandchildren
    parent = await org.send(thread, "Go")
    (chief_task,) = await org.tasks(parent)
    assert (await org.run(chief_task.child_run_id)).status == "waiting_handoff"  # type: ignore[arg-type]

    await org.stop(parent)

    (grandchild,) = held
    assert (await org.run(chief_task.child_run_id)).status == "cancelled"  # type: ignore[arg-type]
    assert (await org.run(grandchild.id)).status == "cancelled"
    (sales_task,) = await org.tasks(chief_task.child_run_id)  # type: ignore[arg-type]
    assert sales_task.status == "cancelled"


async def test_stopping_a_child_fails_only_its_task_and_the_parent_resumes_told_so(org: Org) -> None:
    thread = await org.dm("chief")
    parent, (sales, research) = await _waiting_with_held_children(org, thread)

    await org.stop(sales.id)

    sales_task, research_task = await org.tasks(parent)
    assert (sales_task.status, sales_task.error_code, research_task.status) == ("failed", "stopped", "queued")
    assert (await org.run(parent)).status == "waiting_handoff"  # Research is still open
    await org.release(research.id)

    assert (await org.run(parent)).status == "succeeded"
    results = org.model.prompts["Chief"][-1][-1].text
    assert 'bot="Sales (@sales)" status="failed" error="Stopped before it finished."' in results


async def test_a_task_past_its_deadline_times_out_and_the_parent_carries_on(org: Org) -> None:
    thread = await org.dm("chief")
    parent, (sales, research) = await _waiting_with_held_children(org, thread)
    await org.release(sales.id)  # Sales finishes; Research is stuck (queued, never started)
    an_hour_ago = utcnow() - timedelta(minutes=61)
    async with org.db() as db:
        await db.execute(
            update(Task)
            .where(Task.child_run_id == research.id)
            .values(created_at=an_hour_ago, deadline_at=an_hour_ago + timedelta(minutes=60))
        )
        await db.commit()

    env = JobEnv(runs=org.runs, queue=org.runs.queue, sessionmaker=org.app.state.sessionmaker, settings=TEST_SETTINGS)
    # The parent's resume is deferred but held back until the child is stopped: the in-memory
    # test database has one connection, which a job running alongside would share.
    org.runs.enabled = False
    await expire_tasks(env, timestamp=0)
    assert (await org.run(parent)).status == "waiting_handoff"  # its job wasn't deferred (held)
    org.runs.enabled = True
    await org.runs.reconcile_tasks()  # what the deferred job would have done: resume it
    await org.runs.wait_until_idle()

    tasks = {task.child_run_id: task for task in await org.tasks(parent)}  # research's is older now
    sales_task, research_task = tasks[sales.id], tasks[research.id]
    assert sales_task.status == "done"
    assert (research_task.status, research_task.error_code) == ("failed", "timeout")
    assert research_task.error == "Timed out after 60 minutes."
    assert (await org.run(research.id)).status == "cancelled"  # the child was stopped
    assert (await org.run(parent)).status == "succeeded"
    assert 'status="failed" error="Timed out after 60 minutes."' in org.model.prompts["Chief"][-1][-1].text
    # The child's own end (it was cancelled) changed nothing.
    assert (await org.tasks(parent))[0].error_code == "timeout"


async def test_a_child_out_of_budget_fails_its_task_with_the_budget_message(org: Org) -> None:
    await org.client.patch(f"{org.path}/bots/{org.bots['sales']}", json={"monthlyBudgetUsd": 1})
    async with org.db() as db:
        db.add(
            UsageRecord(
                org_id=org.org_id,
                bot_id=org.bots["sales"],
                provider="anthropic",
                model_id="anthropic:claude-sonnet-4-5",
                input_tokens=1,
                output_tokens=1,
                cost_usd=5.0,
                created_at=utcnow(),
            )
        )
        await db.commit()
    org.model.plans["Chief"] = [("", [handoff("sales", "Draft openers")])]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    (task,) = await org.tasks(parent)
    assert (task.status, task.error_code) == ("failed", "budget")
    assert task.error and "budget" in task.error
    assert (await org.run(parent)).status == "succeeded"
    assert f'status="failed" error="{task.error}"' in org.model.prompts["Chief"][-1][-1].text


async def test_after_a_restart_on_sqlite_the_waiting_parent_fails_and_its_tasks_end(org: Org) -> None:
    thread = await org.dm("chief")
    parent, _children = await _waiting_with_held_children(org, thread)
    # A restart: the children's jobs and every in-memory checkpoint are gone.
    org.runs._graph = build_graph(InMemorySaver())

    await org.runs.recover_after_restart()
    await org.runs.wait_until_idle()

    run = await org.run(parent)
    assert (run.status, run.error) == ("failed", run_service.LOST_PAUSE_ERROR)
    assert [(t.status, t.error) for t in await org.tasks(parent)] == [
        ("failed", run_service.RESTART_ERROR),
        ("failed", run_service.RESTART_ERROR),
    ]


async def test_a_handoff_message_is_saved_once_per_pause(org: Org) -> None:
    org.model.plans["Chief"] = [
        ("First.", [handoff("sales", "One")]),
        ("Second.", [handoff("research", "Two")]),
    ]
    thread = await org.dm("chief")

    parent = await org.send(thread, "Go")

    one, two = await org.tasks(parent)
    assert one.message_id != two.message_id
    async with org.db() as db:
        first = await db.get(Message, one.message_id)
        second = await db.get(Message, two.message_id)
    assert first is not None and second is not None
    assert [p["type"] for p in first.parts] == ["text", "handoff"] and first.parts[0]["text"] == "First."
    assert [p["type"] for p in second.parts] == ["text", "handoff"] and second.parts[0]["text"] == "Second."
    assert (await org.run(parent)).status == "succeeded"

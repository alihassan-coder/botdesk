"""The task service (ADR 0014) at its interface, on SQLite with no model: handing off, the task
state machine, cards and events, the parent's single resume, the answer it resumes with, timeouts
and recovery. Runs never start here (`client`-style app): the tests move them by hand."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.database import utcnow
from src.models import Message, Run, RunEvent, Task
from src.plugins.team import HandoffArgs
from src.services import run_service, task_service
from src.services.task_service import Aftermath, HandedOff, Refused
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

ORGS = "/api/v1/orgs"


@dataclass
class Team:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    bots: dict[str, uuid.UUID]  # handle → id
    thread: str
    parent: uuid.UUID  # Chief's run, answering Ali's message, running

    @property
    def settings(self) -> Settings:
        settings: Settings = self.app.state.settings
        return settings

    def db(self) -> AsyncSession:
        sessionmaker: async_sessionmaker[AsyncSession] = self.app.state.sessionmaker
        return sessionmaker()

    async def hand_off(
        self,
        bot: str,
        task: str = "Draft openers",
        *,
        run: uuid.UUID | None = None,
        call: str | None = None,
        message: uuid.UUID | None = None,
        reply_text: str = "I'll ask the team.",
        level: str = "autonomous",
        tainted: bool = False,
        settings: Settings | None = None,
    ) -> HandedOff | Refused:
        async with self.db() as db:
            result = await task_service.hand_off(
                db,
                parent_run_id=run or self.parent,
                tool_call_id=call or f"call_{uuid.uuid4().hex[:8]}",
                args=HandoffArgs(bot=bot, task=task),
                message_id=message or uuid.uuid4(),
                reply_text=reply_text,
                exclude_execution_ids=[],
                level=level,
                tainted=tainted,
                settings=settings or self.settings,
            )
            await db.commit()
            return result

    async def set_status(self, run_id: uuid.UUID, status: str, **values: Any) -> None:
        async with self.db() as db:
            await db.execute(update(Run).where(Run.id == run_id).values(status=status, **values))
            await db.commit()

    async def end(
        self, run_id: uuid.UUID, status: str, *, error: str | None = None, code: str | None = None, reply: str = ""
    ) -> Aftermath:
        """The run ends the way the runner ends it: finished, then `run_ended`, in one transaction."""
        async with self.db() as db:
            if reply:
                await run_service.save_reply(
                    db, run_id=run_id, message_id=uuid.uuid4(), text=reply, settings=self.settings
                )
            await db.execute(update(Run).where(Run.id == run_id).values(status=status, error=error))
            aftermath = await task_service.run_ended(db, run_id, status=status, error=error, code=code)
            await db.commit()
            return aftermath

    async def task(self, task_id: uuid.UUID) -> Task:
        async with self.db() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            return task

    async def run(self, run_id: uuid.UUID) -> Run:
        async with self.db() as db:
            run = await db.get(Run, run_id)
            assert run is not None
            return run

    async def message(self, message_id: uuid.UUID) -> Message:
        async with self.db() as db:
            message = await db.get(Message, message_id)
            assert message is not None
            return message

    async def events(self, kind: str) -> list[dict[str, Any]]:
        async with self.db() as db:
            rows = await db.scalars(select(RunEvent).where(RunEvent.kind == kind).order_by(RunEvent.id))
            return [row.payload for row in rows]

    async def count(self, model: Any) -> int:
        async with self.db() as db:
            return await db.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
async def team(providers: FakeProviders) -> AsyncIterator[Team]:
    """Ali's DM with Chief; Sales and Research are in the organization too. Chief is answering."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        me = await sign_up(client)
        org = f"{ORGS}/{me['organizations'][0]['id']}"
        bots = {}
        for name in ("Chief", "Sales", "Research"):
            bot = (await client.post(f"{org}/bots", json={"name": name})).json()
            bots[bot["handle"]] = uuid.UUID(bot["id"])
        thread = (await client.post(f"{org}/threads/dm", json={"botId": str(bots["chief"])})).json()
        path = f"{org}/threads/{thread['id']}"
        sent = await client.post(f"{path}/messages", json={"text": "Plan tonight's outreach"})
        parent = uuid.UUID(sent.json()["runIds"][0])
        t = Team(app, client, org, bots, path, parent)
        await t.set_status(parent, "running")
        yield t


async def _handed(team: Team, *args: Any, **kwargs: Any) -> HandedOff:
    result = await team.hand_off(*args, **kwargs)
    assert isinstance(result, HandedOff), result
    return result


# Handing off


async def test_a_handoff_makes_a_queued_task_a_child_run_one_hop_on_and_a_card(team: Team) -> None:
    message_id = uuid.uuid4()
    handed = await _handed(team, "@Sales", message=message_id, level="read-only", tainted=True)

    task = await team.task(handed.task.id)
    child = await team.run(handed.child.id)
    parent = await team.run(team.parent)
    assert (task.status, task.to_bot_id, task.from_bot_id) == ("queued", team.bots["sales"], team.bots["chief"])
    assert task.child_run_id == child.id and task.message_id == message_id
    assert (child.status, child.bot_id, child.hop, child.parent_run_id) == ("queued", team.bots["sales"], 1, parent.id)
    assert child.trigger_message_id == message_id
    assert child.requester_id == parent.requester_id is not None
    assert child.tainted is True  # the parent's state said tainted
    assert child.security_level == "read-only"  # the parent's effective level caps it
    assert (task.deadline_at - task.created_at) == timedelta(minutes=60)
    message = await team.message(message_id)
    assert (message.author_type, message.author_id) == ("bot", team.bots["chief"])
    assert message.parts == [
        {"type": "text", "text": "I'll ask the team."},
        {
            "type": "handoff",
            "taskId": str(task.id),
            "fromBotId": str(team.bots["chief"]),
            "toBotId": str(team.bots["sales"]),
            "task": "Draft openers",
            "status": "queued",
            "resultMessageId": None,
            "resultPreview": None,
            "error": None,
            "errorCode": None,
        },
    ]
    saved = (await team.events("message_saved"))[-1]
    assert saved["message"]["id"] == str(message_id)
    (updated,) = await team.events("task_updated")
    assert updated["task"]["id"] == str(task.id) and updated["task"]["status"] == "queued"


async def test_the_task_json_is_the_whole_task_in_camel_case(team: Team) -> None:
    handed = await _handed(team, "sales")

    (updated,) = await team.events("task_updated")

    assert set(updated["task"]) == {
        "id",
        "threadId",
        "parentRunId",
        "childRunId",
        "messageId",
        "fromBotId",
        "toBotId",
        "task",
        "status",
        "resultMessageId",
        "resultPreview",
        "error",
        "errorCode",
        "createdAt",
        "startedAt",
        "finishedAt",
        "deadlineAt",
    }
    assert updated["task"]["childRunId"] == str(handed.child.id)
    assert updated["task"]["threadId"] == team.thread.rsplit("/", 1)[1]
    assert "context" not in updated["task"] and "result" not in updated["task"]


async def test_several_handoffs_in_one_step_share_one_message_in_order(team: Team) -> None:
    message_id = uuid.uuid4()
    first = await _handed(team, "sales", "One", message=message_id)
    second = await _handed(team, "research", "Two", message=message_id)

    parts = (await team.message(message_id)).parts
    assert [part.get("taskId") for part in parts if part["type"] == "handoff"] == [
        str(first.task.id),
        str(second.task.id),
    ]


async def test_handing_off_the_same_call_twice_makes_one_task_and_one_child(team: Team) -> None:
    first = await _handed(team, "sales", call="call_1")
    again = await _handed(team, "sales", call="call_1")

    assert again.created is False
    assert again.task.id == first.task.id and again.child.id == first.child.id
    assert await team.count(Task) == 1


@pytest.mark.parametrize("handle", ["@sales", "sales", "@Sales", "SALES"])
async def test_the_handle_may_have_an_at_and_any_case(team: Team, handle: str) -> None:
    await _handed(team, handle)


async def _refused(team: Team, bot: str, **kwargs: Any) -> str:
    result = await team.hand_off(bot, **kwargs)
    assert isinstance(result, Refused), result
    return result.message


async def test_an_unknown_bot_is_refused(team: Team) -> None:
    message = await _refused(team, "@marketing")
    assert message == (
        "There's no bot @marketing in this organization. Your teammates are listed in your instructions."
    )


async def test_a_bot_of_another_organization_is_refused_as_unknown(team: Team) -> None:
    other = await sign_up(team.client, name="Omar", email="omar@globex.dev")
    await team.client.post(f"{ORGS}/{other['organizations'][0]['id']}/bots", json={"name": "Closer"})

    message = await _refused(team, "@closer")

    assert message.startswith("There's no bot @closer in this organization.")


async def test_a_bot_cant_hand_a_task_to_itself(team: Team) -> None:
    assert await _refused(team, "@chief") == "You can't hand a task to yourself. Do it yourself."


async def test_a_bot_above_in_the_chain_is_refused(team: Team) -> None:
    handed = await _handed(team, "sales")
    await team.set_status(team.parent, "waiting_handoff")
    await team.set_status(handed.child.id, "running")

    message = await _refused(team, "@chief", run=handed.child.id)

    assert message == (
        "@chief is already part of this chain (it handed work down to you). "
        "Do it yourself or answer with what you have."
    )


async def test_the_hop_limit_is_shared_with_mentions(team: Team) -> None:
    await team.set_status(team.parent, "running", hop=2)
    handed = await _handed(team, "sales")  # a child at hop 3 is allowed
    await team.set_status(team.parent, "waiting_handoff")
    await team.set_status(handed.child.id, "running")

    message = await _refused(team, "@research", run=handed.child.id)

    assert message == (
        "Can't hand off: this run is already 3 hops from a person, and the limit is 3. "
        "Do it yourself or answer with what you have."
    )


async def test_a_run_hands_off_at_most_five_tasks_over_its_life(team: Team) -> None:
    for number in range(5):
        handed = await _handed(team, "sales", f"Task {number}")
        await team.end(handed.child.id, "succeeded", reply="Done.")

    message = await _refused(team, "@research")

    assert (
        message == "You've already handed off 5 tasks in this reply, the most allowed. Work with the results you have."
    )


async def test_an_organization_has_at_most_twenty_open_tasks(team: Team) -> None:
    settings = team.settings.model_copy(update={"handoff_max_open_tasks_per_org": 2})
    await _handed(team, "sales", settings=settings)
    await _handed(team, "research", settings=settings)

    message = await _refused(team, "@sales", settings=settings)

    assert message == (
        "Too many handed-off tasks are open in this organization right now. Do it yourself, or try again later."
    )
    assert TEST_SETTINGS.handoff_max_open_tasks_per_org == 20


async def test_a_refusal_saves_no_task_no_card_and_no_event(team: Team) -> None:
    message_id = uuid.uuid4()
    await _refused(team, "@nobody", message=message_id)

    assert await team.count(Task) == 0
    async with team.db() as db:
        assert await db.get(Message, message_id) is None
    assert await team.events("task_updated") == []


# The state machine


async def test_the_childs_first_claim_makes_the_task_working(team: Team) -> None:
    handed = await _handed(team, "sales")

    async with team.db() as db:
        await task_service.child_started(db, handed.child.id)
        await task_service.child_started(db, team.parent)  # not a child: nothing
        await db.commit()

    task = await team.task(handed.task.id)
    assert task.status == "working" and task.started_at is not None
    card = next(p for p in (await team.message(task.message_id)).parts if p["type"] == "handoff")  # type: ignore[arg-type]
    assert card["status"] == "working"
    assert [e["task"]["status"] for e in await team.events("task_updated")] == ["queued", "working"]


async def test_a_child_that_succeeds_makes_its_task_done_with_its_reply(team: Team) -> None:
    handed = await _handed(team, "sales")
    long_reply = "Here  are\nthe openers. " + "x" * 9000

    await team.end(handed.child.id, "succeeded", reply=long_reply)

    task = await team.task(handed.task.id)
    child = await team.run(handed.child.id)
    assert task.status == "done" and task.finished_at is not None
    assert task.result == long_reply[:8000]
    assert task.result_message_id == child.reply_message_id
    card = next(p for p in (await team.message(task.message_id)).parts if p["type"] == "handoff")  # type: ignore[arg-type]
    assert card["status"] == "done"
    assert card["resultMessageId"] == str(child.reply_message_id)
    assert card["resultPreview"] == ("Here are the openers. " + "x" * 9000)[:280]
    last = (await team.events("task_updated"))[-1]["task"]
    assert last["status"] == "done" and last["resultPreview"] == card["resultPreview"]


async def test_a_child_out_of_budget_fails_its_task_with_the_budget_code(team: Team) -> None:
    handed = await _handed(team, "sales")

    await team.end(handed.child.id, "failed", error="Sales has reached its monthly budget.", code="budget")

    task = await team.task(handed.task.id)
    assert (task.status, task.error, task.error_code) == ("failed", "Sales has reached its monthly budget.", "budget")


async def test_a_child_that_fails_otherwise_fails_its_task_without_a_code(team: Team) -> None:
    handed = await _handed(team, "sales")

    await team.end(handed.child.id, "failed", error="The model couldn't reply.")

    task = await team.task(handed.task.id)
    assert (task.status, task.error, task.error_code) == ("failed", "The model couldn't reply.", None)


async def test_a_stopped_child_fails_its_task_as_stopped(team: Team) -> None:
    handed = await _handed(team, "sales")

    await team.end(handed.child.id, "cancelled")

    task = await team.task(handed.task.id)
    assert (task.status, task.error, task.error_code) == ("failed", "Stopped before it finished.", "stopped")


async def test_ending_a_task_twice_changes_nothing(team: Team) -> None:
    handed = await _handed(team, "sales")
    await team.end(handed.child.id, "failed", error="First")
    events = len(await team.events("task_updated"))

    again = await team.end(handed.child.id, "succeeded", reply="Late")

    task = await team.task(handed.task.id)
    assert (task.status, task.error) == ("failed", "First")
    assert len(await team.events("task_updated")) == events
    assert again == Aftermath()


async def test_a_parent_that_ends_first_cancels_its_open_tasks_and_stops_their_children(team: Team) -> None:
    message_id = uuid.uuid4()
    done = await _handed(team, "sales", message=message_id)
    await team.end(done.child.id, "succeeded", reply="Done.")
    open_one = await _handed(team, "research", message=message_id)

    aftermath = await team.end(team.parent, "cancelled")

    assert aftermath.stop == [open_one.child.id] and aftermath.resume == []
    task = await team.task(open_one.task.id)
    assert (task.status, task.error) == ("cancelled", "Cancelled: Chief stopped before it finished.")
    assert (await team.task(done.task.id)).status == "done"
    statuses = [p["status"] for p in (await team.message(message_id)).parts if p["type"] == "handoff"]
    assert statuses == ["done", "cancelled"]


async def test_taint_comes_back_up_from_a_tainted_child(team: Team) -> None:
    handed = await _handed(team, "sales")
    await team.set_status(team.parent, "waiting_handoff")
    await team.set_status(handed.child.id, "running", tainted=True)

    await team.end(handed.child.id, "succeeded", reply="The email says hi.")

    assert (await team.run(team.parent)).tainted is True


# The parent resumes once


async def test_the_parent_resumes_only_when_its_last_open_task_ends(team: Team) -> None:
    sales = await _handed(team, "sales")
    research = await _handed(team, "research")
    await team.set_status(team.parent, "waiting_handoff")

    first = await team.end(sales.child.id, "succeeded", reply="Openers.")
    last = await team.end(research.child.id, "failed", error="No data.")

    assert first.resume == []
    assert [run.id for run in last.resume] == [team.parent]


async def test_a_parent_still_running_is_not_resumed_by_its_tasks(team: Team) -> None:
    sales = await _handed(team, "sales")

    aftermath = await team.end(sales.child.id, "succeeded", reply="Openers.")

    assert aftermath.resume == []  # it pauses later, and resume_if_ready resumes it then


async def test_resume_if_ready_resumes_a_parent_whose_tasks_already_ended(team: Team) -> None:
    sales = await _handed(team, "sales")
    async with team.db() as db:
        assert await task_service.resume_if_ready(db, team.parent) is None  # still running

    await team.set_status(team.parent, "waiting_handoff")
    async with team.db() as db:
        assert await task_service.resume_if_ready(db, team.parent) is None  # Sales is still open
    await team.end(sales.child.id, "succeeded", reply="Openers.")
    async with team.db() as db:
        resumed = await task_service.resume_if_ready(db, team.parent)
    assert resumed is not None and resumed.id == team.parent


async def test_resume_answer_waits_for_every_task_then_lists_them_in_order(team: Team) -> None:
    sales = await _handed(team, "sales", "Draft openers")
    research = await _handed(team, "research", "Pull numbers")
    await team.end(sales.child.id, "succeeded", reply="Openers.")

    async with team.db() as db:
        assert await task_service.resume_answer(db, team.parent) is None

    await team.set_status(team.parent, "waiting_handoff")
    await team.set_status(research.child.id, "running", tainted=True)
    await team.end(research.child.id, "failed", error="Research has reached its monthly budget.", code="budget")
    async with team.db() as db:
        answer = await task_service.resume_answer(db, team.parent, [str(sales.task.id), str(research.task.id)])

    assert answer == {
        "tasks": [
            {
                "taskId": str(sales.task.id),
                "task": "Draft openers",
                "botName": "Sales",
                "botHandle": "sales",
                "status": "done",
                "result": "Openers.",
                "error": None,
            },
            {
                "taskId": str(research.task.id),
                "task": "Pull numbers",
                "botName": "Research",
                "botHandle": "research",
                "status": "failed",
                "result": None,
                "error": "Research has reached its monthly budget.",
            },
        ],
        "tainted": True,
    }


async def test_resume_answer_covers_only_the_tasks_named(team: Team) -> None:
    earlier = await _handed(team, "sales", "Earlier")
    await team.end(earlier.child.id, "succeeded", reply="Old.")
    later = await _handed(team, "research", "Later")
    await team.end(later.child.id, "succeeded", reply="New.")

    async with team.db() as db:
        answer = await task_service.resume_answer(db, team.parent, [str(later.task.id)])

    assert answer is not None and [task["task"] for task in answer["tasks"]] == ["Later"]


# Timeouts and recovery


async def test_an_overdue_task_times_out_resumes_its_parent_and_stops_its_child(team: Team) -> None:
    handed = await _handed(team, "sales")
    await team.set_status(team.parent, "waiting_handoff")
    later = utcnow() + timedelta(minutes=61)

    async with team.db() as db:
        assert await task_service.overdue(db) == []
        assert await task_service.overdue(db, now=later) == [handed.task.id]
        aftermath = await task_service.expire_overdue(db, handed.task.id, now=later)
        await db.commit()

    assert [run.id for run in aftermath.resume] == [team.parent]
    assert aftermath.stop == [handed.child.id]
    task = await team.task(handed.task.id)
    assert (task.status, task.error, task.error_code) == ("failed", "Timed out after 60 minutes.", "timeout")
    # The child's own end, later, changes nothing.
    assert await team.end(handed.child.id, "cancelled") == Aftermath()
    assert (await team.task(handed.task.id)).error_code == "timeout"


async def test_a_task_not_yet_overdue_is_left_alone(team: Team) -> None:
    handed = await _handed(team, "sales")

    async with team.db() as db:
        assert await task_service.expire_overdue(db, handed.task.id) == Aftermath()

    assert (await team.task(handed.task.id)).status == "queued"


async def test_reconcile_ends_a_task_whose_child_already_finished_and_resumes_the_parent(team: Team) -> None:
    handed = await _handed(team, "sales")
    await team.set_status(team.parent, "waiting_handoff")
    await team.set_status(handed.child.id, "failed", error="Interrupted by a restart. Send your message again.")

    async with team.db() as db:
        aftermath = await task_service.reconcile(db)
        await db.commit()

    assert [run.id for run in aftermath.resume] == [team.parent]
    task = await team.task(handed.task.id)
    assert (task.status, task.error) == ("failed", "Interrupted by a restart. Send your message again.")


async def test_reconcile_cancels_the_open_tasks_of_a_parent_that_already_ended(team: Team) -> None:
    handed = await _handed(team, "sales")
    await team.set_status(team.parent, "failed")

    async with team.db() as db:
        aftermath = await task_service.reconcile(db)
        await db.commit()

    assert aftermath.stop == [handed.child.id]
    assert (await team.task(handed.task.id)).status == "cancelled"

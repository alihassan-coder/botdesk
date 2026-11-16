"""Handoffs on real Postgres (ADR 0014): the cases that need its row locks, its job queue and its
checkpoints. Skipped without TEST_DATABASE_URL (the SQLite cases are in `test_handoffs.py` and
`test_task_service.py`)."""

import asyncio
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models import Message, Run, RunEvent, Task
from src.plugins.team import HandoffArgs
from src.services import run_service, task_service
from tests.conftest import Postgres, sign_up
from tests.test_handoffs import TWO_TASKS, TeamModel
from tests.test_runs_postgres import use_model

ORGS = "/api/v1/orgs"


async def _org(pg: Postgres) -> tuple[str, dict[str, uuid.UUID], str]:
    me = await sign_up(pg.client)
    path = f"{ORGS}/{me['organizations'][0]['id']}"
    bots = {}
    for name in ("Chief", "Sales", "Research"):
        bot = (await pg.client.post(f"{path}/bots", json={"name": name, "securityLevel": "autonomous"})).json()
        bots[bot["handle"]] = uuid.UUID(bot["id"])
    thread = (await pg.client.post(f"{path}/threads/dm", json={"botId": str(bots["chief"])})).json()
    return path, bots, f"{path}/threads/{thread['id']}"


def _sessions(pg: Postgres) -> async_sessionmaker[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = pg.runs.sessionmaker
    return sessionmaker


async def test_a_chief_and_two_children_finish_through_the_job_queue_without_holding_the_chat(pg: Postgres) -> None:
    """The chat's job lock is free while the parent waits: the children (same lock) run, and the
    whole thing finishes under wait_until_idle, in order."""
    model = TeamModel(plans={"Chief": TWO_TASKS}, replies={"Chief": "Here is the plan."})
    use_model(pg, model)
    _path, _bots, thread = await _org(pg)

    sent = await pg.client.post(f"{thread}/messages", json={"text": "Plan tonight's outreach"})
    parent = uuid.UUID(sent.json()["runIds"][0])
    await pg.runs.wait_until_idle()

    async with _sessions(pg)() as db:
        run = await db.get(Run, parent)
        tasks = list(await db.scalars(select(Task).where(Task.parent_run_id == parent).order_by(Task.created_at)))
        paused_at = await db.scalar(
            select(RunEvent.created_at).where(RunEvent.run_id == parent, RunEvent.kind == "run_waiting_handoff")
        )
        children = [await db.get(Run, task.child_run_id) for task in tasks]
        resumed = list(
            await db.scalars(select(RunEvent).where(RunEvent.run_id == parent, RunEvent.kind == "run_resumed"))
        )
    assert run is not None and run.status == "succeeded"
    assert [task.status for task in tasks] == ["done", "done"]
    assert paused_at is not None
    assert all(
        child is not None and child.started_at is not None and child.started_at >= paused_at for child in children
    )
    assert len(resumed) == 1
    messages = (await pg.client.get(f"{thread}/messages")).json()
    assert len(messages) == 5  # Ali, the handoff message, two replies, Chief's answer


async def _parent_with_two_working_tasks(pg: Postgres) -> tuple[uuid.UUID, list[Task]]:
    """A waiting parent with two tasks whose children are running (made by hand: no model)."""
    pg.runs.enabled = False
    _path, _bots, thread = await _org(pg)
    sent = await pg.client.post(f"{thread}/messages", json={"text": "Go"})
    parent = uuid.UUID(sent.json()["runIds"][0])
    settings = pg.runs.settings
    async with _sessions(pg)() as db:
        await db.execute(update(Run).where(Run.id == parent).values(status="running"))
        message_id = uuid.uuid4()
        for handle in ("sales", "research"):
            await task_service.hand_off(
                db,
                parent_run_id=parent,
                tool_call_id=f"call_{handle}",
                args=HandoffArgs(bot=handle, task=f"Task for {handle}"),
                message_id=message_id,
                reply_text="",
                exclude_execution_ids=[],
                level="autonomous",
                tainted=False,
                settings=settings,
            )
        await db.execute(update(Run).where(Run.id == parent).values(status="waiting_handoff"))
        await db.commit()
    async with _sessions(pg)() as db:
        tasks = list(await db.scalars(select(Task).where(Task.parent_run_id == parent).order_by(Task.created_at)))
        await db.execute(update(Task).where(Task.parent_run_id == parent).values(status="working"))
        await db.commit()
    return parent, tasks


def _child(task: Task) -> uuid.UUID:
    assert task.child_run_id is not None
    return task.child_run_id


async def test_two_tasks_ending_at_once_resume_the_parent_exactly_once(pg: Postgres) -> None:
    _parent, tasks = await _parent_with_two_working_tasks(pg)

    async def end(task: Task) -> list[uuid.UUID]:
        async with _sessions(pg)() as db:
            await db.execute(update(Run).where(Run.id == task.child_run_id).values(status="succeeded"))
            aftermath = await task_service.run_ended(db, _child(task), status="succeeded", error=None, code=None)
            await db.commit()
            return [run.id for run in aftermath.resume]

    resumed = await asyncio.gather(*(end(task) for task in tasks))

    assert sorted(len(ids) for ids in resumed) == [0, 1]
    async with _sessions(pg)() as db:
        parts = await db.scalar(select(Message.parts).where(Message.id == tasks[0].message_id))
    assert parts is not None
    assert [p["status"] for p in parts if p["type"] == "handoff"] == ["done", "done"]  # no lost JSON update


async def test_a_pause_racing_the_last_task_resumes_exactly_once(pg: Postgres) -> None:
    parent, tasks = await _parent_with_two_working_tasks(pg)
    async with _sessions(pg)() as db:
        await db.execute(update(Run).where(Run.id == parent).values(status="running"))
        await db.commit()
    first, last = tasks
    async with _sessions(pg)() as db:
        await db.execute(update(Run).where(Run.id == first.child_run_id).values(status="succeeded"))
        await task_service.run_ended(db, _child(first), status="succeeded", error=None, code=None)
        await db.commit()

    async def pause() -> int:
        async with _sessions(pg)() as db:
            await run_service.pause_run(db, parent, status="waiting_handoff")
            ready = await task_service.resume_if_ready(db, parent)
            await db.commit()
            return 1 if ready is not None else 0

    async def end_last() -> int:
        async with _sessions(pg)() as db:
            await db.execute(update(Run).where(Run.id == last.child_run_id).values(status="succeeded"))
            aftermath = await task_service.run_ended(db, _child(last), status="succeeded", error=None, code=None)
            await db.commit()
            return len(aftermath.resume)

    counts = await asyncio.gather(pause(), end_last())

    assert sum(counts) == 1


async def test_a_restart_while_the_parent_waits_still_resumes_it_from_its_checkpoint(pg: Postgres) -> None:
    """The parent is rows and a checkpoint, with no job. Lose every job (as if the worker died),
    then recover: the children run, and the last one resumes the parent from Postgres."""
    model = TeamModel(plans={"Chief": TWO_TASKS}, replies={"Chief": "Here is the plan."})
    use_model(pg, model)
    _path, _bots, thread = await _org(pg)
    start = pg.runs.start
    held: list[Run] = []

    async def hold_children(db: AsyncSession, runs: list[Run]) -> None:
        held.extend(run for run in runs if run.hop > 0)
        await start(db, [run for run in runs if run.hop == 0])

    pg.runs.start = hold_children  # type: ignore[method-assign]
    sent = await pg.client.post(f"{thread}/messages", json={"text": "Go"})
    parent = uuid.UUID(sent.json()["runIds"][0])
    await pg.runs.wait_until_idle()
    assert (await pg.client.get(f"{thread.split('/threads/')[0]}/runs/{parent}")).json()["status"] == "waiting_handoff"
    pg.runs.start = start  # type: ignore[method-assign]

    await pg.runs.recover_after_restart()  # the children have no job: picked up again
    await pg.runs.wait_until_idle()

    async with _sessions(pg)() as db:
        run = await db.get(Run, parent)
    assert run is not None and run.status == "succeeded"
    assert "<task-results>" in model.prompts["Chief"][-1][-1].text

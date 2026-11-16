"""Handoffs on real Postgres (ADR 0014): the cases that need its row locks, its job queue and its
checkpoints. Skipped without TEST_DATABASE_URL (the SQLite cases are in `test_handoffs.py` and
`test_task_service.py`)."""

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import utcnow
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


async def _waiting_parents(pg: Postgres, count: int) -> list[tuple[uuid.UUID, list[Task]]]:
    """`count` waiting parents, each Chief's run in a group of its own, with a working task for
    Sales and one for Research (made by hand: no model, runs never start)."""
    pg.runs.enabled = False
    path, bots, _thread = await _org(pg)
    parents = []
    for number in range(count):
        parent = await _chief_run_in_a_group(pg, path, bots, number)
        async with _sessions(pg)() as db:
            await db.execute(update(Run).where(Run.id == parent).values(status="running"))
            message_id = uuid.uuid4()
            for handle in ("sales", "research"):
                handed = await task_service.hand_off(
                    db,
                    parent_run_id=parent,
                    tool_call_id=f"call_{handle}",
                    args=HandoffArgs(bot=handle, task=f"Task for {handle}"),
                    message_id=message_id,
                    reply_text="",
                    exclude_execution_ids=[],
                    level="autonomous",
                    tainted=False,
                    settings=pg.runs.settings,
                )
                assert isinstance(handed, task_service.HandedOff), handed
            await db.execute(update(Run).where(Run.id == parent).values(status="waiting_handoff"))
            await db.execute(update(Task).where(Task.parent_run_id == parent).values(status="working"))
            await db.commit()
        async with _sessions(pg)() as db:
            tasks = list(await db.scalars(select(Task).where(Task.parent_run_id == parent).order_by(Task.created_at)))
        parents.append((parent, tasks))
    return parents


async def _chief_run_in_a_group(pg: Postgres, path: str, bots: dict[str, uuid.UUID], number: int) -> uuid.UUID:
    body = {"title": f"Chat {number}", "botIds": [str(b) for b in bots.values()], "leadBotId": str(bots["chief"])}
    group = (await pg.client.post(f"{path}/threads/groups", json=body)).json()
    sent = await pg.client.post(f"{path}/threads/{group['id']}/messages", json={"text": "Go"})
    return uuid.UUID(sent.json()["runIds"][0])


async def _reconcile_pass(pg: Postgres) -> list[uuid.UUID]:
    """One recovery pass as `RunManager.reconcile_tasks` makes it, without swallowing errors."""
    async with _sessions(pg)() as db:
        parent_ids = await task_service.to_reconcile(db)
    resumed: list[uuid.UUID] = []
    for parent_id in parent_ids:
        async with _sessions(pg)() as db:
            aftermath = await task_service.reconcile(db, parent_id)
            await db.commit()
        resumed += [run.id for run in aftermath.resume]
    return resumed


async def _task_statuses(pg: Postgres, parent: uuid.UUID) -> list[str]:
    async with _sessions(pg)() as db:
        rows = await db.scalars(select(Task.status).where(Task.parent_run_id == parent).order_by(Task.created_at))
        return list(rows)


async def test_two_reconcile_passes_at_once_never_deadlock_and_end_every_task(pg: Postgres) -> None:
    parents = await _waiting_parents(pg, 3)
    async with _sessions(pg)() as db:  # every child finished, but nothing ended their tasks
        for _parent, tasks in parents:
            for task in tasks:
                await db.execute(update(Run).where(Run.id == task.child_run_id).values(status="succeeded"))
        await db.commit()

    first, second = await asyncio.wait_for(asyncio.gather(_reconcile_pass(pg), _reconcile_pass(pg)), timeout=30)

    assert set(first) | set(second) == {parent for parent, _ in parents}
    for parent, tasks in parents:
        assert await _task_statuses(pg, parent) == ["done", "done"]
        async with _sessions(pg)() as db:
            parts = await db.scalar(select(Message.parts).where(Message.id == tasks[0].message_id))
        assert parts is not None and [p["status"] for p in parts if p["type"] == "handoff"] == ["done", "done"]


async def test_reconcile_alongside_expire_tasks_ends_each_task_once(pg: Postgres) -> None:
    ((parent, (finished, overdue)),) = await _waiting_parents(pg, 1)
    async with _sessions(pg)() as db:
        await db.execute(update(Run).where(Run.id == finished.child_run_id).values(status="succeeded"))
        await db.execute(update(Task).where(Task.id == overdue.id).values(deadline_at=utcnow() - timedelta(minutes=1)))
        await db.commit()

    async def expire_pass() -> list[uuid.UUID]:
        async with _sessions(pg)() as db:
            due = await task_service.overdue(db)
        resumed: list[uuid.UUID] = []
        for task_id in due:
            async with _sessions(pg)() as db:
                aftermath = await task_service.expire_overdue(db, task_id)
                await db.commit()
            resumed += [run.id for run in aftermath.resume]
        return resumed

    reconciled, expired = await asyncio.wait_for(asyncio.gather(_reconcile_pass(pg), expire_pass()), timeout=30)

    assert parent in [*reconciled, *expired]
    assert await _task_statuses(pg, parent) == ["done", "failed"]
    async with _sessions(pg)() as db:
        timed_out = await db.get(Task, overdue.id)
        updates = list(await db.scalars(select(RunEvent).where(RunEvent.kind == "task_updated")))
    assert timed_out is not None and timed_out.error_code == "timeout"
    finals = [e.payload["task"]["id"] for e in updates if e.payload["task"]["status"] in ("done", "failed")]
    assert sorted(finals) == sorted([str(finished.id), str(overdue.id)])  # each ended exactly once


async def test_handoffs_from_two_chats_at_once_never_pass_the_organizations_cap(pg: Postgres) -> None:
    pg.runs.enabled = False
    path, bots, _thread = await _org(pg)
    parents = [await _chief_run_in_a_group(pg, path, bots, number) for number in range(2)]
    async with _sessions(pg)() as db:
        await db.execute(update(Run).where(Run.id.in_(parents)).values(status="running"))
        await db.commit()
    settings = pg.runs.settings.model_copy(update={"handoff_max_open_tasks_per_org": 1})

    async def hand_off(parent: uuid.UUID) -> task_service.HandoffResult:
        async with _sessions(pg)() as db:
            result = await task_service.hand_off(
                db,
                parent_run_id=parent,
                tool_call_id="call_1",
                args=HandoffArgs(bot="sales", task="Draft openers"),
                message_id=uuid.uuid4(),
                reply_text="",
                exclude_execution_ids=[],
                level="autonomous",
                tainted=False,
                settings=settings,
            )
            await asyncio.sleep(0.2)  # hold the transaction open while the other handoff counts
            await db.commit()
            return result

    results = await asyncio.gather(*(hand_off(parent) for parent in parents))

    assert sorted(type(result).__name__ for result in results) == ["HandedOff", "Refused"]
    async with _sessions(pg)() as db:
        assert len(list(await db.scalars(select(Task)))) == 1


async def test_a_resume_job_deferred_twice_resumes_the_parent_once(pg: Postgres) -> None:
    model = TeamModel(plans={"Chief": TWO_TASKS}, replies={"Chief": "Here is the plan."})
    use_model(pg, model)
    _path, _bots, thread = await _org(pg)
    resume = pg.runs.resume
    held: list[uuid.UUID] = []

    async def hold(_db: AsyncSession, run: Run) -> None:
        held.append(run.id)

    pg.runs.resume = hold  # type: ignore[method-assign,assignment]
    sent = await pg.client.post(f"{thread}/messages", json={"text": "Plan tonight's outreach"})
    parent = uuid.UUID(sent.json()["runIds"][0])
    await pg.runs.wait_until_idle()
    pg.runs.resume = resume  # type: ignore[method-assign]
    assert held == [parent]

    await asyncio.gather(pg.runs.take_turn(parent), pg.runs.take_turn(parent))
    await pg.runs.wait_until_idle()

    async with _sessions(pg)() as db:
        run = await db.get(Run, parent)
        resumed = list(
            await db.scalars(select(RunEvent).where(RunEvent.run_id == parent, RunEvent.kind == "run_resumed"))
        )
    assert run is not None and run.status == "succeeded"
    assert len(resumed) == 1
    assert len((await pg.client.get(f"{thread}/messages")).json()) == 5  # one final answer


async def test_stop_racing_the_last_task_ending_leaves_one_consistent_outcome(pg: Postgres) -> None:
    ((parent, (first, last)),) = await _waiting_parents(pg, 1)
    async with _sessions(pg)() as db:
        await db.execute(update(Run).where(Run.id == first.child_run_id).values(status="succeeded"))
        await task_service.run_ended(db, _child(first), status="succeeded", error=None, code=None)
        await db.commit()

    async def end_last() -> list[uuid.UUID]:
        async with _sessions(pg)() as db:
            await db.execute(update(Run).where(Run.id == last.child_run_id).values(status="succeeded"))
            aftermath = await task_service.run_ended(db, _child(last), status="succeeded", error=None, code=None)
            await db.commit()
            return [run.id for run in aftermath.resume]

    _stopped, resumed = await asyncio.gather(pg.runs.stop(parent), end_last())

    async with _sessions(pg)() as db:
        run = await db.get(Run, parent)
        task = await db.get(Task, last.id)
        parts = await db.scalar(select(Message.parts).where(Message.id == last.message_id))
    assert run is not None and run.status == "cancelled"  # Stop wins either way
    assert task is not None and task.status in ("done", "cancelled")
    # Resumed at most once, and only when the task ended first (that job then finds it cancelled).
    assert resumed in ([], [parent])
    if task.status == "cancelled":
        assert resumed == []
    assert parts is not None
    assert [p["status"] for p in parts if p["type"] == "handoff"] == ["done", task.status]

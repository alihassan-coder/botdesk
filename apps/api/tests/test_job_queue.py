"""The job queue's promises (src/jobs/queue.py), on the in-process adapter. The procrastinate
adapter keeps the same ones on Postgres: tests/test_job_queue_postgres.py."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast

import pytest
from sqlalchemy import text

from src.core.database import create_engine, create_sessionmaker, utcnow
from src.jobs.local import LocalQueue
from src.jobs.queue import Job, JobEnv, JobRegistry

ENV = cast(JobEnv, None)  # these tasks don't use it


class Recorder:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.running = 0
        self.most_at_once = 0
        self.release = asyncio.Event()

    def registry(self) -> JobRegistry:
        jobs = JobRegistry()

        @jobs.task("work")
        async def work(env: JobEnv, name: str, wait: bool = False) -> None:
            self.running += 1
            self.most_at_once = max(self.most_at_once, self.running)
            self.log.append(f"start {name}")
            try:
                if wait:
                    await self.release.wait()
                await asyncio.sleep(0.01)
            finally:
                self.running -= 1
                self.log.append(f"end {name}")

        return jobs


@pytest.fixture
async def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
async def queue(recorder: Recorder) -> AsyncIterator[LocalQueue]:
    queue = LocalQueue(recorder.registry())
    await queue.start(ENV)
    yield queue
    await queue.close()


async def test_jobs_with_the_same_lock_run_one_at_a_time_in_order(queue: LocalQueue, recorder: Recorder) -> None:
    for name in ("a", "b", "c"):
        await queue.defer(Job("work", {"name": name}, lock="chat:1"))
    await queue.wait_until_idle()

    assert recorder.log == ["start a", "end a", "start b", "end b", "start c", "end c"]


async def test_jobs_with_different_locks_run_side_by_side(queue: LocalQueue, recorder: Recorder) -> None:
    await queue.defer(Job("work", {"name": "a", "wait": True}, lock="chat:1"))
    await queue.defer(Job("work", {"name": "b", "wait": True}, lock="chat:2"))
    await asyncio.sleep(0.05)
    recorder.release.set()
    await queue.wait_until_idle()

    assert recorder.most_at_once == 2


async def test_a_job_deferred_in_a_transaction_runs_only_if_it_commits(queue: LocalQueue, recorder: Recorder) -> None:
    engine = create_engine("sqlite+aiosqlite://")
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as db:
        await db.execute(text("SELECT 1"))
        await queue.defer(Job("work", {"name": "kept"}), db=db)
        await asyncio.sleep(0.05)
        assert recorder.log == []  # not before the commit
        await db.commit()
    async with sessionmaker() as db:
        await db.execute(text("SELECT 1"))
        await queue.defer(Job("work", {"name": "dropped"}), db=db)
        await db.rollback()
    await queue.wait_until_idle()
    await engine.dispose()

    assert recorder.log == ["start kept", "end kept"]


async def test_only_one_job_waits_per_queueing_lock(queue: LocalQueue, recorder: Recorder) -> None:
    await queue.defer(Job("work", {"name": "first", "wait": True}, lock="chat:1"))
    await queue.defer(Job("work", {"name": "second"}, lock="chat:1", queueing_lock="run:2"))
    await queue.defer(Job("work", {"name": "again"}, lock="chat:1", queueing_lock="run:2"))  # ignored
    recorder.release.set()
    await queue.wait_until_idle()

    assert recorder.log == ["start first", "end first", "start second", "end second"]


async def test_abort_stops_the_running_job_with_that_key(queue: LocalQueue, recorder: Recorder) -> None:
    await queue.defer(Job("work", {"name": "long", "wait": True}, queueing_lock="run:1"))
    await asyncio.sleep(0.05)

    await queue.abort("run:1")
    await queue.wait_until_idle()

    assert recorder.log == ["start long", "end long"]
    assert not recorder.release.is_set()


async def test_a_job_waits_for_its_time(queue: LocalQueue, recorder: Recorder) -> None:
    await queue.defer(Job("work", {"name": "later"}, run_at=utcnow() + timedelta(seconds=0.2)))
    await asyncio.sleep(0.1)
    assert recorder.log == []

    await queue.wait_until_idle()
    assert recorder.log == ["start later", "end later"]


async def test_recover_defers_only_jobs_that_are_not_already_waiting_or_running(
    queue: LocalQueue, recorder: Recorder
) -> None:
    await queue.defer(Job("work", {"name": "live", "wait": True}, queueing_lock="run:1"))
    await asyncio.sleep(0.05)

    await queue.recover(
        [
            Job("work", {"name": "duplicate"}, queueing_lock="run:1"),
            Job("work", {"name": "lost"}, queueing_lock="run:2"),
        ]
    )
    recorder.release.set()
    await queue.wait_until_idle()

    assert sorted(recorder.log) == ["end live", "end lost", "start live", "start lost"]


async def test_jobs_wait_until_the_worker_starts(recorder: Recorder) -> None:
    queue = LocalQueue(recorder.registry())
    await queue.defer(Job("work", {"name": "early"}))
    await asyncio.sleep(0.05)
    assert recorder.log == []

    await queue.start(ENV)
    await queue.wait_until_idle()
    await queue.close()
    assert recorder.log == ["start early", "end early"]


def test_two_tasks_cannot_share_a_name() -> None:
    jobs = JobRegistry()

    @jobs.task("same")
    async def one(env: JobEnv) -> None: ...

    with pytest.raises(ValueError, match="Two jobs are named 'same'"):
        jobs.task("same")(one)

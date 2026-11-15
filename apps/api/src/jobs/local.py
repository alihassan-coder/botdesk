"""The in-process job queue: jobs are asyncio tasks in this process (see `jobs.queue` for the promises).

Used on SQLite (local development without Postgres) and by unit tests. Nothing is saved: jobs
waiting or running when the process stops are gone, which is why a restart on SQLite fails the
runs it interrupted (`RunManager.recover_after_restart`).
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any

from croniter import croniter
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from src.core.database import utcnow
from src.jobs.queue import Job, JobEnv, JobRegistry, TaskDef

logger = logging.getLogger(__name__)

_IN_TRANSACTION = "botdesk.local_jobs"  # session.info key: (queue, job) pairs waiting for the commit


class LocalQueue:
    def __init__(self, registry: JobRegistry) -> None:
        self.registry = registry
        self._env: JobEnv | None = None
        self._started = False
        self._ready: deque[Job] = deque()  # deferred before the worker started
        self._lines: dict[str, deque[Job]] = {}  # lock → jobs waiting their turn, in order
        self._waiting: set[str] = set()  # queueing locks of jobs not started yet
        self._running: dict[str, asyncio.Task[None]] = {}  # queueing lock → the job running now
        self._tasks: set[asyncio.Task[None]] = set()  # every job and line (asyncio keeps weak references)
        self._periodic: set[asyncio.Task[None]] = set()

    # The interface

    async def defer(self, job: Job, *, db: AsyncSession | None = None) -> None:
        if db is None:
            self._add(job)
            return
        await db.connection()  # make sure there is a transaction to wait for
        db.sync_session.info.setdefault(_IN_TRANSACTION, []).append((self, job))

    async def abort(self, queueing_lock: str) -> None:
        if task := self._running.get(queueing_lock):
            task.cancel()

    async def recover(self, jobs: list[Job]) -> None:
        for job in jobs:
            if job.queueing_lock not in self._running:
                self._add(job)

    async def wait_until_idle(self) -> None:
        while self._tasks or (self._ready and self._started):
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # The worker

    async def start(self, env: JobEnv, *, periodic: bool = False) -> None:
        """Start running jobs (those deferred so far first). `periodic` also fires the cron tasks."""
        self._env, self._started = env, True
        while self._ready:
            self._schedule(self._ready.popleft())
        if periodic:
            for task in self.registry.periodic:
                self._keep(self._periodic, self._every(task))

    async def close(self) -> None:
        tasks = [*self._tasks, *self._periodic]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._started = False

    # Inside

    def _add(self, job: Job) -> None:
        if job.queueing_lock is not None:
            if job.queueing_lock in self._waiting:
                return  # one waiting job per key
            self._waiting.add(job.queueing_lock)
        if not self._started:
            self._ready.append(job)
        else:
            self._schedule(job)

    def _schedule(self, job: Job) -> None:
        if job.lock is None:
            self._keep(self._tasks, self._run(job))
            return
        line = self._lines.get(job.lock)
        if line is not None:  # its line is already moving: join the end
            line.append(job)
            return
        self._lines[job.lock] = deque([job])
        self._keep(self._tasks, self._run_line(job.lock))

    async def _run_line(self, lock: str) -> None:
        line = self._lines[lock]
        try:
            while line:
                await self._run(line[0])
                line.popleft()
        finally:
            del self._lines[lock]

    async def _run(self, job: Job) -> None:
        if job.run_at is not None:
            await asyncio.sleep(max(0.0, (job.run_at - utcnow()).total_seconds()))
        if job.queueing_lock is not None:
            self._waiting.discard(job.queueing_lock)
        task = asyncio.create_task(self._call(self.registry.tasks[job.task], job.args), name=f"job {job.task}")
        if job.queueing_lock is not None:
            self._running[job.queueing_lock] = task
        try:
            await asyncio.wait({task})  # not `await task`: an aborted or failed job doesn't stop its line
        finally:
            if job.queueing_lock is not None and self._running.get(job.queueing_lock) is task:
                del self._running[job.queueing_lock]
            if not task.done():  # the line itself was cancelled (shutdown)
                task.cancel()

    async def _call(self, task: TaskDef, args: dict[str, Any]) -> None:
        try:
            await task.handler(self._env, **args)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Job %s failed", task.name)

    async def _every(self, task: TaskDef) -> None:
        assert task.cron is not None
        schedule = croniter(task.cron, datetime.now().astimezone())
        while True:
            at: float = schedule.get_next(float)
            await asyncio.sleep(max(0.0, at - time.time()))
            await self._call(task, {"timestamp": int(at)})

    @staticmethod
    def _keep(tasks: set[asyncio.Task[None]], work: Any) -> None:
        task = asyncio.create_task(work)
        tasks.add(task)
        task.add_done_callback(tasks.discard)


@event.listens_for(Session, "after_commit")
def _add_jobs_after_commit(session: Session) -> None:
    for queue, job in session.info.pop(_IN_TRANSACTION, []):
        queue._add(job)


@event.listens_for(Session, "after_transaction_end")
def _drop_jobs_after_rollback(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:  # the outermost transaction ended without a commit
        session.info.pop(_IN_TRANSACTION, None)

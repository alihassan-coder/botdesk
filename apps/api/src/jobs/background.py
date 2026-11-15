"""Puts the run manager, the job queue and the live-events listener together for one process
(ADR 0013). The API calls it with `role="api"`, `python -m src.worker` with `role="worker"`.

| Database | WORKER_MODE | API process | Worker process |
|---|---|---|---|
| SQLite | (any) | in-process queue, jobs run here | not used |
| Postgres | embedded | procrastinate worker here + LISTEN for events | not needed |
| Postgres | separate | adds jobs only + LISTEN for events | procrastinate worker |
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.database import is_in_memory
from src.core.secrets import SecretBox
from src.jobs.local import LocalQueue
from src.jobs.postgres import SHUTDOWN_SECONDS, ProcrastinateQueue
from src.jobs.queue import JobEnv
from src.jobs.tasks import JOBS
from src.runtime.event_bus import listen_to_postgres
from src.runtime.memory import MemoryService
from src.runtime.runner import RunManager, checkpointer_for
from src.services.model_catalog import ModelCatalog

logger = logging.getLogger(__name__)

Role = Literal["api", "worker"]


@asynccontextmanager
async def background(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    memory: MemoryService,
    secrets: SecretBox,
    catalog: ModelCatalog | None = None,
    *,
    role: Role = "api",
    shutdown_seconds: float = SHUTDOWN_SECONDS,
) -> AsyncIterator[JobEnv]:
    """Yields the process's `JobEnv` (its run manager and queue). In the API with an embedded
    worker, and on SQLite, jobs run in the background until the block ends. A worker process
    runs its worker itself: `queue.run_worker(env, …, own_signals=True)`."""
    if not settings.uses_postgres:
        if role == "worker" or settings.worker_mode == "separate":
            raise RuntimeError("WORKER_MODE=separate and `python -m src.worker` need Postgres (DATABASE_URL).")
        async with _in_process(settings, sessionmaker, memory, secrets, catalog) as env:
            yield env
        return

    queue = ProcrastinateQueue(settings, JOBS, shutdown_seconds=shutdown_seconds)
    runs_here = role == "worker" or settings.worker_mode == "embedded"
    await queue.open()
    tasks: list[asyncio.Task[None]] = []
    try:
        # Only a process that executes runs needs their checkpoints.
        async with checkpointer_for(settings) if runs_here else contextlib.nullcontext(InMemorySaver()) as checkpointer:
            runs = RunManager(
                settings=settings,
                sessionmaker=sessionmaker,
                checkpointer=checkpointer,
                memory=memory,
                secrets=secrets,
                queue=queue,
                catalog=catalog,
            )
            env = JobEnv(runs=runs, queue=queue, sessionmaker=sessionmaker, settings=settings)
            try:
                if role == "api":
                    # Streams in this process hear about events other processes save.
                    tasks.append(asyncio.create_task(listen_to_postgres(settings.direct_url, runs.bus)))
                if runs_here:
                    queue.bind(env)
                    await runs.recover_after_restart()
                if role == "api" and runs_here:
                    worker = queue.run_worker(env, concurrency=settings.worker_concurrency)
                    tasks.append(asyncio.create_task(worker, name="job worker"))
                yield env
            finally:
                # Cancelling the worker stops it gracefully: running jobs get a few seconds, then
                # they're aborted and put back in the queue for the next start.
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await runs.close()
    finally:
        await queue.close()


@asynccontextmanager
async def _in_process(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    memory: MemoryService,
    secrets: SecretBox,
    catalog: ModelCatalog | None,
) -> AsyncIterator[JobEnv]:
    """SQLite: jobs are asyncio tasks in this process, and nothing survives a restart."""
    queue = LocalQueue(JOBS)
    async with checkpointer_for(settings) as checkpointer:
        runs = RunManager(
            settings=settings,
            sessionmaker=sessionmaker,
            checkpointer=checkpointer,
            memory=memory,
            secrets=secrets,
            queue=queue,
            catalog=catalog,
        )
        env = JobEnv(runs=runs, queue=queue, sessionmaker=sessionmaker, settings=settings)
        await runs.recover_after_restart()
        # Not on an in-memory database (tests): it has a single connection, which a timer firing
        # mid-test would share with the test's own transaction.
        await queue.start(env, periodic=not is_in_memory(settings.sqlalchemy_url))
        try:
            yield env
        finally:
            await queue.close()
            await runs.close()

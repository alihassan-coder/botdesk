"""The job queue's interface (ADR 0013): what the rest of the app knows about background work.

A **job** is a named task with JSON arguments that a worker runs later. Two adapters sit
behind this interface:

- `jobs.postgres.ProcrastinateQueue`: procrastinate on Postgres. Jobs are rows; a worker (inside
  the API process, or its own process) takes them. Survives restarts.
- `jobs.local.LocalQueue`: asyncio tasks in this process. For SQLite (local development
  without Postgres) and for unit tests. Lost on restart.

Both keep the same promises:

- **Deferring inside a transaction:** `defer(job, db=session)` adds the job to that transaction.
  It runs only if the transaction commits, and never if it rolls back. Without `db`, the job is
  added at once.
- **`lock`:** jobs with the same lock run one at a time, in the order they were deferred. Jobs
  with different locks (or none) run side by side.
- **`queueing_lock`:** at most one job *waiting* with this key; deferring another while one
  waits does nothing. It also names a job for `abort` and `recover`.
- **`run_at`:** not before this moment.
- A job may run more than once (after a crash, or when recovery puts it back), so a handler must
  be safe to run again. Handlers read what to do from the database, not from the job.

Tasks themselves are declared in a `JobRegistry` (see `jobs.tasks` and the backend guide,
"Background jobs").
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings

if TYPE_CHECKING:
    from src.runtime.runner import RunManager

JsonArgs = dict[str, str | int | float | bool | None]


@dataclass(frozen=True)
class Job:
    task: str  # a name registered in the JobRegistry
    args: JsonArgs = field(default_factory=dict)
    lock: str | None = None
    queueing_lock: str | None = None
    run_at: datetime | None = None  # timezone-aware; None = as soon as possible


class JobQueue(Protocol):
    """What services and controllers use. Starting and stopping the worker belongs to the process
    that owns the queue (`jobs/background.py`), not to callers."""

    async def defer(self, job: Job, *, db: AsyncSession | None = None) -> None:
        """Add a job. With `db`, in that session's transaction: it exists only once the caller commits."""
        ...

    async def abort(self, queueing_lock: str) -> None:
        """Stop the job with this key that is running now, wherever it runs (Stop button). Its task
        sees `asyncio.CancelledError`. Does nothing if no such job is running."""
        ...

    async def recover(self, jobs: list[Job]) -> None:
        """After a crash: put back jobs whose worker died, then defer each of `jobs` that has no job
        with its `queueing_lock` waiting or running."""
        ...

    async def wait_until_idle(self) -> None:
        """Wait until no job (other than periodic ones) is waiting or running. For tests."""
        ...


@dataclass(frozen=True)
class JobEnv:
    """What a task gets to work with, in the worker's process."""

    runs: "RunManager"
    queue: JobQueue
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: Settings


Handler = Callable[..., Awaitable[None]]  # async def handler(env: JobEnv, **args) -> None


@dataclass(frozen=True)
class TaskDef:
    name: str
    handler: Handler
    cron: str | None = None  # periodic: a cron line; the handler also gets `timestamp` (Unix seconds)
    # Put the job back when the worker shuts down while it runs (instead of dropping it).
    retry_after_shutdown: bool = False


class JobRegistry:
    """The tasks a worker knows. Declaring one is the hook other slices use:

    @JOBS.task("routines.fire")                      # deferred: queue.defer(Job("routines.fire", {...}))
    async def fire(env: JobEnv, routine_id: str) -> None: ...

    @JOBS.task("gmail.poll", cron="*/2 * * * *")    # periodic: every 2 minutes, on one worker
    async def poll(env: JobEnv, timestamp: int) -> None: ...
    """

    def __init__(self) -> None:
        self.tasks: dict[str, TaskDef] = {}

    def task(
        self, name: str, *, cron: str | None = None, retry_after_shutdown: bool = False
    ) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            if name in self.tasks:
                raise ValueError(f"Two jobs are named {name!r}.")
            self.tasks[name] = TaskDef(name, handler, cron, retry_after_shutdown)
            return handler

        return register

    @property
    def periodic(self) -> list[TaskDef]:
        return [task for task in self.tasks.values() if task.cron]


def run_lock(thread_id: uuid.UUID) -> str:
    """Runs in one chat take turns: their jobs share this lock."""
    return f"chat:{thread_id}"


def run_key(run_id: uuid.UUID) -> str:
    """A run's job key (its `queueing_lock`): one waiting job per run, and what Stop aborts."""
    return f"run:{run_id}"

"""The job queue on Postgres, with procrastinate (ADR 0005, ADR 0013). See `jobs.queue` for the promises.

- **Deferring** inside a transaction uses that transaction's own connection (procrastinate takes
  an external connection), so a run and its job are saved together or not at all.
- **The worker** runs inside the API process (`WORKER_MODE=embedded`) or as `python -m src.worker`
  (`separate`). It finds new jobs through procrastinate's `LISTEN/NOTIFY`, and polls as a fallback.
- **Connections:** the queue's own pool and its `LISTEN` connection use the direct address
  (`DATABASE_URL_DIRECT`): `LISTEN` doesn't work through a transaction pooler. Like every other
  pool here, a connection that sat idle is tested before use (`IdleCheck`), so one Neon closed
  while suspended is replaced, and connections are recycled before Neon's 5 minutes.
- **Restarts:** a job the worker was running when it shut down is put back (`retry_after_shutdown`);
  one whose worker died without saying so (a crash) is put back by `recover`, which the worker
  calls at start and once a minute.
"""

import asyncio
import contextlib
import logging
from typing import Any, LiteralString

import procrastinate
from procrastinate import exceptions as procrastinate_errors
from procrastinate.jobs import Job as ProcrastinateJob
from procrastinate.jobs import Status as ProcrastinateStatus
from procrastinate.retry import BaseRetryStrategy, RetryDecision
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.database import POOL_MAX_LIFETIME_SECONDS, IdleCheck, postgres_connect_args
from src.jobs.queue import Job, JobEnv, JobRegistry, TaskDef

logger = logging.getLogger(__name__)

# A worker that hasn't sent a heartbeat for this long is gone; its running jobs are put back.
# (procrastinate's worker sends one every 10 seconds.)
STALLED_WORKER_SECONDS = 60.0
# The worker looks for jobs this often even without a notification. `LISTEN` normally wakes it
# at once, so this is only the fallback (and every poll is a query, which keeps Neon awake).
POLL_SECONDS = 10.0
# A worker that stops waits this long for running jobs, then aborts them (they're put back).
SHUTDOWN_SECONDS = 5.0
RESTART_DELAY_SECONDS = 5.0  # after the embedded worker fails (say, the database is unreachable)

_LIVE_KEYS: LiteralString = """
    SELECT queueing_lock FROM procrastinate_jobs
     WHERE status IN ('todo', 'doing') AND queueing_lock = ANY(%(keys)s)
"""
_BUSY: LiteralString = """
    SELECT count(*) AS busy FROM procrastinate_jobs
     WHERE status IN ('todo', 'doing') AND NOT task_name = ANY(%(periodic)s)
"""


class _PutBackAfterShutdown(BaseRetryStrategy):
    """A job aborted because its worker is stopping goes back in the queue, to run again at once
    on the next worker. Every other failure is final (handlers deal with their own errors)."""

    def get_retry_decision(self, *, exception: BaseException, job: ProcrastinateJob) -> RetryDecision | None:
        if isinstance(exception, asyncio.CancelledError | procrastinate_errors.JobAborted):
            return RetryDecision(retry_in={"seconds": 0})
        return None


def queue_pool_factory(idle_check: IdleCheck) -> Any:
    """procrastinate builds its own pool and checks *every* connection before use; this one checks
    only connections that sat idle (`IdleCheck`) and recycles them before Neon's 5 minutes."""

    def factory(**kwargs: Any) -> AsyncConnectionPool[Any]:
        return AsyncConnectionPool(
            **{
                **kwargs,
                "check": idle_check.check,
                "configure": idle_check.configure,
                "reset": idle_check.reset,
                "max_lifetime": POOL_MAX_LIFETIME_SECONDS,
                "max_idle": POOL_MAX_LIFETIME_SECONDS,
            }
        )

    return factory


class ProcrastinateQueue:
    def __init__(
        self,
        settings: Settings,
        registry: JobRegistry,
        *,
        shutdown_seconds: float = SHUTDOWN_SECONDS,
        idle_check: IdleCheck | None = None,
    ) -> None:
        url = settings.direct_url
        self.registry = registry
        self.shutdown_seconds = shutdown_seconds
        self.app = procrastinate.App(
            connector=procrastinate.PsycopgConnector(
                conninfo=url,
                min_size=1,
                max_size=4,
                kwargs=postgres_connect_args(url),
                pool_factory=queue_pool_factory(idle_check or IdleCheck()),
            )
        )
        self._bound = False

    async def open(self) -> None:
        await self.app.open_async()

    async def close(self) -> None:
        await self.app.close_async()

    # The interface

    async def defer(self, job: Job, *, db: AsyncSession | None = None) -> None:
        options: dict[str, Any] = {"lock": job.lock, "queueing_lock": job.queueing_lock, "schedule_at": job.run_at}
        if db is None:
            with contextlib.suppress(procrastinate_errors.AlreadyEnqueued):
                await self.app.configure_task(job.task, **options).defer_async(**job.args)
            return
        connection = await (await db.connection()).get_raw_connection()
        options["connection"] = connection.driver_connection
        if job.queueing_lock is None:
            await self.app.configure_task(job.task, **options).defer_async(**job.args)
            return
        # A refused duplicate must not spoil the caller's transaction: try it in a savepoint.
        with contextlib.suppress(procrastinate_errors.AlreadyEnqueued):
            async with db.begin_nested():
                await self.app.configure_task(job.task, **options).defer_async(**job.args)

    async def abort(self, queueing_lock: str) -> None:
        for job in await self.app.job_manager.list_jobs_async(queueing_lock=queueing_lock, status="doing"):
            assert job.id is not None
            await self.app.job_manager.cancel_job_by_id_async(job.id, abort=True)

    async def recover(self, jobs: list[Job]) -> None:
        manager = self.app.job_manager
        for stalled in await manager.get_stalled_jobs(seconds_since_heartbeat=STALLED_WORKER_SECONDS):
            try:
                await manager.retry_job(stalled)
                logger.info("Put back job %s: its worker stopped answering", stalled.call_string)
            except procrastinate_errors.ProcrastinateException:
                # The same key already has a waiting job, which does the work: end this one, or
                # it would hold its lock (and its chat's line) for good.
                logger.info("Job %s already has a replacement; ending it", stalled.call_string)
                await manager.finish_job(stalled, status=ProcrastinateStatus.FAILED, delete_job=False)
        keys = [job.queueing_lock for job in jobs if job.queueing_lock]
        rows = await self.app.connector.execute_query_all_async(_LIVE_KEYS, keys=keys) if keys else []
        live = {row["queueing_lock"] for row in rows}
        for job in jobs:
            if job.queueing_lock not in live:
                logger.info("Deferring %s again: it had no job", job.queueing_lock or job.task)
                await self.defer(job)

    async def wait_until_idle(self) -> None:
        periodic = [task.name for task in self.registry.periodic]
        while (await self.app.connector.execute_query_one_async(_BUSY, periodic=periodic))["busy"]:  # noqa: ASYNC110 (polls another process's state)
            await asyncio.sleep(0.05)

    # The worker

    def bind(self, env: JobEnv) -> None:
        """Register the registry's tasks with procrastinate, each handed `env`. Once per queue."""
        if self._bound:
            return
        for task in self.registry.tasks.values():
            self._register(task, env)
        self._bound = True

    def _register(self, task: TaskDef, env: JobEnv) -> None:
        retry: BaseRetryStrategy | bool = _PutBackAfterShutdown() if task.retry_after_shutdown else False
        if task.cron:

            async def tick(timestamp: int) -> None:
                await task.handler(env, timestamp=timestamp)

            periodic = self.app.task(name=task.name, retry=retry, pass_context=False)(tick)
            self.app.periodic(cron=task.cron)(periodic)
            return

        async def call(**kwargs: Any) -> None:
            await task.handler(env, **kwargs)

        self.app.task(name=task.name, retry=retry, pass_context=False)(call)

    async def run_worker(self, env: JobEnv, *, concurrency: int, own_signals: bool = False) -> None:
        """Run the worker until cancelled (embedded) or until SIGINT/SIGTERM (`own_signals`, the
        separate process). It's started again after a failure, such as a lost database."""
        self.bind(env)
        while True:
            try:
                await self.app.run_worker_async(
                    concurrency=concurrency,
                    wait=True,
                    fetch_job_polling_interval=POLL_SECONDS,
                    abort_job_polling_interval=POLL_SECONDS,
                    shutdown_graceful_timeout=self.shutdown_seconds,
                    install_signal_handlers=own_signals,
                    delete_jobs="successful",
                    stalled_worker_timeout=STALLED_WORKER_SECONDS,
                )
                if own_signals:
                    return  # stopped by a signal
                logger.warning("The job worker stopped; starting it again in %s s", RESTART_DELAY_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("The job worker failed; starting it again in %s s", RESTART_DELAY_SECONDS)
            await asyncio.sleep(RESTART_DELAY_SECONDS)

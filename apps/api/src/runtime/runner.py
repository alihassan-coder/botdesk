"""Moves runs forward, as jobs on the job queue (ADR 0013).

Posting a message saves queued runs and, in the same transaction, a `run_bot` job for each
(`RunManager.start`). A worker takes the job and calls `RunManager.take_turn`, which starts the
run when it's its chat's turn (one run at a time per chat), runs the graph, and ends it as
succeeded, failed or cancelled, or pauses it:

- **waiting_approval:** the graph called `interrupt()`. The job ends; the run is rows in
  Postgres. When a person decides (or the approval expires), `RunManager.resume` defers another
  `run_bot` job, which continues the same checkpoint with `Command(resume=...)`.
- **waiting_handoff:** the run handed tasks to teammate bots (ADR 0014) and paused in
  `wait_for_tasks`. Its job ends, so the chat's lock is free for the children. When the last of
  its tasks ends, `task_service` says so and `resume` defers its job, which continues the
  checkpoint with the tasks' results (`task_service.resume_answer`).
- **needs_attention:** a tool may have half run. A person has to look.

When a run ends, `task_service.run_ended` ends its task if it was a child (resuming the parent
when it was the last one), and cancels the tasks it still had open (their children are stopped).

A run the worker was in the middle of when it stopped (a restart, a crash) is still `running`;
its job comes back and `take_turn` carries on from the last saved step (Postgres checkpoints).
On SQLite, checkpoints live in memory, so such runs fail instead (`recover_after_restart`).
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.database import POOL_MAX_LIFETIME_SECONDS, IdleCheck, postgres_connect_args
from src.core.secrets import SecretBox
from src.jobs.queue import Job, JobQueue, run_key, run_lock
from src.models import Run
from src.plugins.registry import ToolRegistry, build_registry
from src.runtime.chat_model import ModelPrice, ModelResolver
from src.runtime.event_bus import EventBus
from src.runtime.graph import RunDeps, RunError, RunStopped, build_graph
from src.runtime.limits import RunLimits, time_limit_message
from src.runtime.memory import MemoryService, NoMemory
from src.runtime.reporter import RunReporter
from src.runtime.tool_access import ToolAccessProvider
from src.runtime.tool_pipeline import NeedsAttention
from src.services import approval_service, run_event_service, run_service, task_service
from src.services.credential_vault import CredentialVault
from src.services.model_catalog import ModelCatalog
from src.services.oauth_flow import OAuth

logger = logging.getLogger(__name__)

RUN_BOT = "run_bot"  # the job that moves one run forward (src/jobs/tasks.py)
SOMETHING_WENT_WRONG = "Something went wrong while replying. Try again."


@dataclass(frozen=True)
class RunTicket:
    """The few facts about a run needed to start it (copied, so no database object is shared)."""

    id: uuid.UUID
    org_id: uuid.UUID
    thread_id: uuid.UUID
    bot_id: uuid.UUID
    max_steps: int
    max_seconds: int

    @classmethod
    def of(cls, run: Run) -> "RunTicket":
        return cls(run.id, run.org_id, run.thread_id, run.bot_id, run.max_steps, run.max_seconds)


@dataclass(frozen=True)
class Outcome:
    """How one stretch of a run ended."""

    status: str  # succeeded | failed | cancelled | waiting_approval | waiting_handoff | needs_attention
    error: str | None = None
    code: str | None = None  # why it failed, for the web: "budget" when out of budget
    approval_id: str | None = None  # when waiting_approval: the approval it waits for
    task_ids: tuple[str, ...] = ()  # when waiting_handoff: the tasks it waits for


class RunManager:
    def __init__(
        self,
        *,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        checkpointer: BaseCheckpointSaver[Any],
        memory: MemoryService | None = None,
        bus: EventBus | None = None,
        registry: ToolRegistry | None = None,
        secrets: SecretBox,
        queue: JobQueue,
        catalog: ModelCatalog | None = None,
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.sessionmaker = sessionmaker
        self.bus = bus or EventBus()
        self.memory: MemoryService = memory or NoMemory()
        self.registry = registry or build_registry(settings.plugin_ids)
        # What tools may reach: their plugin's hosts, with its connection's credential (ADR 0010).
        # Tests set `tool_access.transport` to answer tools' requests without a network.
        vault = CredentialVault.from_settings(settings)
        # OAuth tokens are refreshed just before a tool uses them (services/oauth_flow.py).
        self.tool_access = ToolAccessProvider(
            sessionmaker, self.registry, vault, oauth=OAuth(settings, vault, self.registry)
        )
        resolver = ModelResolver(settings, sessionmaker, secrets, catalog)
        # (org id, model id) → the chat model, with the org's keys. Tests swap in a fake model here.
        self.model_for: Callable[[uuid.UUID, str], Awaitable[BaseChatModel]] = resolver
        # (org id, model id) → its price, for budgets and usage records. Tests swap in prices here.
        self.price_for: Callable[[uuid.UUID, str], Awaitable[ModelPrice]] = resolver.price
        # Tests about chats (not replies) switch this off: runs are created but never start.
        self.enabled = True
        self._graph = build_graph(checkpointer)
        # The runs executing in this process (their jobs' tasks), so Stop can cancel one at once.
        self._runs: dict[uuid.UUID, asyncio.Task[Any]] = {}
        # Keep a reference to every task: asyncio only holds weak ones, and a task that is
        # garbage-collected mid-run just vanishes.
        self._background: set[asyncio.Task[None]] = set()
        # Writes that must land even when their run is stopped or the API shuts down (usage).
        self._unstoppable: set[asyncio.Task[None]] = set()

    async def start(self, db: AsyncSession, runs: list[Run]) -> None:
        """Defer a job for each new run, in `db`'s transaction: the runs and their jobs are saved
        together when the caller commits."""
        if not self.enabled:
            return
        for run in runs:
            await self.queue.defer(run_job(run.id, run.thread_id), db=db)

    async def resume(self, db: AsyncSession, run: Run) -> None:
        """Defer the job that continues a paused run, in `db`'s transaction: with the decision, for
        an approval (the job reads the answer from the approval), or with the end of its last open
        task, for a handoff (the job reads the tasks' results)."""
        await self.start(db, [run])

    async def stop(self, run_id: uuid.UUID) -> None:
        """Stop button (and the cascade, and the task timeout). A queued or paused run is cancelled
        on the spot: its pending approvals expire, and its open tasks are cancelled (their children
        stop too). A running one gets the Stop flag and is aborted now. If it was a task's child,
        its task fails as stopped and the parent may resume. Stopping an ended run does nothing."""
        aftermath = task_service.Aftermath()
        async with self.sessionmaker() as db:
            run = await db.get(Run, run_id)
            if run is None:
                return
            if await run_service.request_stop(db, run):  # it wasn't running: cancelled right here
                for approval_id in await approval_service.expire_for_run(db, run.id):
                    view = await approval_service.view_by_id(db, approval_id)
                    run_event_service.add_event(
                        db,
                        org_id=run.org_id,
                        thread_id=run.thread_id,
                        run_id=run.id,
                        kind="approval_decided",
                        data={"approval": approval_service.approval_json(view, self.registry)},
                    )
                run_event_service.add_event(
                    db,
                    org_id=run.org_id,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    kind="run_finished",
                    data={"status": "cancelled"},
                )
                aftermath = await task_service.run_ended(db, run.id, status="cancelled", error=None, code=None)
                for parent in aftermath.resume:
                    await self.resume(db, parent)
            await db.commit()
            thread_id = run.thread_id
        self.bus.announce(thread_id)
        await self.stop_now(run_id)  # if it's running, stop it now, not at its next step
        for child_id in aftermath.stop:
            await self.stop(child_id)

    async def reconcile_tasks(self) -> None:
        """The handoffs' safety net (recovery): tasks whose child already ended are ended, the open
        tasks of runs that already ended are cancelled, and parents whose tasks have all ended
        resume (`task_service.reconcile`)."""
        async with self.sessionmaker() as db:
            aftermath = await task_service.reconcile(db)
            for parent in aftermath.resume:
                await self.resume(db, parent)
            threads = {run.thread_id for run in aftermath.resume}
            await db.commit()
        for thread_id in threads:
            self.bus.announce(thread_id)
        for child_id in aftermath.stop:
            await self.stop(child_id)

    async def stop_now(self, run_id: uuid.UUID) -> None:
        """Stop a running run straight away, not at its next step (its Stop flag is already
        saved): cancel it here, or ask the worker running it to."""
        if task := self._runs.get(run_id):
            task.cancel()
        else:
            await self.queue.abort(run_key(run_id))

    def in_background(self, work: Coroutine[Any, Any, None]) -> None:
        """Fire-and-forget work (like saving memories) that must not fail or slow a run."""
        task = asyncio.create_task(self._log_failure(work))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def unstoppable(self, work: Coroutine[Any, Any, None]) -> None:
        """Run `work` to the end even if the caller is cancelled (Stop, shutdown): it runs as its
        own task, which `close` waits for instead of cancelling. Keep such work short."""
        task = asyncio.create_task(self._log_failure(work))
        self._unstoppable.add(task)
        task.add_done_callback(self._unstoppable.discard)
        await asyncio.shield(task)

    async def warm_price(self, org_id: uuid.UUID, model_id: str) -> None:
        """Look up a model's price now (a bot was saved with it), so its first run doesn't wait for
        OpenRouter's model list. Never fails."""
        try:
            await self.price_for(org_id, model_id)
        except Exception:
            logger.warning("Couldn't look up the price of %s", model_id)

    async def wait_until_idle(self) -> None:
        """Wait until no run job is waiting or running and every background task has finished
        (tests use this). A run that pauses for approval counts as finished: its job has ended."""
        await self.queue.wait_until_idle()
        while self._background or self._unstoppable:
            await asyncio.gather(*self._background, *self._unstoppable, return_exceptions=True)
            await self.queue.wait_until_idle()  # a background task may have started a run

    async def recover_after_restart(self) -> None:
        """When a worker starts (and once a minute): runs that should be moving but have no job
        get one again. That's a run left `running` by a crash (it carries on from its last saved
        step), a `queued` one, and one `waiting_approval` whose approval was already decided.

        On SQLite nothing survives a restart (jobs and checkpoints live in memory), so unfinished
        runs fail with a clear message instead, or wait for a person if a tool call was half done.
        Runs waiting for approval stay paused either way."""
        if self.settings.uses_postgres:
            await self.reconcile_tasks()
            await self.pick_up_stuck_runs()
            return
        async with self.sessionmaker() as db:
            for run in await run_service.fail_interrupted_runs(db):
                reporter = self._reporter(RunTicket.of(run))
                if run.status == "needs_attention":
                    reporter.add(db, "run_needs_attention", {"status": run.status, "error": run.error})
                else:
                    reporter.add(db, "run_failed", {"status": "failed", "error": run_service.RESTART_ERROR})
            await db.commit()
        # Children that just failed end their tasks, and parents waiting for them resume (and
        # fail: their checkpoints were in memory too).
        await self.reconcile_tasks()

    async def pick_up_stuck_runs(self) -> None:
        """Postgres only: give every run that should be moving but has no job a job again."""
        async with self.sessionmaker() as db:
            stuck = await run_service.runs_to_pick_up(db)
        await self.queue.recover([run_job(run_id, thread_id) for run_id, thread_id in stuck])

    async def close(self) -> None:
        """At shutdown (after the worker stopped): stop background work, and let the usage writes
        of stopped runs finish."""
        for task in self._background:
            task.cancel()
        await asyncio.gather(*self._background, return_exceptions=True)
        await asyncio.gather(*self._unstoppable, return_exceptions=True)

    # The life of one run

    async def take_turn(self, run_id: uuid.UUID) -> bool:
        """The `run_bot` job: move this run forward. Starts a queued run, resumes a paused one
        whose approval was decided, or carries on with one a restart interrupted. Does nothing for
        a run that has ended or still waits for a person; safe to call again.

        False when the run can't go yet (an older run in its chat is still queued, or its bot
        already has `BOT_MAX_RUNNING_RUNS` going): defer the job again a little later."""
        async with self.sessionmaker() as db:
            run = await db.get(Run, run_id)
            if run is None:
                return True
            ticket, status = RunTicket.of(run), run.status
        reporter = self._reporter(ticket)
        graph_input: Any
        if status == "queued":
            claimed = await self._claim(ticket, "queued")
            if claimed is not True:
                return claimed is None
            async with self.sessionmaker() as db:
                await task_service.child_started(db, ticket.id)  # a task's child: its task is working
                await db.commit()
            await reporter.send("run_started", {"botId": str(ticket.bot_id)})
            graph_input = {}
        elif status == "waiting_approval":
            snapshot = await self._graph.aget_state(self._config(ticket))
            answer = None
            if snapshot.interrupts:
                answer = await self._answer(uuid.UUID(snapshot.interrupts[0].value["approvalId"]))
                if answer is None:
                    return True  # nobody has decided yet
            claimed = await self._claim(ticket, "waiting_approval")
            if claimed is not True:
                return claimed is None
            if answer is None:
                # The checkpoint is gone (in-memory checkpoints don't survive a restart).
                await self._finish(ticket, reporter, Outcome("failed", run_service.LOST_PAUSE_ERROR))
                return True
            await reporter.send("run_resumed", {"botId": str(ticket.bot_id), "after": "approval"})
            graph_input = Command(resume=answer)
        elif status == "waiting_handoff":
            snapshot = await self._graph.aget_state(self._config(ticket))
            task_ids = snapshot.interrupts[0].value.get("taskIds") if snapshot.interrupts else None
            async with self.sessionmaker() as db:
                tasks_answer = await task_service.resume_answer(db, ticket.id, task_ids)
            if tasks_answer is None:
                return True  # a task is still open; the last one to end defers this job again
            claimed = await self._claim(ticket, "waiting_handoff")
            if claimed is not True:
                return claimed is None
            if not snapshot.interrupts:
                # The checkpoint is gone (in-memory checkpoints don't survive a restart).
                await self._finish(ticket, reporter, Outcome("failed", run_service.LOST_PAUSE_ERROR))
                return True
            await reporter.send("run_resumed", {"botId": str(ticket.bot_id), "after": "tasks"})
            graph_input = Command(resume=tasks_answer)
        elif status == "running":
            # A restart stopped it mid-way: carry on from the last saved step (from the start if
            # it hadn't saved one). A tool call left half done stops it as needs_attention.
            snapshot = await self._graph.aget_state(self._config(ticket))
            await reporter.send("run_resumed", {"botId": str(ticket.bot_id)})
            graph_input = None if snapshot.values else {}
        else:
            return True
        self._runs[ticket.id] = task = asyncio.current_task()  # type: ignore[assignment]
        try:
            outcome = await self._execute(ticket, reporter, graph_input)
        finally:
            if self._runs.get(ticket.id) is task:
                del self._runs[ticket.id]
        await self._finish(ticket, reporter, outcome)
        return True

    async def _claim(self, ticket: RunTicket, from_status: str) -> bool | None:
        """True if this run is now running; False if it must wait its turn; None if it ended (or
        was stopped) meanwhile. The guarded UPDATE in `claim_run` keeps one running run per chat
        across workers, under the job queue's lock per chat."""
        async with self.sessionmaker() as db:
            if await run_service.claim_run(
                db, ticket.id, bot_cap=self.settings.bot_max_running_runs, from_status=from_status
            ):
                return True
            return False if await run_service.run_status(db, ticket.id) == from_status else None

    async def _answer(self, approval_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.sessionmaker() as db:
            return approval_service.resume_answer(await approval_service.status_of(db, approval_id))

    @staticmethod
    def _config(ticket: RunTicket) -> RunnableConfig:
        # Checkpoints are saved under the run id. Our step limit (checked in call_model) is the
        # real guard; LangGraph's recursion limit only stops a graph that loops by mistake.
        return {"configurable": {"thread_id": str(ticket.id)}, "recursion_limit": 200}

    async def _execute(self, ticket: RunTicket, reporter: RunReporter, graph_input: Any) -> Outcome:
        """Run the graph (from the start, or on from a pause) until it ends or pauses."""
        deps = RunDeps(
            run_id=ticket.id,
            org_id=ticket.org_id,
            bot_id=ticket.bot_id,
            thread_id=ticket.thread_id,
            limits=RunLimits(max_steps=ticket.max_steps, max_seconds=ticket.max_seconds),
            started_at=time.monotonic(),
            sessionmaker=self.sessionmaker,
            reporter=reporter,
            memory=self.memory,
            model_for=_once_per_model(partial(self.model_for, ticket.org_id)),
            price_for=partial(self.price_for, ticket.org_id),
            in_background=self.in_background,
            unstoppable=self.unstoppable,
            registry=self.registry,
            tool_timeout_seconds=self.settings.tool_timeout_seconds,
            approval_expiry=timedelta(hours=self.settings.approval_expiry_hours),
            settings=self.settings,
            start_runs=self.start,
            tool_access=self.tool_access,
        )
        try:
            # The time limit counts working time only: waiting for a person doesn't use it up.
            async with asyncio.timeout(ticket.max_seconds):
                # "sync": each step is saved before the next starts, so a pause is always on disk.
                result = await self._graph.ainvoke(
                    graph_input, self._config(ticket), context=deps, durability="sync", version="v2"
                )
        except RunStopped:
            return Outcome("cancelled")
        except asyncio.CancelledError:
            # Either Stop was pressed (stop_now) or the worker is shutting down. Then the run
            # stays `running`: its job goes back in the queue and it carries on after the restart.
            if await self._stop_was_requested(ticket.id):
                return Outcome("cancelled")
            raise
        except TimeoutError:
            return Outcome("failed", time_limit_message(ticket.max_seconds))
        except NeedsAttention as error:
            return Outcome("needs_attention", str(error))
        except RunError as error:
            return Outcome("failed", str(error), code=getattr(error, "code", None))
        except Exception:
            logger.exception("Run %s failed", ticket.id)
            return Outcome("failed", SOMETHING_WENT_WRONG)
        if result.interrupts:
            paused_on = result.interrupts[0].value
            if "taskIds" in paused_on:
                return Outcome("waiting_handoff", task_ids=tuple(str(task_id) for task_id in paused_on["taskIds"]))
            return Outcome("waiting_approval", approval_id=str(paused_on["approvalId"]))
        return Outcome("succeeded")

    async def _finish(self, ticket: RunTicket, reporter: RunReporter, outcome: Outcome) -> None:
        """Save how this stretch ended, with its event, in one transaction. A run that ended also
        ends its task (if it was a child) and cancels its own open tasks; what that resumes is
        deferred in the same transaction, and what it stops is stopped after the commit."""
        aftermath = task_service.Aftermath()
        async with self.sessionmaker() as db:
            if outcome.status == "waiting_handoff":
                # The UPDATE takes the run's row lock, so a task ending at this moment either sees
                # the run paused (and resumes it) or leaves it to `resume_if_ready` here.
                if await run_service.pause_run(db, ticket.id, status="waiting_handoff"):
                    data = {"status": "waiting_handoff", "taskIds": list(outcome.task_ids)}
                    reporter.add(db, "run_waiting_handoff", data)
                    if (ready := await task_service.resume_if_ready(db, ticket.id)) is not None:
                        await self.resume(db, ready)
            elif outcome.status == "waiting_approval" and outcome.approval_id:
                if await run_service.pause_run(db, ticket.id, status="waiting_approval"):
                    view = await approval_service.view_by_id(db, uuid.UUID(outcome.approval_id))
                    approval = approval_service.approval_json(view, self.registry)
                    reporter.add(db, "approval_requested", {"approval": approval})
            elif outcome.status == "needs_attention":
                if await run_service.pause_run(db, ticket.id, status="needs_attention", error=outcome.error):
                    reporter.add(db, "run_needs_attention", {"status": "needs_attention", "error": outcome.error})
            elif await run_service.finish_run(db, ticket.id, status=outcome.status, error=outcome.error):
                if outcome.status == "failed":
                    failed: dict[str, Any] = {"status": "failed", "error": outcome.error}
                    if outcome.code:
                        failed["code"] = outcome.code
                    reporter.add(db, "run_failed", failed)
                else:
                    reporter.add(db, "run_finished", {"status": outcome.status})
                aftermath = await task_service.run_ended(
                    db, ticket.id, status=outcome.status, error=outcome.error, code=outcome.code
                )
                for parent in aftermath.resume:
                    await self.resume(db, parent)
            await db.commit()
        reporter.announce()
        for child_id in aftermath.stop:
            await self.stop(child_id)

    async def _stop_was_requested(self, run_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as db:
            return await run_service.stop_requested(db, run_id)

    # Helpers

    def _reporter(self, ticket: RunTicket) -> RunReporter:
        return RunReporter(self.sessionmaker, self.bus, ticket.org_id, ticket.thread_id, ticket.id)

    @staticmethod
    async def _log_failure(work: Coroutine[Any, Any, None]) -> None:
        try:
            await work
        except Exception:
            logger.exception("Background work failed")


def run_job(run_id: uuid.UUID, thread_id: uuid.UUID) -> Job:
    """The job that moves a run forward. Runs in one chat share a lock, so they take turns in order."""
    return Job(
        RUN_BOT,
        {"run_id": str(run_id), "thread_id": str(thread_id)},
        lock=run_lock(thread_id),
        queueing_lock=run_key(run_id),
    )


def _once_per_model(
    model_for: Callable[[str], Awaitable[BaseChatModel]],
) -> Callable[[str], Awaitable[BaseChatModel]]:
    """Look each model up once per stretch of a run, not at every step: a lookup reads the
    organization's keys from the database (a round trip each time)."""
    models: dict[str, BaseChatModel] = {}

    async def cached(model_id: str) -> BaseChatModel:
        if model_id not in models:
            models[model_id] = await model_for(model_id)
        return models[model_id]

    return cached


def checkpoint_pool(url: str, *, idle_check: IdleCheck | None = None) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
    """The checkpoints' small pool of their own (not opened yet). A connection that sat idle is
    tested before use, so one that Neon closed while suspended is replaced, not handed to a run."""
    idle_check = idle_check or IdleCheck()
    return AsyncConnectionPool(
        url,
        min_size=1,
        max_size=3,
        open=False,
        configure=idle_check.configure,
        check=idle_check.check,
        reset=idle_check.reset,
        max_lifetime=POOL_MAX_LIFETIME_SECONDS,
        max_idle=POOL_MAX_LIFETIME_SECONDS,
        # LangGraph needs autocommit and dict rows.
        kwargs={"autocommit": True, "row_factory": dict_row, **postgres_connect_args(url)},
    )


@asynccontextmanager
async def checkpointer_for(settings: Settings) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """Postgres checkpoints (a small pool of their own, on the direct address), or in memory for SQLite."""
    if not settings.uses_postgres:
        yield InMemorySaver()
        return
    pool = checkpoint_pool(settings.direct_url)
    await pool.open()
    try:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # creates its tables the first time; quick after that
        yield checkpointer
    finally:
        await pool.close()

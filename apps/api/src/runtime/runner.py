"""Starts runs inside the API process and keeps track of them (ADR 0007).

Posting a message creates queued runs; `RunManager.start` turns each into an asyncio task.
A run waits for its chat's turn (one run at a time per chat), runs the graph, and ends as
succeeded, failed or cancelled, or pauses:

- **waiting_approval:** the graph called `interrupt()`. The task ends; the run is rows in
  Postgres. When a person decides, `RunManager.resume` starts a new task that continues the
  same checkpoint with `Command(resume=...)`.
- **needs_attention:** a tool may have half run. A person has to look.

Every step is saved in Postgres, so a job queue can take over starting and resuming runs
later without changing what a run does.
"""

import asyncio
import logging
import time
import uuid
from collections import Counter
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
from src.core.database import postgres_connect_args
from src.core.secrets import SecretBox
from src.models import Run
from src.plugins.registry import ToolRegistry, build_registry
from src.runtime.chat_model import ModelPrice, ModelResolver
from src.runtime.event_bus import EventBus
from src.runtime.graph import RunDeps, RunError, RunStopped, build_graph
from src.runtime.limits import RunLimits, time_limit_message
from src.runtime.memory import MemoryService, NoMemory
from src.runtime.reporter import RunReporter
from src.runtime.tool_pipeline import NeedsAttention
from src.services import approval_service, run_service
from src.services.model_catalog import ModelCatalog

logger = logging.getLogger(__name__)

TURN_CHECK_SECONDS = 0.5  # how often a waiting run asks "is it my turn yet?"
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

    status: str  # succeeded | failed | cancelled | waiting_approval | needs_attention
    error: str | None = None
    code: str | None = None  # why it failed, for the web: "budget" when out of budget
    approval_id: str | None = None  # when waiting_approval: the approval it waits for


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
        catalog: ModelCatalog | None = None,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.bus = bus or EventBus()
        self.memory: MemoryService = memory or NoMemory()
        self.registry = registry or build_registry(settings.plugin_ids)
        resolver = ModelResolver(settings, sessionmaker, secrets, catalog)
        # (org id, model id) → the chat model, with the org's keys. Tests swap in a fake model here.
        self.model_for: Callable[[uuid.UUID, str], Awaitable[BaseChatModel]] = resolver
        # (org id, model id) → its price, for budgets and usage records. Tests swap in prices here.
        self.price_for: Callable[[uuid.UUID, str], Awaitable[ModelPrice]] = resolver.price
        # Tests about chats (not replies) switch this off: runs are created but never start.
        self.enabled = True
        self._graph = build_graph(checkpointer)
        # Keep a reference to every task: asyncio only holds weak ones, and a task that is
        # garbage-collected mid-run just vanishes.
        self._runs: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._chat_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._chat_lock_users: Counter[uuid.UUID] = Counter()

    def start(self, runs: list[Run]) -> None:
        """Start each run in the background. Call after the runs are committed."""
        if not self.enabled:
            return
        for run in runs:
            self._track(RunTicket.of(run), self._run)

    def resume(self, run: Run, answer: dict[str, Any]) -> None:
        """Continue a run paused on an approval, with the person's answer. Call after the
        decision is committed. `answer` is `{"approved": bool, "message": str | None}`."""
        if not self.enabled:
            return
        self._track(RunTicket.of(run), partial(self._resume, answer=answer))

    def _track(self, ticket: RunTicket, work: Callable[[RunTicket], Coroutine[Any, Any, None]]) -> None:
        task = asyncio.create_task(work(ticket), name=f"run {ticket.id}")
        self._runs[ticket.id] = task
        task.add_done_callback(partial(self._forget_run, ticket.id))

    def _forget_run(self, run_id: uuid.UUID, task: asyncio.Task[None]) -> None:
        if self._runs.get(run_id) is task:
            del self._runs[run_id]

    def stop_now(self, run_id: uuid.UUID) -> None:
        """Stop a run running in this process straight away (its Stop flag is already saved)."""
        if task := self._runs.get(run_id):
            task.cancel()

    def in_background(self, work: Coroutine[Any, Any, None]) -> None:
        """Fire-and-forget work (like saving memories) that must not fail or slow a run."""
        task = asyncio.create_task(self._log_failure(work))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def wait_until_idle(self) -> None:
        """Wait for every run and background task to finish (tests use this). A run that pauses
        for approval counts as finished: its task has ended."""
        while self._runs or self._background:
            await asyncio.gather(*self._runs.values(), *self._background, return_exceptions=True)

    async def recover_after_restart(self) -> None:
        """At startup: runs a crash or restart left half done fail with a clear message, or wait
        for a person if a tool call was half done. Runs waiting for approval stay paused.
        (With several API copies this would also fail the others' runs; the job queue fixes that.)"""
        async with self.sessionmaker() as db:
            for run in await run_service.fail_interrupted_runs(db):
                reporter = self._reporter(RunTicket.of(run))
                if run.status == "needs_attention":
                    reporter.add(db, "run_needs_attention", {"status": run.status, "error": run.error})
                else:
                    reporter.add(db, "run_failed", {"status": "failed", "error": run_service.RESTART_ERROR})
            await db.commit()

    async def close(self) -> None:
        """At shutdown: stop what's running. Those runs fail as "interrupted by a restart"."""
        for task in [*self._runs.values(), *self._background]:
            task.cancel()
        await asyncio.gather(*self._runs.values(), *self._background, return_exceptions=True)

    # The life of one run

    async def _run(self, ticket: RunTicket) -> None:
        reporter = self._reporter(ticket)
        async with self._chat_lock(ticket.thread_id):
            if not await self._wait_for_turn(ticket.id):
                return  # cancelled while it waited
            await reporter.send("run_started", {"botId": str(ticket.bot_id)})
            outcome = await self._execute(ticket, reporter, {})
            await self._finish(ticket, reporter, outcome)

    async def _resume(self, ticket: RunTicket, answer: dict[str, Any]) -> None:
        reporter = self._reporter(ticket)
        async with self._chat_lock(ticket.thread_id):
            if not await self._wait_for_turn(ticket.id, from_status="waiting_approval"):
                return  # stopped while it waited
            if not await self._has_pause(ticket):
                # The checkpoint is gone (in-memory checkpoints don't survive a restart).
                await self._finish(ticket, reporter, Outcome("failed", run_service.LOST_PAUSE_ERROR))
                return
            await reporter.send("run_resumed", {"botId": str(ticket.bot_id)})
            outcome = await self._execute(ticket, reporter, Command(resume=answer))
            await self._finish(ticket, reporter, outcome)

    async def _wait_for_turn(self, run_id: uuid.UUID, *, from_status: str = "queued") -> bool:
        """True once this run is running; False if it ended (or was stopped) before its turn came.
        A run being resumed may still be `running` for a moment while it finishes pausing."""
        keep_waiting = {from_status} if from_status == "queued" else {from_status, "running"}
        while True:
            async with self.sessionmaker() as db:
                if await run_service.claim_run(
                    db, run_id, bot_cap=self.settings.bot_max_running_runs, from_status=from_status
                ):
                    return True
                if await run_service.run_status(db, run_id) not in keep_waiting:
                    return False
            await asyncio.sleep(TURN_CHECK_SECONDS)

    @staticmethod
    def _config(ticket: RunTicket) -> RunnableConfig:
        # Checkpoints are saved under the run id. Our step limit (checked in call_model) is the
        # real guard; LangGraph's recursion limit only stops a graph that loops by mistake.
        return {"configurable": {"thread_id": str(ticket.id)}, "recursion_limit": 200}

    async def _has_pause(self, ticket: RunTicket) -> bool:
        snapshot = await self._graph.aget_state(self._config(ticket))
        return bool(snapshot.interrupts)

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
            model_for=partial(self.model_for, ticket.org_id),
            price_for=partial(self.price_for, ticket.org_id),
            in_background=self.in_background,
            registry=self.registry,
            tool_timeout_seconds=self.settings.tool_timeout_seconds,
            approval_expiry=timedelta(hours=self.settings.approval_expiry_hours),
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
            # Either Stop was pressed (stop_now) or the API is shutting down.
            if await self._stop_was_requested(ticket.id):
                return Outcome("cancelled")
            return Outcome("failed", run_service.RESTART_ERROR)
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
            return Outcome("waiting_approval", approval_id=str(result.interrupts[0].value["approvalId"]))
        return Outcome("succeeded")

    async def _finish(self, ticket: RunTicket, reporter: RunReporter, outcome: Outcome) -> None:
        """Save how this stretch ended, with its event, in one transaction."""
        async with self.sessionmaker() as db:
            if outcome.status == "waiting_approval" and outcome.approval_id:
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
            await db.commit()
        reporter.announce()

    async def _stop_was_requested(self, run_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as db:
            return await run_service.stop_requested(db, run_id)

    # Helpers

    def _reporter(self, ticket: RunTicket) -> RunReporter:
        return RunReporter(self.sessionmaker, self.bus, ticket.org_id, ticket.thread_id, ticket.id)

    @asynccontextmanager
    async def _chat_lock(self, thread_id: uuid.UUID) -> AsyncIterator[None]:
        """Runs in the same chat take turns inside this process. (The database guard in
        `claim_run` covers other API copies.) The lock is dropped when nobody uses it."""
        lock = self._chat_locks.setdefault(thread_id, asyncio.Lock())
        self._chat_lock_users[thread_id] += 1
        try:
            async with lock:
                yield
        finally:
            self._chat_lock_users[thread_id] -= 1
            if not self._chat_lock_users[thread_id]:
                del self._chat_lock_users[thread_id], self._chat_locks[thread_id]

    @staticmethod
    async def _log_failure(work: Coroutine[Any, Any, None]) -> None:
        try:
            await work
        except Exception:
            logger.exception("Background work failed")


@asynccontextmanager
async def checkpointer_for(settings: Settings) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """Postgres checkpoints (a small pool of its own, on the direct address), or in memory for SQLite."""
    if not settings.uses_postgres:
        yield InMemorySaver()
        return
    url = settings.direct_url
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        url,
        min_size=1,
        max_size=3,
        open=False,
        # LangGraph needs autocommit and dict rows.
        kwargs={"autocommit": True, "row_factory": dict_row, **postgres_connect_args(url)},
    )
    await pool.open()
    try:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # creates its tables the first time; quick after that
        yield checkpointer
    finally:
        await pool.close()


@asynccontextmanager
async def run_manager(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    memory: MemoryService,
    secrets: SecretBox,
    catalog: ModelCatalog | None = None,
) -> AsyncIterator[RunManager]:
    """The API's run manager, for the lifetime of the app. `catalog` gives OpenRouter's prices."""
    async with checkpointer_for(settings) as checkpointer:
        runs = RunManager(
            settings=settings,
            sessionmaker=sessionmaker,
            checkpointer=checkpointer,
            memory=memory,
            secrets=secrets,
            catalog=catalog,
        )
        await runs.recover_after_restart()
        try:
            yield runs
        finally:
            await runs.close()

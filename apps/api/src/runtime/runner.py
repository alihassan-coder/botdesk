"""Starts runs inside the API process and keeps track of them (ADR 0007).

Posting a message creates queued runs; `RunManager.start` turns each into an asyncio task.
A run waits for its chat's turn (one run at a time per chat), runs the graph, and ends as
succeeded, failed or cancelled. Every step is saved in Postgres, so a job queue can take
over starting runs later without changing what a run does.
"""

import asyncio
import logging
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.database import postgres_connect_args
from src.models import Run
from src.runtime.chat_model import chat_model_for
from src.runtime.event_bus import EventBus
from src.runtime.graph import RunDeps, RunError, RunStopped, build_graph
from src.runtime.limits import RunLimits, time_limit_message
from src.runtime.memory import MemoryService, NoMemory
from src.runtime.reporter import RunReporter
from src.services import run_service

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


class RunManager:
    def __init__(
        self,
        *,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        checkpointer: BaseCheckpointSaver[Any],
        memory: MemoryService | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.bus = bus or EventBus()
        self.memory: MemoryService = memory or NoMemory()
        self.model_for: Callable[[str], BaseChatModel] = self._model_for
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
            ticket = RunTicket.of(run)
            task = asyncio.create_task(self._run(ticket), name=f"run {ticket.id}")
            self._runs[ticket.id] = task
            task.add_done_callback(partial(self._forget_run, ticket.id))

    def _forget_run(self, run_id: uuid.UUID, _task: asyncio.Task[None]) -> None:
        self._runs.pop(run_id, None)

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
        """Wait for every run and background task to finish (tests use this)."""
        while self._runs or self._background:
            await asyncio.gather(*self._runs.values(), *self._background, return_exceptions=True)

    async def recover_after_restart(self) -> None:
        """At startup: runs a crash or restart left half done fail with a clear message.
        (With several API copies this would also fail the others' runs; the job queue fixes that.)"""
        async with self.sessionmaker() as db:
            for run in await run_service.fail_interrupted_runs(db):
                reporter = self._reporter(RunTicket.of(run))
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
            status, error = await self._execute(ticket, reporter)
            await self._finish(ticket, reporter, status, error)

    async def _wait_for_turn(self, run_id: uuid.UUID) -> bool:
        """True once this run is running; False if it was cancelled before its turn came."""
        while True:
            async with self.sessionmaker() as db:
                if await run_service.claim_run(db, run_id, bot_cap=self.settings.bot_max_running_runs):
                    return True
                if await run_service.run_status(db, run_id) != "queued":
                    return False
            await asyncio.sleep(TURN_CHECK_SECONDS)

    async def _execute(self, ticket: RunTicket, reporter: RunReporter) -> tuple[str, str | None]:
        """Run the graph. Returns the run's final status and, if it failed, why."""
        deps = RunDeps(
            run_id=ticket.id,
            org_id=ticket.org_id,
            bot_id=ticket.bot_id,
            limits=RunLimits(max_steps=ticket.max_steps, max_seconds=ticket.max_seconds),
            started_at=time.monotonic(),
            sessionmaker=self.sessionmaker,
            reporter=reporter,
            memory=self.memory,
            model_for=self.model_for,
            in_background=self.in_background,
        )
        # Checkpoints are saved under the run id. Our step limit (checked in call_model) is the
        # real guard; LangGraph's recursion limit only stops a graph that loops by mistake.
        config: RunnableConfig = {"configurable": {"thread_id": str(ticket.id)}, "recursion_limit": 100}
        try:
            async with asyncio.timeout(ticket.max_seconds):
                await self._graph.ainvoke({}, config, context=deps)
        except RunStopped:
            return "cancelled", None
        except asyncio.CancelledError:
            # Either Stop was pressed (stop_now) or the API is shutting down.
            if await self._stop_was_requested(ticket.id):
                return "cancelled", None
            return "failed", run_service.RESTART_ERROR
        except TimeoutError:
            return "failed", time_limit_message(ticket.max_seconds)
        except RunError as error:
            return "failed", str(error)
        except Exception:
            logger.exception("Run %s failed", ticket.id)
            return "failed", SOMETHING_WENT_WRONG
        return "succeeded", None

    async def _finish(self, ticket: RunTicket, reporter: RunReporter, status: str, error: str | None) -> None:
        async with self.sessionmaker() as db:
            if await run_service.finish_run(db, ticket.id, status=status, error=error):
                if status == "failed":
                    reporter.add(db, "run_failed", {"status": status, "error": error})
                else:
                    reporter.add(db, "run_finished", {"status": status})
            await db.commit()
        reporter.announce()

    async def _stop_was_requested(self, run_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as db:
            return await run_service.stop_requested(db, run_id)

    # Helpers

    def _model_for(self, model_id: str) -> BaseChatModel:
        return chat_model_for(model_id, self.settings)

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
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], memory: MemoryService
) -> AsyncIterator[RunManager]:
    """The API's run manager, for the lifetime of the app."""
    async with checkpointer_for(settings) as checkpointer:
        runs = RunManager(settings=settings, sessionmaker=sessionmaker, checkpointer=checkpointer, memory=memory)
        await runs.recover_after_restart()
        try:
            yield runs
        finally:
            await runs.close()

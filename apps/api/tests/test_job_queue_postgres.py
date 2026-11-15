"""Runs as jobs on real Postgres (ADR 0013): procrastinate, a worker inside the app or on its own,
restarts, the approval expiry timer, and live events across processes."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from src.controllers import thread_controller
from src.core.database import create_engine, create_sessionmaker, utcnow
from src.core.secrets import build_secret_box
from src.jobs.background import background
from src.jobs.postgres import ProcrastinateQueue
from src.jobs.queue import JobEnv
from src.jobs.tasks import JOBS, expire_approvals
from src.main import create_app
from src.models import Approval, Run, ToolExecution
from src.runtime.memory import NoMemory
from src.runtime.runner import RunManager
from tests.conftest import TEST_DATABASE_URL, Postgres, _client_for, _empty_database, pg_settings
from tests.test_approvals_postgres import SEND, _chat, _paused_on_approval
from tests.test_runs_postgres import ScriptedModel, _bot_chat, _events, _send, _wait_for_status, use_model


def _runs(app: FastAPI) -> RunManager:
    runs: RunManager = app.state.runs
    return runs


@asynccontextmanager
async def _app(**settings: object) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    """An app on the test database that isn't emptied first (a "restart" keeps the data)."""
    app = create_app(pg_settings(**settings))
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        yield app, http


@pytest.fixture
async def empty() -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("Postgres test: set TEST_DATABASE_URL to run it (see docs/backend/README.md)")
    await _empty_database(TEST_DATABASE_URL)


async def test_runs_in_one_chat_take_turns_through_the_queue(pg: Postgres) -> None:
    assert isinstance(pg.runs.queue, ProcrastinateQueue)
    use_model(pg, ScriptedModel(tokens=["a", "b", "c"], delay=0.05))
    org, thread = await _bot_chat(pg.client)

    first = await _send(pg.client, thread, "One")
    second = await _send(pg.client, thread, "Two")
    await pg.runs.wait_until_idle()

    one, two = [(await pg.client.get(f"{org}/runs/{run_id}")).json() for run_id in (first, second)]
    assert one["status"] == two["status"] == "succeeded"
    started, finished = datetime.fromisoformat(two["startedAt"]), datetime.fromisoformat(one["finishedAt"])
    assert started >= finished  # never side by side


async def test_a_run_interrupted_by_a_restart_carries_on_after_it(empty: None) -> None:
    async with _app() as (app, client):
        use_model(Postgres(client, _runs(app)), ScriptedModel(tokens=["slow "] * 400, delay=0.05))
        org, thread = await _bot_chat(client)
        run_id = await _send(client, thread, "Write a novel")
        await _wait_for_status(client, org, run_id, "running")
        await asyncio.sleep(0.3)
        signed_in = httpx.Cookies(client.cookies)
    # The app stopped mid-reply: the run is still `running`, and its job went back in the queue.

    async with _app() as (app, client):
        client.cookies = signed_in
        use_model(Postgres(client, _runs(app)), ScriptedModel(tokens=["Done."]))
        await _runs(app).wait_until_idle()

        run = (await client.get(f"{org}/runs/{run_id}")).json()
        assert run["status"] == "succeeded"
        kinds = [event["event"] for event in await _events(client, thread)]
        assert kinds.count("run_started") == 1
        assert "run_resumed" in kinds
        assert kinds[-1] == "run_finished"
        replies = [m for m in (await client.get(f"{thread}/messages")).json() if m["author"]["type"] == "bot"]
        assert [m["parts"][-1]["text"] for m in replies] == ["Done."]


async def test_an_approval_nobody_answers_expires_on_the_timer_and_the_run_carries_on(pg: Postgres) -> None:
    assert "expire_approvals" in {task.name for task in JOBS.periodic}
    org, thread = await _chat(pg.client)
    run_id, approval = await _paused_on_approval(pg, thread, SEND)
    async with pg.runs.sessionmaker() as db:
        await db.execute(update(Approval).values(expires_at=utcnow() - timedelta(minutes=1)))
        await db.commit()

    env = JobEnv(runs=pg.runs, queue=pg.runs.queue, sessionmaker=pg.runs.sessionmaker, settings=pg.runs.settings)
    await expire_approvals(env, timestamp=0)
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/approvals/{approval['id']}")).json()["status"] == "expired"
    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    async with pg.runs.sessionmaker() as db:
        assert await db.scalar(select(ToolExecution.status)) == "denied"  # never sent
    events = await _events(pg.client, thread)
    decided = [e for e in events if e["event"] == "approval_decided"]
    assert decided[-1]["data"]["data"]["approval"]["status"] == "expired"
    assert [e["event"] for e in events][-2:] == ["message_saved", "run_finished"]


async def test_a_separate_worker_runs_the_reply_and_its_events_reach_the_apis_stream(
    empty: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(thread_controller, "RECHECK_SECONDS", 60.0)  # only a notification can wake it
    settings = pg_settings(worker_mode="separate")
    engine = create_engine(settings.sqlalchemy_url)
    async with (
        _app(worker_mode="separate") as (app, client),
        background(
            settings, create_sessionmaker(engine), NoMemory(), build_secret_box(settings), role="worker"
        ) as worker,
    ):
        assert isinstance(worker.queue, ProcrastinateQueue)
        working = asyncio.create_task(worker.queue.run_worker(worker, concurrency=2))
        try:
            _org, thread = await _bot_chat(client)
            thread_id = uuid.UUID(thread.rsplit("/", 1)[1])
            stream = thread_controller.follow_events(_runs(app), thread_id, after_id=0, follow=True)
            await _send(client, thread, "Hi Scout")
            # The bot's reply is saved before the run is marked finished (a separate transaction),
            # so wait for run_finished, which is saved together with the run's new status.
            saw_reply = False
            async with asyncio.timeout(20):
                async for event in stream:
                    if event.event == "message_saved" and event.data["data"]["message"]["author"]["type"] == "bot":
                        saw_reply = True
                    if event.event == "run_finished":
                        break
            assert saw_reply
            await stream.aclose()  # type: ignore[attr-defined]  # an async generator
            async with worker.sessionmaker() as db:
                assert await db.scalar(select(Run.status)) == "succeeded"
        finally:
            working.cancel()
            await asyncio.gather(working, return_exceptions=True)
    await engine.dispose()

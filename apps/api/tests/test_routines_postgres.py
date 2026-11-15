"""Routines end to end on real Postgres: the every-minute job fires a due routine, the job queue
runs it, and the bot's reply lands in the creator's DM, at the routine's security level."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from src.jobs.queue import JobEnv
from src.jobs.tasks import fire_routines
from src.models import Routine, Run, ToolExecution
from src.runtime.chat_model import StandInModel
from tests.conftest import Postgres, sign_up
from tests.test_runs_postgres import use_model

SEND = "/tool demo.send_email to=sara@acme.dev subject=Launch"


async def _routine(pg: Postgres, instructions: str, **extra: Any) -> tuple[str, dict[str, Any]]:
    me = await sign_up(pg.client, name="Sara Khan", email="sara@acme.dev")
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await pg.client.post(f"{org}/bots", json={"name": "Reader"})).json()
    body = {"botId": bot["id"], "name": "Digest", "instructions": instructions, "cron": "0 9 * * *"}
    created = await pg.client.post(f"{org}/routines", json=body | {"timezone": "Asia/Karachi"} | extra)
    assert created.status_code == 201, created.text
    return org, created.json()


async def _fire_now(pg: Postgres, routine_id: str) -> None:
    now = datetime.now(UTC)
    async with pg.runs.sessionmaker() as db:
        await db.execute(
            update(Routine).where(Routine.id == uuid.UUID(routine_id)).values(next_run_at=now - timedelta(minutes=1))
        )
        await db.commit()
    runs = pg.runs
    await fire_routines(JobEnv(runs, runs.queue, runs.sessionmaker, runs.settings), timestamp=int(now.timestamp()))
    await runs.wait_until_idle()


async def test_a_due_routine_runs_and_the_bot_replies_in_the_creators_dm(pg: Postgres) -> None:
    use_model(pg, StandInModel(provider="test"))
    org, routine = await _routine(pg, "Sum up yesterday's chats.")
    await _fire_now(pg, routine["id"])

    async with pg.runs.sessionmaker() as db:
        [run] = list(await db.scalars(select(Run)))
    assert run.status == "succeeded" and run.hop == 0
    dm = (await pg.client.post(f"{org}/threads/dm", json={"botId": routine["botId"]})).json()
    assert str(run.thread_id) == dm["id"]
    messages = (await pg.client.get(f"{org}/threads/{dm['id']}/messages")).json()
    kinds = [(m["author"]["type"], m["parts"][0].get("type")) for m in messages]
    # The "Created a routine" card, the routine's trigger, then the bot's reply.
    assert kinds == [("system", "routine-created"), ("system", "text"), ("bot", "text")]
    assert messages[1]["parts"][0]["text"] == "Routine: Digest"
    listed = (await pg.client.get(f"{org}/routines")).json()[0]
    assert listed["lastResult"] == "succeeded"


async def test_a_read_only_routine_cannot_send_even_if_its_bot_would_ask(pg: Postgres) -> None:
    use_model(pg, StandInModel(provider="test"))
    _, routine = await _routine(pg, SEND, securityLevel="read-only")
    await _fire_now(pg, routine["id"])

    async with pg.runs.sessionmaker() as db:
        [run] = list(await db.scalars(select(Run)))
        [call] = list(await db.scalars(select(ToolExecution)))
    assert call.tool_name == "demo.send_email"
    assert call.decision == "deny"  # the bot alone ("Ask before acting") would have asked
    assert run.status == "succeeded"

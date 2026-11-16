"""Routines (slice 4), on SQLite: saving them, who may change them, Run now, and the every-minute
`fire_routines` job that starts a run in the creator's DM when one is due. Runs don't start here;
the tests look at the runs and messages a routine leaves behind."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from src.jobs.queue import JobEnv
from src.jobs.tasks import fire_routines
from src.models import Message, Routine, Run
from src.runtime.runner import RunManager
from src.services import run_service, usage_service
from tests.conftest import PASSWORD, TEST_SETTINGS, FakeProviders, api_client, sign_up

ORGS = "/api/v1/orgs"
DAILY = {"cron": "0 9 * * *", "timezone": "Asia/Karachi"}


@dataclass
class Team:
    app: FastAPI
    client: httpx.AsyncClient
    org_id: str
    ali: str  # the owner
    sara: str  # a member
    bot: str  # Reader's id

    @property
    def url(self) -> str:
        return f"{ORGS}/{self.org_id}/routines"

    @property
    def runs(self) -> RunManager:
        runs: RunManager = self.app.state.runs
        return runs

    async def sign_in(self, email: str) -> None:
        self.client.cookies.clear()
        response = await self.client.post("/api/v1/auth/sign-in", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text

    async def create(self, **body: Any) -> dict[str, Any]:
        payload = {"botId": self.bot, "name": "Morning digest", "instructions": "Sum up yesterday's chats.", **DAILY}
        response = await self.client.post(self.url, json=payload | body)
        assert response.status_code == 201, response.text
        routine: dict[str, Any] = response.json()
        return routine

    async def make_due(self, routine_id: str, at: datetime) -> None:
        async with self.runs.sessionmaker() as db:
            await db.execute(update(Routine).where(Routine.id == uuid.UUID(routine_id)).values(next_run_at=at))
            await db.commit()

    async def fire(self, now: datetime) -> None:
        runs = self.runs
        env = JobEnv(runs=runs, queue=runs.queue, sessionmaker=runs.sessionmaker, settings=runs.settings)
        await fire_routines(env, timestamp=int(now.timestamp()))

    async def routine_runs(self) -> list[Run]:
        async with self.runs.sessionmaker() as db:
            return list(await db.scalars(select(Run).order_by(Run.created_at)))

    async def get(self, routine_id: str) -> dict[str, Any]:
        found = [r for r in (await self.client.get(self.url)).json() if r["id"] == routine_id]
        assert found, "routine not listed"
        routine: dict[str, Any] = found[0]
        return routine


@pytest.fixture
async def team(providers: FakeProviders) -> AsyncIterator[Team]:
    """Ali owns Acme and hired Reader; Sara joined as a member. Sara is signed in."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        ali = await sign_up(client, "Ali", "ali@acme.dev")
        org_id = ali["organizations"][0]["id"]
        bot = (await client.post(f"{ORGS}/{org_id}/bots", json={"name": "Reader"})).json()
        invite = await client.post(f"{ORGS}/{org_id}/invitations", json={"email": "sara@acme.dev", "role": "member"})
        token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
        client.cookies.clear()
        sara = await sign_up(client, "Sara", "sara@acme.dev")
        assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
        yield Team(app, client, org_id, ali["user"]["id"], sara["user"]["id"], bot["id"])


def utc(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


# Saving routines


async def test_a_member_creates_a_routine_and_it_is_listed_with_its_next_run(team: Team) -> None:
    routine = await team.create()
    assert routine["name"] == "Morning digest"
    assert routine["createdBy"] == team.sara
    assert routine["enabled"] is True
    assert routine["nextRunAt"] is not None
    # 09:00 in Karachi is 04:00 UTC.
    assert datetime.fromisoformat(routine["nextRunAt"]).astimezone(UTC).hour == 4
    listed = (await team.client.get(team.url)).json()
    assert [r["id"] for r in listed] == [routine["id"]]
    assert (await team.client.get(team.url, params={"botId": team.bot})).json()[0]["id"] == routine["id"]
    assert (await team.client.get(team.url, params={"botId": str(uuid.uuid4())})).json() == []


async def test_creating_a_routine_says_so_in_the_creators_dm(team: Team) -> None:
    routine = await team.create()
    dm = (await team.client.post(f"{ORGS}/{team.org_id}/threads/dm", json={"botId": team.bot})).json()
    messages = (await team.client.get(f"{ORGS}/{team.org_id}/threads/{dm['id']}/messages")).json()
    assert messages[-1]["author"]["type"] == "system"
    assert {"type": "routine-created", "routineId": routine["id"], "name": "Morning digest"} in messages[-1]["parts"]


async def test_a_switched_off_routine_has_no_next_run(team: Team) -> None:
    routine = await team.create(enabled=False)
    assert routine["nextRunAt"] is None


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"cron": "every day"}, 400),
        ({"cron": "0 9 * *"}, 400),
        ({"timezone": "Mars/Olympus"}, 400),
        ({"name": ""}, 422),
        ({"instructions": ""}, 422),
        ({"securityLevel": "wide-open"}, 422),
        ({"botId": str(uuid.uuid4())}, 404),
    ],
)
async def test_bad_routines_are_refused(team: Team, change: dict[str, Any], status: int) -> None:
    body = {"botId": team.bot, "name": "Digest", "instructions": "Sum up.", **DAILY} | change
    assert (await team.client.post(team.url, json=body)).status_code == status


async def test_switching_off_and_on_and_editing_the_schedule(team: Team) -> None:
    routine = await team.create()
    off = await team.client.patch(f"{team.url}/{routine['id']}", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert off.json()["enabled"] is False and off.json()["nextRunAt"] is None
    on = (await team.client.patch(f"{team.url}/{routine['id']}", json={"enabled": True, "cron": "0 * * * *"})).json()
    assert on["enabled"] is True and on["cron"] == "0 * * * *"
    assert datetime.fromisoformat(on["nextRunAt"]).minute == 0
    renamed = (await team.client.patch(f"{team.url}/{routine['id']}", json={"name": "Digest"})).json()
    assert renamed["name"] == "Digest" and renamed["nextRunAt"] == on["nextRunAt"]


async def test_only_the_creator_owners_and_admins_change_a_routine(team: Team) -> None:
    routine = await team.create()  # Sara's
    url = f"{team.url}/{routine['id']}"
    # Another member: can see it, can't touch it.
    await team.sign_in("ali@acme.dev")
    invite = await team.client.post(f"{ORGS}/{team.org_id}/invitations", json={"email": "omar@acme.dev"})
    team.client.cookies.clear()
    await sign_up(team.client, "Omar", "omar@acme.dev")
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    assert (await team.client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
    assert [r["id"] for r in (await team.client.get(team.url)).json()] == [routine["id"]]
    for response in (
        await team.client.patch(url, json={"enabled": False}),
        await team.client.post(f"{url}/run-now"),
        await team.client.delete(url),
    ):
        assert response.status_code == 403
        assert response.json()["detail"] == "Only the routine's creator, owners and admins can change it."
    # The owner can.
    await team.sign_in("ali@acme.dev")
    assert (await team.client.patch(url, json={"enabled": False})).status_code == 200
    assert (await team.client.delete(url)).status_code == 204
    assert (await team.client.get(team.url)).json() == []


async def test_routines_are_private_to_their_organization(team: Team) -> None:
    routine = await team.create()
    team.client.cookies.clear()
    await sign_up(team.client, "Eve", "eve@else.dev")
    assert (await team.client.get(team.url)).status_code == 404
    assert (await team.client.post(f"{team.url}/{routine['id']}/run-now")).status_code == 404


# Run now


async def test_run_now_starts_a_run_in_the_creators_dm_for_the_creator(team: Team) -> None:
    routine = await team.create(enabled=False)
    response = await team.client.post(f"{team.url}/{routine['id']}/run-now")
    assert response.status_code == 202, response.text
    run_id = response.json()["runId"]
    run = (await team.client.get(f"{ORGS}/{team.org_id}/runs/{run_id}")).json()
    assert run["status"] == "queued" and run["hop"] == 0 and run["botId"] == team.bot
    async with team.app.state.sessionmaker() as db:
        requester = await db.scalar(select(Run.requester_id).where(Run.id == uuid.UUID(run_id)))
    assert str(requester) == team.sara  # the routine acts for the member who set it up (Sara)
    dm = (await team.client.post(f"{ORGS}/{team.org_id}/threads/dm", json={"botId": team.bot})).json()
    assert run["threadId"] == dm["id"]
    messages = (await team.client.get(f"{ORGS}/{team.org_id}/threads/{dm['id']}/messages")).json()
    trigger = messages[-1]
    assert trigger["author"]["type"] == "system"
    assert trigger["parts"][0] == {"type": "text", "text": "Routine: Morning digest"}
    runs = (await team.client.get(f"{team.url}/{routine['id']}/runs")).json()
    assert [(r["runId"], r["status"], r["threadId"]) for r in runs] == [(run_id, "queued", dm["id"])]
    assert (await team.get(routine["id"]))["lastResult"] == "queued"
    # Run now doesn't move the schedule: it's still off.
    assert (await team.get(routine["id"]))["nextRunAt"] is None


async def test_run_now_waits_for_the_last_run_to_finish(team: Team) -> None:
    routine = await team.create()
    assert (await team.client.post(f"{team.url}/{routine['id']}/run-now")).status_code == 202
    again = await team.client.post(f"{team.url}/{routine['id']}/run-now")
    assert again.status_code == 409
    assert again.json()["detail"] == "This routine's last run is still going."


async def test_the_run_reads_the_routine_as_its_question_at_the_routines_level(team: Team) -> None:
    routine = await team.create(securityLevel="read-only")
    run_id = (await team.client.post(f"{team.url}/{routine['id']}/run-now")).json()["runId"]
    async with team.runs.sessionmaker() as db:
        context = await run_service.run_context(db, uuid.UUID(run_id))
    assert context.security_level == "read-only"  # stricter than the bot's "ask-before-acting"
    assert context.member_id == uuid.UUID(team.sara)  # the requester: the routine's creator
    assert context.history[-1].author_type == "user"
    assert "Sum up yesterday's chats." in context.history[-1].text
    assert "Morning digest" in context.history[-1].text


async def test_a_routine_cannot_loosen_its_bots_level(team: Team) -> None:
    await team.sign_in("ali@acme.dev")
    await team.client.patch(f"{ORGS}/{team.org_id}/bots/{team.bot}", json={"securityLevel": "read-only"})
    routine = await team.create(securityLevel="autonomous")
    run_id = (await team.client.post(f"{team.url}/{routine['id']}/run-now")).json()["runId"]
    async with team.runs.sessionmaker() as db:
        assert (await run_service.run_context(db, uuid.UUID(run_id))).security_level == "read-only"


# The every-minute job


async def test_a_due_routine_starts_a_run_in_the_creators_dm_and_moves_to_its_next_slot(team: Team) -> None:
    routine = await team.create()
    await team.make_due(routine["id"], utc(2026, 11, 15, 4, 0))
    await team.fire(utc(2026, 11, 15, 4, 0, 20))
    [run] = await team.routine_runs()
    assert (run.bot_id, run.hop, run.status) == (uuid.UUID(team.bot), 0, "queued")
    async with team.runs.sessionmaker() as db:
        trigger = await db.get(Message, run.trigger_message_id)
    assert trigger is not None and trigger.author_type == "system"
    listed = await team.get(routine["id"])
    assert datetime.fromisoformat(listed["nextRunAt"]) == utc(2026, 11, 16, 4, 0)
    assert datetime.fromisoformat(listed["lastRunAt"]) == utc(2026, 11, 15, 4, 0, 20)
    # The same minute again (a second worker, a retry): nothing more.
    await team.fire(utc(2026, 11, 15, 4, 0, 40))
    assert len(await team.routine_runs()) == 1


async def test_a_routine_not_yet_due_or_switched_off_does_not_run(team: Team) -> None:
    later = await team.create()
    off = await team.create(name="Off")
    await team.make_due(later["id"], utc(2026, 11, 15, 5, 0))
    await team.make_due(off["id"], utc(2026, 11, 15, 4, 0))
    await team.client.patch(f"{team.url}/{off['id']}", json={"enabled": False})
    await team.fire(utc(2026, 11, 15, 4, 30))
    assert await team.routine_runs() == []


async def test_slots_missed_while_the_server_was_down_run_once_not_as_a_backlog(team: Team) -> None:
    routine = await team.create()
    await team.make_due(routine["id"], utc(2026, 11, 10, 4, 0))  # five days of slots missed
    await team.fire(utc(2026, 11, 15, 3, 0))
    assert len(await team.routine_runs()) == 1
    assert datetime.fromisoformat((await team.get(routine["id"]))["nextRunAt"]) == utc(2026, 11, 15, 4, 0)


async def test_a_routine_whose_bot_was_removed_is_switched_off_with_a_reason(team: Team) -> None:
    routine = await team.create()
    await team.make_due(routine["id"], utc(2026, 11, 15, 4, 0))
    await team.sign_in("ali@acme.dev")
    assert (await team.client.delete(f"{ORGS}/{team.org_id}/bots/{team.bot}")).status_code == 204
    await team.fire(utc(2026, 11, 15, 4, 1))
    assert await team.routine_runs() == []
    listed = await team.get(routine["id"])
    assert listed["enabled"] is False and listed["nextRunAt"] is None
    assert listed["disabledReason"] == "Its bot was removed."


async def test_a_routine_whose_bot_is_over_budget_is_switched_off_with_a_reason(team: Team) -> None:
    routine = await team.create()
    run_id = (await team.client.post(f"{team.url}/{routine['id']}/run-now")).json()["runId"]
    async with team.runs.sessionmaker() as db:
        await db.execute(update(Run).values(status="succeeded"))
        usage_service.record(
            db, org_id=uuid.UUID(team.org_id), bot_id=uuid.UUID(team.bot), run_id=uuid.UUID(run_id),
            provider="anthropic", model_id="m", input_tokens=1, output_tokens=1, cost_usd=60.0,
        )  # fmt: skip
        await db.commit()
    now = datetime.now(UTC)
    await team.make_due(routine["id"], now - timedelta(minutes=1))
    await team.fire(now)
    assert len(await team.routine_runs()) == 1  # only the Run now one
    listed = await team.get(routine["id"])
    assert listed["enabled"] is False
    assert listed["disabledReason"] == "Reader reached its $50 monthly budget. Raise it in the bot's settings."


async def test_a_routine_whose_last_run_is_still_going_skips_its_slot(team: Team) -> None:
    routine = await team.create()
    await team.make_due(routine["id"], utc(2026, 11, 15, 4, 0))
    await team.fire(utc(2026, 11, 15, 4, 0, 10))
    await team.make_due(routine["id"], utc(2026, 11, 15, 4, 1))
    await team.fire(utc(2026, 11, 15, 4, 1, 10))  # the first run is still queued
    assert len(await team.routine_runs()) == 1
    runs = (await team.client.get(f"{team.url}/{routine['id']}/runs")).json()
    assert [r["status"] for r in runs] == ["skipped", "queued"]
    assert (await team.get(routine["id"]))["lastResult"] == "skipped"


async def test_a_finished_run_shows_as_the_routines_last_result(team: Team) -> None:
    routine = await team.create()
    await team.make_due(routine["id"], utc(2026, 11, 15, 4, 0))
    await team.fire(utc(2026, 11, 15, 4, 0, 10))
    async with team.runs.sessionmaker() as db:
        await db.execute(update(Run).values(status="succeeded"))
        await db.commit()
    assert (await team.get(routine["id"]))["lastResult"] == "succeeded"
    # A finished run doesn't block the next slot.
    await team.make_due(routine["id"], utc(2026, 11, 16, 4, 0))
    await team.fire(utc(2026, 11, 16, 4, 0, 10))
    assert len(await team.routine_runs()) == 2


async def test_fire_routines_is_a_periodic_job() -> None:
    from src.jobs.tasks import JOBS

    assert JOBS.tasks["fire_routines"].cron == "* * * * *"


async def test_a_due_routines_run_waits_until_now(team: Team) -> None:
    """The job's `timestamp` is the minute it was meant for: a routine due later isn't run early."""
    routine = await team.create()
    await team.make_due(routine["id"], utc(2026, 11, 15, 4, 0) + timedelta(seconds=30))
    await team.fire(utc(2026, 11, 15, 4, 0))
    assert await team.routine_runs() == []

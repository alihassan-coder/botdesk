"""Bots' cloud computers (ADR 0020): the organization's Orgo key, each bot's Browser-or-Cloud
choice, a computer's life (made on first use, started, stopped when idle, deleted with its bot),
watching and taking over, and Orgo's refusals in words people can act on. Orgo is a fake
(tests/orgo_fake.py); nothing here reaches orgo.ai."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.computers.base import (
    Busy,
    ComputerError,
    Gone,
    KeyRefused,
    MayHaveRun,
    NoRoom,
    NotAllowed,
    OutOfCredit,
    RateLimited,
    Unreachable,
)
from src.computers.orgo import OrgoComputers
from src.core.config import Settings
from src.core.database import Base, create_engine, create_sessionmaker, utcnow
from src.models import Bot, BotComputer, ComputerProvider, Organization, UsageRecord
from src.services.computer_service import Computers
from src.services.credential_vault import CredentialVault
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up
from tests.orgo_fake import HOST, KEY, RAW_ADDRESS, ROOT_PASSWORD, FakeOrgo
from tests.test_members import _sign_in, _team

API = "https://www.orgo.ai/api"


@dataclass
class Desk:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    org_id: uuid.UUID
    orgo: FakeOrgo

    @property
    def computers(self) -> Computers:
        computers: Computers = self.app.state.runs.computers
        return computers

    async def add_key(self, key: str = KEY) -> httpx.Response:
        return await self.client.put(f"{self.org}/computer-provider", json={"provider": "orgo", "apiKey": key})

    async def cloud_bot(self, name: str = "Coder") -> str:
        bot = (await self.client.post(f"{self.org}/bots", json={"name": name})).json()
        switched = await self.client.patch(f"{self.org}/bots/{bot['id']}", json={"computer": "cloud"})
        assert switched.status_code == 200, switched.text
        bot_id: str = bot["id"]
        return bot_id

    async def row(self, bot_id: str) -> BotComputer | None:
        async with self.app.state.sessionmaker() as db:
            row: BotComputer | None = await db.scalar(
                select(BotComputer).where(BotComputer.bot_id == uuid.UUID(bot_id))
            )
            return row

    async def usage(self) -> list[UsageRecord]:
        async with self.app.state.sessionmaker() as db:
            return list(await db.scalars(select(UsageRecord).where(UsageRecord.kind == "computer")))


@pytest.fixture
async def desk(providers: FakeProviders) -> AsyncIterator[Desk]:
    orgo = FakeOrgo()
    providers.answer(HOST, handler=orgo.handle)
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        app.state.runs.computers.poll_seconds = 0
        me = await sign_up(client)
        org_id = me["organizations"][0]["id"]
        yield Desk(app=app, client=client, org=f"/api/v1/orgs/{org_id}", org_id=uuid.UUID(org_id), orgo=orgo)


# Orgo's answers, in BotDesk's words


@pytest.mark.parametrize(
    ("status", "answer", "refusal", "words"),
    [
        (401, {"error": "Invalid API key"}, KeyRefused, "refused the organization's key"),
        (402, {"error": "Choose a plan to continue."}, OutOfCredit, "out of credit"),
        (403, {"error": f"This API key {KEY} cannot access this workspace."}, NotAllowed, "didn't allow that"),
        (404, {"error": "Computer not found"}, Gone, "isn't at Orgo any more"),
        (409, {"error": "Waking up", "code": "computer_waking"}, Busy, "busy"),
        (429, {"error": "Too many", "code": "rate_limited"}, RateLimited, "too many requests"),
        (503, {"error": "Could not reach the desktop."}, Unreachable, "couldn't reach the computer"),
    ],
)
async def test_orgos_refusals_say_what_to_do_without_the_key(
    status: int, answer: dict[str, Any], refusal: type[ComputerError], words: str
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(status, json=answer)

    orgo = OrgoComputers(KEY, base_url=API, transport=httpx.MockTransport(refuse))
    with pytest.raises(refusal) as raised:
        await orgo.click("pc-1", 10, 10, button="left", double=False)
    assert words in str(raised.value)
    assert KEY not in str(raised.value) and KEY not in repr(orgo)


async def test_no_room_and_lost_answers_while_making_or_running() -> None:
    def no_room(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "REGION_UNAVAILABLE", "code": "REGION_UNAVAILABLE"})

    orgo = OrgoComputers(KEY, base_url=API, transport=httpx.MockTransport(no_room))
    with pytest.raises(NoRoom, match="no room for a computer"):
        await orgo.create(workspace_id="ws", name="botdesk-coder", idempotency_key="k")

    def lost(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    orgo = OrgoComputers(KEY, base_url=API, transport=httpx.MockTransport(lost))
    with pytest.raises(MayHaveRun, match="may have run"):  # not a NotDone: the pipeline asks a person
        await orgo.bash("pc-1", "make deploy", seconds=10)
    with pytest.raises(Unreachable):  # anything else lost: nothing was done
        await orgo.stop("pc-1")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    orgo = OrgoComputers(KEY, base_url=API, transport=httpx.MockTransport(down))
    with pytest.raises(Unreachable, match="couldn't reach Orgo"):  # it never left
        await orgo.bash("pc-1", "make deploy", seconds=10)


# The organization's key


async def test_an_admin_adds_the_orgo_key_checked_live(desk: Desk) -> None:
    assert (await desk.client.get(f"{desk.org}/computer-provider")).json() == {
        "provider": None,
        "keyHint": None,
        "checkedAt": None,
        "status": None,
    }

    wrong = await desk.add_key("sk_live_wrong_key_0000")
    assert wrong.status_code == 400
    assert wrong.json()["detail"].startswith("That key didn't work: Orgo refused it.")
    assert "sk_live_wrong_key_0000" not in wrong.text

    saved = await desk.add_key()
    assert saved.status_code == 200, saved.text
    assert (saved.json()["provider"], saved.json()["keyHint"], saved.json()["status"]) == ("orgo", KEY[-4:], "ok")
    assert desk.orgo.called("GET", "/me") == 2
    assert [w["name"] for w in desk.orgo.workspaces] == ["production", "BotDesk"]  # made once
    assert KEY not in saved.text

    again = await desk.client.put(f"{desk.org}/computer-provider", json={"provider": "orgo"})  # the saved key
    assert again.status_code == 200
    assert desk.orgo.called("POST", "/workspaces") == 1  # found, not made again
    async with desk.app.state.sessionmaker() as db:
        row = await db.scalar(select(ComputerProvider).where(ComputerProvider.kind == "computer"))
        assert row is not None and KEY not in row.encrypted_secret
        assert row.config == {"workspace_id": "ws-2", "status": "ok"}


async def test_only_owners_and_admins_change_the_key(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    orgo = FakeOrgo()
    providers.answer(HOST, handler=orgo.handle)
    org_id, _, _ = await _team(client)  # Sara, a member, is signed in
    provider = f"/api/v1/orgs/{org_id}/computer-provider"
    assert (await client.put(provider, json={"provider": "orgo", "apiKey": KEY})).status_code == 403
    assert (await client.delete(provider)).status_code == 403
    assert (await client.get(provider)).status_code == 200  # any member sees whether there is one
    await _sign_in(client, "ali@acme.dev")
    assert (await client.put(provider, json={"provider": "orgo", "apiKey": KEY})).status_code == 200


async def test_removing_the_key_stops_the_bots_computers_first(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))

    assert (await desk.client.delete(f"{desk.org}/computer-provider")).status_code == 204

    assert desk.orgo.computers["pc-1"]["status"] == "stopped"
    row = await desk.row(bot_id)
    assert row is not None and row.status == "stopped"  # kept: the same key again finds it
    assert len(await desk.usage()) == 1
    assert (await desk.client.get(f"{desk.org}/computer-provider")).json()["provider"] is None


async def test_a_key_orgo_refuses_later_shows_as_refused(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    computer = f"{desk.org}/bots/{bot_id}/computer"
    desk.orgo.key = "sk_live_rotated_at_orgo"  # someone revoked it at Orgo

    assert (await desk.client.post(f"{computer}/start")).json()["status"] == "creating"
    await desk.computers.settle()

    failed = (await desk.client.get(computer)).json()
    assert failed["status"] == "error" and "refused the organization's key" in failed["error"]
    assert (await desk.client.get(f"{desk.org}/computer-provider")).json()["status"] == "key_refused"

    desk.orgo.key = KEY  # fixed: the next try is a new attempt, with a new idempotency key
    await desk.add_key()
    await desk.client.post(f"{computer}/start")
    await desk.computers.settle()
    assert (await desk.client.get(computer)).json()["status"] == "running"
    row = await desk.row(bot_id)
    assert row is not None and desk.orgo.idempotency_keys == [f"botdesk-{row.id}-2"]


# Browser or cloud


async def test_a_bot_goes_on_a_cloud_computer_only_with_the_organizations_key(desk: Desk) -> None:
    bot = (await desk.client.post(f"{desk.org}/bots", json={"name": "Coder"})).json()
    assert bot["computer"] == "browser"
    refused = await desk.client.patch(f"{desk.org}/bots/{bot['id']}", json={"computer": "cloud"})
    assert refused.status_code == 400
    assert refused.json() == {"detail": "Add an Orgo key in Settings → Computers first."}

    await desk.add_key()
    cloud = await desk.client.patch(f"{desk.org}/bots/{bot['id']}", json={"computer": "cloud"})
    assert cloud.json()["computer"] == "cloud"
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot["id"]))

    back = await desk.client.patch(f"{desk.org}/bots/{bot['id']}", json={"computer": "browser"})
    assert back.json()["computer"] == "browser"
    await desk.computers.settle()
    assert desk.orgo.computers["pc-1"]["status"] == "stopped"  # stopped, not deleted: its disk stays


# A computer's life


async def test_start_makes_the_computer_once_then_it_runs(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    computer = f"{desk.org}/bots/{bot_id}/computer"
    assert (await desk.client.get(computer)).json()["status"] == "none"

    desk.orgo.boot_gets = 2  # it takes a moment to boot
    started = await desk.client.post(f"{computer}/start")
    assert started.status_code == 200, started.text
    assert started.json()["status"] in ("creating", "starting")
    await desk.computers.settle()

    view = (await desk.client.get(computer)).json()
    assert (view["status"], view["name"], view["remoteId"], view["cpu"], view["ram"]) == (
        "running",
        "botdesk-coder",
        "pc-1",
        2,
        8,
    )
    assert view["orgoUrl"] == "https://www.orgo.ai/computers/pc-1"
    assert view["idleStopsAt"] is not None and view["apps"] == [] and view["previews"] == []
    _, _, body = next(call for call in desk.orgo.calls if call[:2] == ("POST", "/computers"))
    assert body == {"workspace_id": "ws-2", "name": "botdesk-coder", "os": "linux", "ram": 8, "cpu": 2}
    row = await desk.row(bot_id)
    assert row is not None and desk.orgo.idempotency_keys == [f"botdesk-{row.id}-1"]
    # Orgo's root password and the machine's raw address never leave the API.
    everything = (await desk.client.get(computer)).text
    assert ROOT_PASSWORD not in everything and RAW_ADDRESS not in everything

    assert (await desk.client.post(f"{computer}/start")).json()["status"] == "running"
    assert desk.orgo.made() == 1


async def test_stop_keeps_the_disk_records_the_time_and_start_starts_the_same_one(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    computer = f"{desk.org}/bots/{bot_id}/computer"
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))
    async with desk.app.state.sessionmaker() as db:  # it ran for two hours
        await db.execute(update(BotComputer).values(started_at=utcnow() - timedelta(hours=2)))
        await db.commit()

    stopped = await desk.client.post(f"{computer}/stop")
    assert stopped.json()["status"] == "stopped"
    assert desk.orgo.computers["pc-1"]["status"] == "stopped"
    (usage,) = await desk.usage()
    assert (usage.kind, usage.model_id, usage.run_id, str(usage.bot_id)) == (
        "computer",
        "orgo:linux-2cpu-8gb",
        None,
        bot_id,
    )
    assert usage.cost_usd == pytest.approx(0.11, abs=0.001)  # 2 h at $0.055
    assert (await desk.client.post(f"{computer}/stop")).json()["status"] == "stopped"  # nothing more
    assert len(await desk.usage()) == 1

    await desk.client.post(f"{computer}/start")
    await desk.computers.settle()
    assert (await desk.client.get(computer)).json()["status"] == "running"
    assert desk.orgo.made() == 1 and desk.orgo.called("POST", "/computers/pc-1/start") == 1


async def test_a_computer_gone_at_orgo_is_made_again_and_the_bot_is_told(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))
    await desk.client.post(f"{desk.org}/bots/{bot_id}/computer/stop")
    del desk.orgo.computers["pc-1"]  # deleted in Orgo's dashboard

    ready = await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))

    assert ready.remote_id == "pc-2"
    assert ready.note is not None and "files and apps from before aren't on it" in ready.note
    assert desk.orgo.made() == 2


async def test_a_creator_that_went_quiet_is_taken_over_with_the_same_key(desk: Desk) -> None:
    await desk.add_key()
    bot_id = uuid.UUID(await desk.cloud_bot())
    async with desk.app.state.sessionmaker() as db:
        row = BotComputer(org_id=desk.org_id, bot_id=bot_id, provider="orgo", name="botdesk-coder")
        row.created_at = utcnow() - timedelta(minutes=10)
        db.add(row)
        await db.commit()
        row_id = row.id

    ready = await desk.computers.ensure_running(desk.org_id, bot_id)

    assert ready.remote_id == "pc-1" and desk.orgo.idempotency_keys == [f"botdesk-{row_id}-1"]


@dataclass
class OwnDb:
    """A bot on a file database, so callers have connections of their own (as on Postgres; the
    in-memory test database is one shared connection)."""

    computers: Computers
    sessionmaker: async_sessionmaker[AsyncSession]
    org_id: uuid.UUID
    bot_id: uuid.UUID
    orgo: FakeOrgo


@pytest.fixture
async def own_db(tmp_path: Path) -> AsyncIterator[OwnDb]:
    settings = Settings(
        environment="test", database_url=f"sqlite+aiosqlite:///{tmp_path.as_posix()}/own.db", _env_file=None
    )
    engine = create_engine(settings.sqlalchemy_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = create_sessionmaker(engine)
    vault = CredentialVault.from_settings(settings)
    org = Organization(name="Acme", slug="acme")
    async with sessionmaker() as db:
        db.add(org)
        await db.flush()
        bot = Bot(org_id=org.id, name="Coder", handle="coder", computer="cloud")
        db.add(bot)
        db.add(
            ComputerProvider(
                org_id=org.id,
                kind="computer",
                provider="orgo",
                config={"workspace_id": "ws-1", "status": "ok"},
                encrypted_secret=vault.seal(json.dumps({"api_key": KEY})),
                secret_hint=KEY[-4:],
            )
        )
        await db.commit()
    orgo = FakeOrgo()
    computers = Computers(
        sessionmaker, settings, vault, transport=httpx.MockTransport(orgo.handle_slowly), poll_seconds=0.01
    )
    try:
        yield OwnDb(computers, sessionmaker, org.id, bot.id, orgo)
    finally:
        await engine.dispose()


async def test_one_creator_when_two_callers_race(own_db: OwnDb) -> None:
    """Two runs of a bot (or a run and a person) want its first computer at once: one makes it."""
    own_db.orgo.create_seconds = 0.2
    first, second = await asyncio.gather(
        own_db.computers.ensure_running(own_db.org_id, own_db.bot_id),
        own_db.computers.ensure_running(own_db.org_id, own_db.bot_id),
    )
    assert first.remote_id == second.remote_id == "pc-1"
    assert own_db.orgo.made() == 1


async def test_a_second_caller_waits_for_the_one_making_it(own_db: OwnDb) -> None:
    async with own_db.sessionmaker() as db:  # someone else is making it right now
        db.add(BotComputer(org_id=own_db.org_id, bot_id=own_db.bot_id, provider="orgo", name="botdesk-coder"))
        await db.commit()

    waiting = asyncio.create_task(own_db.computers.ensure_running(own_db.org_id, own_db.bot_id))
    await asyncio.sleep(0.1)
    assert not waiting.done() and own_db.orgo.made() == 0

    own_db.orgo.computers["pc-9"] = {"id": "pc-9", "name": "botdesk-coder", "status": "running", "gets": 0}
    async with own_db.sessionmaker() as db:  # ...and it's made
        await db.execute(update(BotComputer).values(remote_id="pc-9", status="starting"))
        await db.commit()
    assert (await asyncio.wait_for(waiting, 5)).remote_id == "pc-9"
    assert own_db.orgo.made() == 0


async def test_deleting_the_bot_deletes_its_computer_and_records_its_time(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))

    assert (await desk.client.delete(f"{desk.org}/bots/{bot_id}")).status_code == 204

    assert "pc-1" not in desk.orgo.computers
    assert await desk.row(bot_id) is None
    (usage,) = await desk.usage()
    assert usage.bot_id is None  # the bot is gone; the organization's spend stays right


async def test_deleting_a_computer_deletes_it_at_orgo(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))
    computer = f"{desk.org}/bots/{bot_id}/computer"

    assert (await desk.client.delete(computer)).status_code == 204

    assert desk.orgo.computers == {}
    assert (await desk.client.get(computer)).json()["status"] == "none"


# Watching and taking over


async def test_people_watch_the_screen_and_take_over(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    computer = f"{desk.org}/bots/{bot_id}/computer"
    not_yet = await desk.client.get(f"{computer}/screen")
    assert not_yet.status_code == 409 and not_yet.json()["detail"] == "The computer isn't running. Start it first."
    await desk.computers.ensure_running(desk.org_id, uuid.UUID(bot_id))

    screen = await desk.client.get(f"{computer}/screen")
    assert screen.status_code == 200
    assert (screen.headers["content-type"], screen.headers["cache-control"]) == ("image/jpeg", "private, no-store")
    assert screen.content.startswith(b"\xff\xd8")
    asked = next(call for call in desk.orgo.calls if call[1].endswith("/screenshot"))
    assert asked[0] == "GET"

    for move in (
        {"kind": "click", "x": 10, "y": 20},
        {"kind": "double_click", "x": 11, "y": 21},
        {"kind": "right_click", "x": 12, "y": 22},
        {"kind": "type", "text": "hello"},
        {"kind": "key", "key": "Enter"},
        {"kind": "key", "key": "ctrl+l"},
        {"kind": "scroll", "direction": "up", "x": 300, "y": 200},
        {"kind": "scroll", "direction": "down"},
    ):
        answer = await desk.client.post(f"{computer}/input", json=move)
        assert answer.status_code == 204, answer.text
    assert desk.orgo.actions == [
        ("click", {"x": 10, "y": 20, "button": "left", "double": False}),
        ("click", {"x": 11, "y": 21, "button": "left", "double": True}),
        ("click", {"x": 12, "y": 22, "button": "right", "double": False}),
        ("type", {"text": "hello"}),
        ("key", {"key": "Return"}),  # Orgo takes X11 key names
        ("key", {"key": "ctrl+l"}),
        ("scroll", {"x": 300, "y": 200, "direction": "up", "amount": 3}),
        ("scroll", {"x": 640, "y": 360, "direction": "down", "amount": 3}),
    ]


async def test_take_over_input_is_checked_and_needs_the_organization(desk: Desk) -> None:
    await desk.add_key()
    bot_id = await desk.cloud_bot()
    computer = f"{desk.org}/bots/{bot_id}/computer"
    for bad in (
        {"kind": "key", "key": "alt+F4"},  # only the allowed keys
        {"kind": "key", "key": "super"},
        {"kind": "click", "x": 10},
        {"kind": "type"},
        {"kind": "scroll"},
    ):
        assert (await desk.client.post(f"{computer}/input", json=bad)).status_code == 422, bad
    other = f"{desk.org}/bots/{uuid.uuid4()}/computer"
    assert (await desk.client.get(other)).status_code == 404
    assert (await desk.client.get(f"{other}/screen")).status_code == 404

    desk.client.cookies.clear()
    await sign_up(desk.client, name="Omar", email="omar@else.dev")  # in another organization
    assert (await desk.client.get(computer)).status_code == 404
    assert (await desk.client.post(f"{computer}/input", json={"kind": "type", "text": "x"})).status_code == 404


async def test_members_watch_and_take_over_like_editing_the_bot(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    orgo = FakeOrgo()
    providers.answer(HOST, handler=orgo.handle)
    org_id, _, _ = await _team(client)
    await _sign_in(client, "ali@acme.dev")
    org = f"/api/v1/orgs/{org_id}"
    await client.put(f"{org}/computer-provider", json={"provider": "orgo", "apiKey": KEY})
    bot = (await client.post(f"{org}/bots", json={"name": "Coder"})).json()
    await client.patch(f"{org}/bots/{bot['id']}", json={"computer": "cloud"})
    await _sign_in(client, "sara@acme.dev")  # a member
    computer = f"{org}/bots/{bot['id']}/computer"

    assert (await client.post(f"{computer}/start")).status_code == 200
    await asyncio.sleep(0.05)
    for _ in range(50):
        if (await client.get(computer)).json()["status"] == "running":
            break
        await asyncio.sleep(0.05)
    assert (await client.get(f"{computer}/screen")).status_code == 200
    assert (await client.post(f"{computer}/input", json={"kind": "type", "text": "hi"})).status_code == 204
    assert (await client.post(f"{computer}/stop")).json()["status"] == "stopped"


def test_settings_default_to_orgos_list_price_and_a_fake_only_outside_production() -> None:
    assert (TEST_SETTINGS.computer_idle_minutes, TEST_SETTINGS.orgo_price_per_hour) == (20, 0.055)
    fake = "http://127.0.0.1:9200/api"
    assert Settings(environment="test", orgo_base_url=fake, _env_file=None).orgo_api_url == fake
    assert Settings(environment="development", orgo_base_url=fake, _env_file=None).orgo_api_url == fake
    production = Settings(environment="production", orgo_base_url=fake, _env_file=None)
    assert production.orgo_api_url == "https://www.orgo.ai/api"

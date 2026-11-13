"""Run events on real Postgres: a chat's event ids become visible in order, so a stream that
has seen id N never misses a smaller id committed later."""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import run_event_service
from tests.conftest import Postgres, sign_up


async def _two_chats(pg: Postgres) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """(org id, a chat, another chat)"""
    me = await sign_up(pg.client)
    org_id = me["organizations"][0]["id"]
    org = f"/api/v1/orgs/{org_id}"
    chats = []
    for name in ("Scout", "Inbox Manager"):
        bot = (await pg.client.post(f"{org}/bots", json={"name": name})).json()
        chats.append((await pg.client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()["id"])
    return uuid.UUID(org_id), uuid.UUID(chats[0]), uuid.UUID(chats[1])


def _add(db: AsyncSession, org_id: uuid.UUID, thread_id: uuid.UUID) -> None:
    run_event_service.add_event(db, org_id=org_id, thread_id=thread_id, run_id=None, kind="message_saved", data={})


async def test_a_chats_events_commit_in_id_order(pg: Postgres) -> None:
    org_id, chat, other_chat = await _two_chats(pg)
    sessionmaker = pg.runs.sessionmaker

    async with sessionmaker() as first:
        _add(first, org_id, chat)
        await first.flush()  # has its id, not committed yet

        connected = asyncio.Event()

        async def second_writer() -> None:
            async with sessionmaker() as second:
                await second.connection()  # connecting to a remote server is slow: not what's timed
                connected.set()
                _add(second, org_id, chat)
                await second.commit()

        second = asyncio.create_task(second_writer())
        await asyncio.wait_for(connected.wait(), 30)
        await asyncio.sleep(2)
        assert not second.done(), "a second writer to the same chat must wait for the first to commit"

        # Another chat isn't held up.
        async with sessionmaker() as elsewhere:
            _add(elsewhere, org_id, other_chat)
            await asyncio.wait_for(elsewhere.commit(), 5)

        await first.commit()
    await asyncio.wait_for(second, 5)

    async with sessionmaker() as db:
        ids = [event.id for event in await run_event_service.events_after(db, thread_id=chat, after_id=0)]
    assert len(ids) == 2 and ids == sorted(ids)


def test_a_chats_lock_key_is_a_signed_64_bit_number() -> None:
    key = run_event_service.thread_lock_key(uuid.UUID("ffffffff-ffff-ffff-0000-000000000000"))
    assert key == -1
    assert run_event_service.thread_lock_key(uuid.UUID(int=1 << 64)) == 1

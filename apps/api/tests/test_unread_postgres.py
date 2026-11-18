"""Unread counts and group changes on real Postgres (timestamps with time zones, DELETE row
counts). Skipped without TEST_DATABASE_URL; the full cases are in `test_unread.py` and
`test_group_management.py`."""

import asyncio
import uuid

from sqlalchemy import func, select

from src.core.database import utcnow
from src.models import Message, ThreadParticipant
from tests.conftest import Postgres, sign_up


async def test_unread_counts_marks_read_and_removing_the_lead(pg: Postgres) -> None:
    me = await sign_up(pg.client)
    org_id = me["organizations"][0]["id"]
    org = f"/api/v1/orgs/{org_id}"
    chief = (await pg.client.post(f"{org}/bots", json={"name": "Chief"})).json()
    scout = (await pg.client.post(f"{org}/bots", json={"name": "Scout"})).json()
    group = (
        await pg.client.post(f"{org}/threads/groups", json={"title": "Launch", "botIds": [chief["id"], scout["id"]]})
    ).json()
    path = f"{org}/threads/{group['id']}"

    await pg.client.post(f"{path}/messages", json={"text": "Hi"})
    async with pg.runs.sessionmaker() as db:
        db.add(
            Message(
                org_id=uuid.UUID(org_id),
                thread_id=uuid.UUID(group["id"]),
                author_type="bot",
                author_id=uuid.UUID(chief["id"]),
                parts=[{"type": "text", "text": "Hello"}],
                created_at=utcnow(),
            )
        )
        await db.commit()
    assert (await pg.client.get(path)).json()["unread"] == 1
    assert (await pg.client.post(f"{path}/read")).status_code == 204
    assert (await pg.client.get(path)).json()["unread"] == 0

    removed = await pg.client.delete(f"{path}/participants/bot/{chief['id']}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["leadBotId"] is None
    renamed = await pg.client.patch(path, json={"title": "Launch week"})
    assert renamed.json()["title"] == "Launch week"


async def test_changes_to_a_group_at_the_same_moment_wait_for_each_other(pg: Postgres) -> None:
    """The group's row is locked while it changes, so two requests at once can't both pass a check
    the other is about to break: adding the same bot twice puts it in once (no duplicate-key
    error), and two removals at once never leave a group with nobody in it."""
    me = await sign_up(pg.client, name="Sara", email="sara@acme.dev")
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    invite = await pg.client.post(f"{org}/invitations", json={"email": "lina@acme.dev", "role": "admin"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    pg.client.cookies.clear()
    lina = (await sign_up(pg.client, name="Lina", email="lina@acme.dev"))["user"]["id"]
    assert (await pg.client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
    pg.client.cookies.clear()
    signed_in = await pg.client.post(
        "/api/v1/auth/sign-in", json={"email": "sara@acme.dev", "password": "correct-horse-battery"}
    )
    assert signed_in.status_code == 200
    chief = (await pg.client.post(f"{org}/bots", json={"name": "Chief"})).json()
    scout = (await pg.client.post(f"{org}/bots", json={"name": "Scout"})).json()
    group = (
        await pg.client.post(
            f"{org}/threads/groups", json={"title": "Launch", "botIds": [chief["id"]], "userIds": [lina]}
        )
    ).json()
    path = f"{org}/threads/{group['id']}"

    added = await asyncio.gather(
        *(pg.client.post(f"{path}/participants", json={"botIds": [scout["id"]]}) for _ in range(2))
    )
    assert [r.status_code for r in added] == [200, 200]
    bots = [p for p in (await pg.client.get(path)).json()["participants"] if p["type"] == "bot"]
    assert sorted(p["id"] for p in bots) == sorted([chief["id"], scout["id"]])

    removed = await asyncio.gather(
        pg.client.delete(f"{path}/participants/user/{lina}"),
        pg.client.delete(f"{path}/participants/user/{me['user']['id']}"),
    )
    # One wins; the other finds the last person (400), or, had Sara's own removal gone first, a
    # group she's no longer in (404).
    assert sorted(r.status_code for r in removed) in ([200, 400], [200, 404])
    async with pg.runs.sessionmaker() as db:
        people = await db.scalar(
            select(func.count())
            .select_from(ThreadParticipant)
            .where(ThreadParticipant.thread_id == uuid.UUID(group["id"]), ThreadParticipant.participant_type == "user")
        )
    assert people == 1


async def test_deleting_a_bot_while_its_group_changes_never_deadlocks(pg: Postgres) -> None:
    """Taking the lead bot out of a group while it's being deleted: both lock the group's row
    before changing who's in it (or its lead), so one waits for the other instead of each holding
    what the other needs. Before, one of them failed with a 500 (a deadlock)."""
    me = await sign_up(pg.client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    for attempt in range(3):
        lead = (await pg.client.post(f"{org}/bots", json={"name": f"Lead {attempt}"})).json()
        other = (await pg.client.post(f"{org}/bots", json={"name": f"Other {attempt}"})).json()
        body = {"title": "Launch", "botIds": [lead["id"], other["id"]]}
        group = (await pg.client.post(f"{org}/threads/groups", json=body)).json()
        removed, deleted = await asyncio.gather(
            pg.client.delete(f"{org}/threads/{group['id']}/participants/bot/{lead['id']}"),
            pg.client.delete(f"{org}/bots/{lead['id']}"),
        )
        # The removal finds the bot already gone (404) if the delete went first.
        assert (removed.status_code in (200, 404), deleted.status_code) == (True, 204), removed.text

"""Unread counts and group changes on real Postgres (timestamps with time zones, DELETE row
counts). Skipped without TEST_DATABASE_URL; the full cases are in `test_unread.py` and
`test_group_management.py`."""

import uuid

from src.core.database import utcnow
from src.models import Message
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

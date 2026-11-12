"""Chats: your DM with a bot, group chats, and their messages."""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from tests.conftest import sign_up


async def _org_with_bot(client: httpx.AsyncClient) -> tuple[str, dict[str, Any]]:
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Inbox Manager"})).json()
    return org, bot


async def test_opening_a_bot_chat_twice_gives_the_same_chat(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    first = await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})
    second = await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})
    assert first.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["kind"] == "dm"
    assert first.json()["title"] == "Inbox Manager"
    assert {p["type"] for p in first.json()["participants"]} == {"user", "bot"}


async def test_messages_are_saved_and_listed_oldest_first(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    messages = f"{org}/threads/{thread['id']}/messages"

    for text in ("First", "  Second  "):
        response = await client.post(messages, json={"text": text})
        assert response.status_code == 201
    listed = (await client.get(messages)).json()
    assert [m["parts"][0]["text"] for m in listed] == ["First", "Second"]
    assert listed[0]["author"]["type"] == "user"

    threads = (await client.get(f"{org}/threads")).json()
    assert threads[0]["lastMessagePreview"] == "Second"


async def test_older_messages_page_with_before(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    messages = f"{org}/threads/{thread['id']}/messages"
    for n in range(5):
        await client.post(messages, json={"text": f"m{n}"})

    latest = (await client.get(messages, params={"limit": 2})).json()
    assert [m["parts"][0]["text"] for m in latest] == ["m3", "m4"]
    older = (await client.get(messages, params={"limit": 2, "before": latest[0]["createdAt"]})).json()
    assert [m["parts"][0]["text"] for m in older] == ["m1", "m2"]

    # The same moment written in another time zone pages the same way.
    in_karachi = datetime.fromisoformat(latest[0]["createdAt"]).astimezone(timezone(timedelta(hours=5)))
    same = (await client.get(messages, params={"limit": 2, "before": in_karachi.isoformat()})).json()
    assert [m["parts"][0]["text"] for m in same] == ["m1", "m2"]


async def test_times_are_utc_with_an_offset(client: httpx.AsyncClient) -> None:
    """SQLite forgets time zones; the API must still say "+00:00" (or "Z") everywhere."""
    org, bot = await _org_with_bot(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Hi"})

    listed = (await client.get(f"{org}/threads")).json()[0]
    message = (await client.get(f"{org}/threads/{thread['id']}/messages")).json()[0]
    for moment in (listed["lastMessageAt"], message["createdAt"]):
        assert datetime.fromisoformat(moment).utcoffset() == timedelta(0), moment


async def test_empty_messages_are_refused(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    assert (await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": ""})).status_code == 422


async def test_your_bot_chats_are_private_to_you(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    org_id = org.rsplit("/", 1)[1]
    alis_chat = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()

    # Sara joins the same organization.
    invite = await client.post(f"{org}/invitations", json={"email": "sara@acme.dev"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")
    await client.post("/api/v1/invitations/accept", json={"token": token})

    assert (await client.get(f"/api/v1/orgs/{org_id}/threads")).json() == []
    assert (await client.get(f"/api/v1/orgs/{org_id}/threads/{alis_chat['id']}")).status_code == 404
    saras_chat = (await client.post(f"/api/v1/orgs/{org_id}/threads/dm", json={"botId": bot["id"]})).json()
    assert saras_chat["id"] != alis_chat["id"]


async def test_group_chats_include_who_you_pick(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    response = await client.post(f"{org}/threads/groups", json={"title": "Launch crew", "botIds": [bot["id"]]})
    assert response.status_code == 201
    group = response.json()
    assert (group["kind"], group["title"]) == ("group", "Launch crew")
    assert [p["type"] for p in group["participants"]].count("bot") == 1


async def test_groups_cannot_include_outsiders(client: httpx.AsyncClient) -> None:
    org, _ = await _org_with_bot(client)
    stranger = "00000000-0000-0000-0000-000000000001"
    response = await client.post(f"{org}/threads/groups", json={"title": "X", "userIds": [stranger]})
    assert response.status_code == 404


async def test_removing_a_bot_removes_its_chats(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    await client.delete(f"{org}/bots/{bot['id']}")
    assert (await client.get(f"{org}/threads/{thread['id']}")).status_code == 404

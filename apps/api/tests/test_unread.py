"""Unread counts in the chat list: per person, the messages after they last read the chat that
someone else (a person, a bot or the system) wrote. Opening a chat marks it read."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from src.core.database import utcnow
from src.models import Message
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up, sql_statements


@dataclass
class Chat:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    bot: dict[str, Any]

    async def unread(self) -> dict[str, int]:
        threads = (await self.client.get(f"{self.org}/threads")).json()
        return {t["id"]: t["unread"] for t in threads}

    async def say(self, thread: dict[str, Any], text: str) -> None:
        response = await self.client.post(f"{self.org}/threads/{thread['id']}/messages", json={"text": text})
        assert response.status_code == 201, response.text

    async def bot_says(self, thread: dict[str, Any], text: str) -> None:
        """A bot's reply, saved as a run saves it."""
        async with self.app.state.sessionmaker() as db:
            org_id = uuid.UUID(self.org.rsplit("/", 1)[1])
            db.add(
                Message(
                    org_id=org_id,
                    thread_id=uuid.UUID(thread["id"]),
                    author_type="bot",
                    author_id=uuid.UUID(self.bot["id"]),
                    parts=[{"type": "text", "text": text}],
                    created_at=utcnow(),
                )
            )
            await db.commit()

    async def read(self, thread: dict[str, Any]) -> httpx.Response:
        return await self.client.post(f"{self.org}/threads/{thread['id']}/read")


@pytest.fixture
async def chat(providers: FakeProviders) -> AsyncIterator[Chat]:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        me = await sign_up(client, name="Sara Khan", email="sara@acme.dev")
        org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
        bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
        yield Chat(app, client, org, bot)


async def _join(chat: Chat, name: str, email: str) -> None:
    """Invite someone (as the signed-in owner); they sign up and accept, and end signed in."""
    invite = await chat.client.post(f"{chat.org}/invitations", json={"email": email, "role": "member"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    chat.client.cookies.clear()
    await sign_up(chat.client, name=name, email=email)
    assert (await chat.client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200


async def _sign_in(client: httpx.AsyncClient, email: str) -> None:
    client.cookies.clear()
    response = await client.post("/api/v1/auth/sign-in", json={"email": email, "password": "correct-horse-battery"})
    assert response.status_code == 200


async def test_a_new_chat_has_nothing_unread_and_your_own_messages_never_count(chat: Chat) -> None:
    dm = (await chat.client.post(f"{chat.org}/threads/dm", json={"botId": chat.bot["id"]})).json()
    assert dm["unread"] == 0
    await chat.say(dm, "Hi")
    await chat.say(dm, "Anyone there?")
    assert (await chat.unread())[dm["id"]] == 0


async def test_bot_replies_count_until_you_read_the_chat(chat: Chat) -> None:
    dm = (await chat.client.post(f"{chat.org}/threads/dm", json={"botId": chat.bot["id"]})).json()
    await chat.say(dm, "Find me leads")
    await chat.bot_says(dm, "On it.")
    await chat.bot_says(dm, "Found 3.")
    assert (await chat.unread())[dm["id"]] == 2
    assert (await chat.client.get(f"{chat.org}/threads/{dm['id']}")).json()["unread"] == 2

    response = await chat.read(dm)
    assert response.status_code == 204
    assert (await chat.unread())[dm["id"]] == 0
    await chat.bot_says(dm, "One more.")
    assert (await chat.unread())[dm["id"]] == 1


async def test_in_a_group_each_person_has_their_own_count(chat: Chat) -> None:
    org_id = chat.org.rsplit("/", 1)[1]
    await _join(chat, "Omar", "omar@acme.dev")
    await _sign_in(chat.client, "sara@acme.dev")
    members = (await chat.client.get(f"{chat.org}/members")).json()
    group = (
        await chat.client.post(
            f"{chat.org}/threads/groups",
            json={"title": "Launch", "botIds": [chat.bot["id"]], "userIds": [m["id"] for m in members]},
        )
    ).json()
    await chat.say(group, "Morning all")  # Sara's
    await chat.bot_says(group, "Morning!")
    assert (await chat.unread())[group["id"]] == 1  # Sara: only the bot's

    await _sign_in(chat.client, "omar@acme.dev")
    assert (await chat.client.get(f"/api/v1/orgs/{org_id}/threads")).json()[0]["unread"] == 2
    await chat.read(group)
    assert (await chat.unread())[group["id"]] == 0
    await _sign_in(chat.client, "sara@acme.dev")
    assert (await chat.unread())[group["id"]] == 1  # Omar reading it doesn't read it for Sara


async def test_you_can_only_mark_your_own_chats_read(chat: Chat) -> None:
    dm = (await chat.client.post(f"{chat.org}/threads/dm", json={"botId": chat.bot["id"]})).json()
    await _join(chat, "Omar", "omar@acme.dev")
    assert (await chat.read(dm)).status_code == 404


async def test_the_chat_list_counts_unread_in_one_query_however_many_chats(chat: Chat) -> None:
    async def statements() -> int:
        async with sql_statements(chat.app) as seen:
            assert (await chat.client.get(f"{chat.org}/threads")).status_code == 200
        return len(seen)

    dm = (await chat.client.post(f"{chat.org}/threads/dm", json={"botId": chat.bot["id"]})).json()
    await chat.bot_says(dm, "Hello")
    one_chat = await statements()
    for n in range(3):
        group = (
            await chat.client.post(f"{chat.org}/threads/groups", json={"title": f"G{n}", "botIds": [chat.bot["id"]]})
        ).json()
        await chat.bot_says(group, "Hi")
    assert await statements() == one_chat
    assert set((await chat.unread()).values()) == {1}

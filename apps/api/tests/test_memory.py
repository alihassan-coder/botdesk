"""The memory screen: see, search, correct and forget what a bot remembers.

Memories live in mem0, so these tests swap in `FakeMemoryStore`, which stores records the way
`Mem0Memory` saves them (org, bot, member) and filters like mem0 does. The rules on top (who
sees and changes what) are the real ones from `services/memory_service.py`.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from src.core.config import Settings
from src.runtime.memory import SHARED, MemoryRecord, MemoryScope, memory_off_reason, org_key
from tests.conftest import TEST_SETTINGS, FakeProviders, Postgres, api_client
from tests.test_members import _as, _invite, _sign_in
from tests.test_runs_postgres import ScriptedModel, _bot_chat, _send, use_model

ORGS = "/api/v1/orgs"
START = datetime(2026, 11, 1, tzinfo=UTC)


class FakeMemoryStore:
    """Memories in a list, filtered by org, bot and member the way mem0 is asked to."""

    def __init__(self, *, leaky: bool = False) -> None:
        self.records: list[MemoryRecord] = []
        self.recalled: list[MemoryScope] = []
        self.remembered: list[MemoryScope] = []
        self.leaky = leaky  # ignores the filters, to prove the service checks scope itself
        self.broken = False

    @property
    def off_reason(self) -> str | None:
        return None

    def add(self, org_id: str, bot_id: str, member: str, text: str) -> str:
        memory_id = str(uuid.uuid4())
        when = START + timedelta(minutes=len(self.records))
        self.records.append(MemoryRecord(memory_id, text, org_key(uuid.UUID(org_id)), bot_id, member, when, when))
        return memory_id

    def _check(self) -> None:
        if self.broken:
            raise ConnectionError("pgvector is down")

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        self.recalled.append(scope)
        return []

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        self.remembered.append(scope)

    async def list_memories(
        self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], *, query: str = "", limit: int
    ) -> list[MemoryRecord]:
        self._check()
        found = [
            r
            for r in self.records
            if self.leaky or (r.user_id == org_key(org_id) and r.agent_id == str(bot_id) and r.member in members)
        ]
        if query:
            found = [r for r in found if query.lower() in r.text.lower()]
        return found[:limit]

    async def get(self, memory_id: str) -> MemoryRecord | None:
        self._check()
        return next((r for r in self.records if r.id == memory_id), None)

    async def update(self, memory_id: str, text: str) -> None:
        self._check()
        self.records = [
            replace(r, text=text, updated_at=START + timedelta(days=1)) if r.id == memory_id else r
            for r in self.records
        ]

    async def delete(self, memory_id: str) -> None:
        self._check()
        self.records = [r for r in self.records if r.id != memory_id]

    async def delete_all(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        self._check()
        self.records = [r for r in self.records if not (r.user_id == org_key(org_id) and r.agent_id == str(bot_id))]

    def texts(self) -> set[str]:
        return {r.text for r in self.records}


class Team:
    """Ali owns Acme and Sara is a member; both use the Scout bot. Elsewhere, Omar owns Globex."""

    def __init__(self, client: httpx.AsyncClient, store: FakeMemoryStore) -> None:
        self.client = client
        self.store = store
        self.org = self.bot = self.ali = self.sara = self.other_org = self.other_bot = ""

    @property
    def memories(self) -> str:
        return f"{ORGS}/{self.org}/bots/{self.bot}/memories"

    async def texts_seen(self, query: str = "") -> list[str]:
        response = await self.client.get(self.memories, params={"q": query} if query else None)
        assert response.status_code == 200, response.text
        return [m["text"] for m in response.json()]


@pytest.fixture
async def team(providers: FakeProviders) -> AsyncIterator[Team]:
    store = FakeMemoryStore()
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        app.state.runs.memory = store
        t = Team(client, store)
        omar = await _as(client, "Omar", "omar@globex.dev")
        t.other_org = omar["organizations"][0]["id"]
        t.other_bot = (await client.post(f"{ORGS}/{t.other_org}/bots", json={"name": "Scout"})).json()["id"]
        ali = await _as(client, "Ali", "ali@acme.dev")
        t.ali, t.org = ali["user"]["id"], ali["organizations"][0]["id"]
        t.bot = (await client.post(f"{ORGS}/{t.org}/bots", json={"name": "Scout"})).json()["id"]
        token = await _invite(client, t.org, "sara@acme.dev")
        sara = await _as(client, "Sara", "sara@acme.dev")
        t.sara = sara["user"]["id"]
        assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
        yield t


def _seed(t: Team) -> dict[str, str]:
    other_bot_here = str(uuid.uuid4())
    return {
        "shared": t.store.add(t.org, t.bot, SHARED, "The team ships on Fridays"),
        "sara": t.store.add(t.org, t.bot, t.sara, "Sara likes short answers"),
        "ali": t.store.add(t.org, t.bot, t.ali, "Ali is vegetarian"),
        "other bot": t.store.add(t.org, other_bot_here, SHARED, "Another bot's memory"),
        "other org": t.store.add(t.other_org, t.other_bot, SHARED, "Globex's secret plan"),
    }


async def test_you_see_the_bots_shared_memories_and_your_own_dm_ones_newest_first(team: Team) -> None:
    _seed(team)  # Sara is signed in
    response = await team.client.get(team.memories)
    assert response.status_code == 200
    seen = [(m["text"], m["scope"]) for m in response.json()]
    assert seen == [("Sara likes short answers", "you"), ("The team ships on Fridays", "bot")]
    assert set(response.json()[0]) == {"id", "text", "createdAt", "updatedAt", "scope"}


async def test_owners_do_not_see_another_members_dm_memories_either(team: Team) -> None:
    _seed(team)
    await _sign_in(team.client, "ali@acme.dev")
    assert await team.texts_seen() == ["Ali is vegetarian", "The team ships on Fridays"]


async def test_scope_is_checked_even_if_the_store_returns_too_much(team: Team) -> None:
    _seed(team)
    team.store.leaky = True
    assert await team.texts_seen() == ["Sara likes short answers", "The team ships on Fridays"]


async def test_search_finds_matching_memories(team: Team) -> None:
    _seed(team)
    assert await team.texts_seen("fridays") == ["The team ships on Fridays"]
    assert await team.texts_seen("vegetarian") == []  # Ali's DM memory stays Ali's


async def test_another_organizations_bot_is_not_found(team: Team) -> None:
    ids = _seed(team)
    await _sign_in(team.client, "omar@globex.dev")
    for url in (
        f"{ORGS}/{team.other_org}/bots/{team.bot}/memories",  # Acme's bot through Globex's URL
        f"{ORGS}/{team.org}/bots/{team.bot}/memories",  # Acme itself
    ):
        assert (await team.client.get(url)).status_code == 404
    # Globex's own bot can't reach Acme's memories by id.
    acme_memory = f"{ORGS}/{team.other_org}/bots/{team.other_bot}/memories/{ids['shared']}"
    assert (await team.client.delete(acme_memory)).status_code == 404
    assert "The team ships on Fridays" in team.store.texts()


async def test_members_forget_only_their_own_dm_memories(team: Team) -> None:
    ids = _seed(team)
    assert (await team.client.delete(f"{team.memories}/{ids['sara']}")).status_code == 204
    shared = await team.client.delete(f"{team.memories}/{ids['shared']}")
    assert shared.status_code == 403
    assert shared.json()["detail"] == "Only owners and admins can change what a bot learned in group chats."
    assert (await team.client.delete(f"{team.memories}/{ids['ali']}")).status_code == 404  # not even "forbidden"
    assert (await team.client.delete(f"{team.memories}/{ids['other bot']}")).status_code == 404
    assert team.store.texts() == {
        "The team ships on Fridays",
        "Ali is vegetarian",
        "Another bot's memory",
        "Globex's secret plan",
    }


async def test_owners_and_admins_forget_any_memory_of_the_bot(team: Team) -> None:
    ids = _seed(team)
    await _sign_in(team.client, "ali@acme.dev")
    assert (await team.client.delete(f"{team.memories}/{ids['shared']}")).status_code == 204
    assert (await team.client.delete(f"{team.memories}/{ids['sara']}")).status_code == 204
    assert (await team.client.delete(f"{team.memories}/{ids['other org']}")).status_code == 404
    assert (await team.client.delete(f"{team.memories}/{uuid.uuid4()}")).status_code == 404
    assert team.store.texts() == {"Ali is vegetarian", "Another bot's memory", "Globex's secret plan"}


async def test_forget_everything_takes_an_owner_or_admin_and_touches_only_that_bot(team: Team) -> None:
    _seed(team)
    refused = await team.client.delete(team.memories)
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Only owners and admins can make a bot forget everything."

    await _sign_in(team.client, "ali@acme.dev")
    assert (await team.client.delete(team.memories)).status_code == 204
    assert team.store.texts() == {"Another bot's memory", "Globex's secret plan"}


async def test_correct_a_memory(team: Team) -> None:
    ids = _seed(team)
    response = await team.client.patch(f"{team.memories}/{ids['sara']}", json={"text": "  Sara likes bullet points "})
    assert response.status_code == 200, response.text
    assert (response.json()["text"], response.json()["scope"]) == ("Sara likes bullet points", "you")
    assert response.json()["updatedAt"] != response.json()["createdAt"]

    assert (await team.client.patch(f"{team.memories}/{ids['shared']}", json={"text": "x"})).status_code == 403
    assert (await team.client.patch(f"{team.memories}/{ids['sara']}", json={"text": "  "})).status_code == 422


async def test_a_failing_memory_store_answers_503_in_plain_words(team: Team) -> None:
    team.store.broken = True
    response = await team.client.get(team.memories)
    assert response.status_code == 503
    assert response.json()["detail"] == "Memory isn't answering right now. Try again in a moment."


async def test_status_says_on_when_the_store_works(team: Team) -> None:
    response = await team.client.get(f"{ORGS}/{team.org}/memory/status")
    assert response.json() == {"enabled": True, "reason": None}


async def test_with_memory_off_everything_is_empty_never_an_error(client: httpx.AsyncClient) -> None:
    me = await _as(client, "Ali", "ali@acme.dev")
    org = f"{ORGS}/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()["id"]

    status = (await client.get(f"{org}/memory/status")).json()
    assert status["enabled"] is False
    assert "MEMORY_ENABLED" in status["reason"]
    assert (await client.get(f"{org}/bots/{bot}/memories", params={"q": "anything"})).json() == []
    assert (await client.delete(f"{org}/bots/{bot}/memories")).status_code == 204


async def test_strangers_cannot_read_an_organizations_memory_status(client: httpx.AsyncClient) -> None:
    me = await _as(client, "Ali", "ali@acme.dev")
    await _as(client, "Omar", "omar@globex.dev")
    assert (await client.get(f"{ORGS}/{me['organizations'][0]['id']}/memory/status")).status_code == 404


async def test_bots_have_memory_on_until_someone_turns_it_off(client: httpx.AsyncClient) -> None:
    me = await _as(client, "Ali", "ali@acme.dev")
    bots = f"{ORGS}/{me['organizations'][0]['id']}/bots"
    bot = (await client.post(bots, json={"name": "Scout"})).json()
    assert bot["memoryEnabled"] is True
    updated = (await client.patch(f"{bots}/{bot['id']}", json={"memoryEnabled": False})).json()
    assert (updated["memoryEnabled"], updated["name"]) == (False, "Scout")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"memory_enabled": False}, "MEMORY_ENABLED"),
        ({"memory_enabled": True}, "Postgres"),
        ({"memory_enabled": True, "database_url": "postgresql://u:p@db/x"}, "OPENAI_API_KEY"),
        ({"memory_enabled": True, "database_url": "postgresql://u:p@db/x", "openai_api_key": SecretStr("sk")}, None),
    ],
)
def test_the_off_reason_names_what_is_missing(changes: dict[str, Any], reason: str | None) -> None:
    settings = Settings(**{"environment": "test", "database_url": "sqlite+aiosqlite://", **changes}, _env_file=None)
    found = memory_off_reason(settings)
    assert (found is None) if reason is None else (reason in str(found))


async def test_a_bot_with_memory_off_neither_recalls_nor_remembers(pg: Postgres) -> None:
    store = FakeMemoryStore()
    pg.runs.memory = store
    use_model(pg, ScriptedModel(tokens=["Sure."]))
    org, thread = await _bot_chat(pg.client)
    bot_id = (await pg.client.get(f"{org}/bots")).json()[0]["id"]

    await _send(pg.client, thread, "Hi")
    await pg.runs.wait_until_idle()
    assert (len(store.recalled), len(store.remembered)) == (1, 1)

    await pg.client.patch(f"{org}/bots/{bot_id}", json={"memoryEnabled": False})
    await _send(pg.client, thread, "Hi again")
    await pg.runs.wait_until_idle()
    assert (len(store.recalled), len(store.remembered)) == (1, 1)

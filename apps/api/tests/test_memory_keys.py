"""The organization's memory key (Settings → Memory): set and checked live, owners and admins only,
and each organization's memory goes through its own key (`OrgMemory`)."""

import uuid
from typing import Any

import httpx

from src.core.config import Settings
from src.core.database import Base, create_engine, create_sessionmaker
from src.models import MemoryKey, Organization
from src.runtime.memory import MemoryProvider, MemoryScope, MemoryService, NoMemory
from src.services.credential_vault import CredentialVault
from src.services.memory_router import OrgMemory
from tests.conftest import TEST_SETTINGS, FakeProviders, sign_up
from tests.test_providers import OPENAI_KEY, openai_answer


async def test_an_admin_sets_a_memory_key_checked_live(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    assert (await client.get(f"{org}/memory-key")).json() == {"provider": None, "keyHint": None, "checkedAt": None}

    providers.answer("api.openai.com", handler=openai_answer)
    wrong = await client.put(f"{org}/memory-key", json={"provider": "openai", "apiKey": "sk-wrong-key-123"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"].startswith("That key didn't work")

    saved = await client.put(f"{org}/memory-key", json={"provider": "openai", "apiKey": OPENAI_KEY})
    assert saved.status_code == 200, saved.text
    assert (saved.json()["provider"], saved.json()["keyHint"]) == ("openai", "abcd")
    assert OPENAI_KEY not in saved.text

    assert (await client.delete(f"{org}/memory-key")).status_code == 204
    assert (await client.get(f"{org}/memory-key")).json()["provider"] is None


async def test_members_see_the_memory_key_but_cant_change_it(client: httpx.AsyncClient) -> None:
    owner = await sign_up(client)
    org = f"/api/v1/orgs/{owner['organizations'][0]['id']}"
    invite = await client.post(f"{org}/invitations", json={"email": "sara@acme.dev", "role": "member"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200

    assert (await client.get(f"{org}/memory-key")).status_code == 200
    put = await client.put(f"{org}/memory-key", json={"provider": "gemini", "apiKey": "AIza-test-key-0000"})
    assert put.status_code == 403
    assert (await client.delete(f"{org}/memory-key")).status_code == 403


class Remembers:
    """A memory backend that only says which key built it."""

    def __init__(self, label: str) -> None:
        self.label = label

    async def off_reason_for(self, org_id: uuid.UUID) -> str | None:
        return None

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        return [self.label]

    def __getattr__(self, name: str) -> Any:  # the rest of MemoryService isn't needed here
        raise AttributeError(name)


async def test_each_organization_remembers_with_its_own_key() -> None:
    engine = create_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = create_sessionmaker(engine)
    vault = CredentialVault.from_settings(TEST_SETTINGS)
    postgres = Settings(environment="test", database_url="postgresql://db/botdesk", _env_file=None)
    built: list[tuple[MemoryProvider, str]] = []

    def build(settings: Settings, provider: MemoryProvider, key: str) -> MemoryService:
        built.append((provider, key))
        return Remembers(f"{provider}:{key}")

    server = NoMemory("Add a memory key in Settings → Memory.")
    memory = OrgMemory(server, sessionmaker, postgres, vault, build=build)
    async with sessionmaker() as db:
        with_key = Organization(name="Acme", slug="acme")
        without_key = Organization(name="Globex", slug="globex")
        db.add_all([with_key, without_key])
        await db.flush()
        key = MemoryKey(org_id=with_key.id, provider="gemini", encrypted_key=vault.seal("AIza-one"), key_hint="-one")
        db.add(key)
        await db.commit()

    scope = MemoryScope(org_id=with_key.id, bot_id=uuid.uuid4(), member_id=None)
    assert await memory.recall(scope, "lunch") == ["gemini:AIza-one"]
    assert await memory.recall(scope, "again") == ["gemini:AIza-one"]
    assert built == [("gemini", "AIza-one")]  # built once, then kept

    async with sessionmaker() as db:
        changed = await db.get(MemoryKey, key.id)
        assert changed is not None
        changed.provider, changed.encrypted_key = "openai", vault.seal("sk-two")
        await db.commit()
    memory.forget(with_key.id)
    assert await memory.recall(scope, "lunch") == ["openai:sk-two"]  # a new key is used at once

    assert await memory.off_reason_for(without_key.id) == "Add a memory key in Settings → Memory."
    other = MemoryScope(org_id=without_key.id, bot_id=uuid.uuid4(), member_id=None)
    assert await memory.recall(other, "x") == []
    await engine.dispose()

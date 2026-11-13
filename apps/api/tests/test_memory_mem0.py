"""`Mem0Memory` against the real mem0 library: the scope keys it passes must be the ones mem0
uses, both for reads and for what mem0's own model sees when it extracts new memories.

mem0 runs for real here, on a local Qdrant in a temp folder; only its model and embedder are
fakes (`SpyModel` records every extraction prompt). The newest-first list reads mem0's pgvector
table directly, so that part is tested on Postgres.
"""

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from src.runtime.memory import SHARED, Mem0Memory, MemoryGone, MemoryScope
from tests.conftest import TEST_DATABASE_URL, Postgres

ORG, BOT = uuid.uuid4(), uuid.uuid4()
SARA, ALI = uuid.uuid4(), uuid.uuid4()


class SpyModel:
    """mem0's extraction model: records each prompt, and remembers the new messages verbatim."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_response(self, messages: list[dict[str, str]], **_: Any) -> str:
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        new = prompt.split("## New Messages", 1)[1].strip().split("\n\n", 1)[0]
        return json.dumps({"memory": [{"id": "0", "text": f"Remembered: {new}"}]})


class FlatEmbedder:
    """Every text looks alike, so every search finds everything its filters allow."""

    def embed(self, text: Any, action: str | None = None) -> list[float]:
        return [1.0, 0.5, 0.25, 0.125]

    def embed_batch(self, texts: list[Any], action: str | None = None) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class Spied(SimpleNamespace):
    model: SpyModel
    searches: list[dict[str, Any]]
    memory: Mem0Memory


@pytest.fixture
async def mem0(tmp_path: Path) -> AsyncIterator[Spied]:
    os.environ["MEM0_TELEMETRY"] = "False"
    from mem0 import AsyncMemory

    fake_key = {"api_key": "sk-test"}
    real = AsyncMemory.from_config(
        {
            "vector_store": {
                "provider": "qdrant",
                "config": {"path": str(tmp_path / "qdrant"), "collection_name": "m", "embedding_model_dims": 4},
            },
            "llm": {"provider": "openai", "config": fake_key},
            "embedder": {"provider": "openai", "config": {**fake_key, "embedding_dims": 4}},
            "history_db_path": str(tmp_path / "history.db"),
        }
    )
    spied = Spied(model=SpyModel(), searches=[], memory=Mem0Memory(real))
    real.llm = spied.model
    real.embedding_model = FlatEmbedder()
    store_search = real.vector_store.search

    def search(*args: Any, **kwargs: Any) -> Any:
        spied.searches.append(dict(kwargs.get("filters") or {}))
        return store_search(*args, **kwargs)

    real.vector_store.search = search
    yield spied
    real.vector_store.client.close()


def dm(member: uuid.UUID) -> MemoryScope:
    return MemoryScope(org_id=ORG, bot_id=BOT, member_id=member)


GROUP = MemoryScope(org_id=ORG, bot_id=BOT, member_id=None)


def said(text: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": text}, {"role": "assistant", "content": "Noted."}]


async def test_a_dm_extraction_never_sees_another_members_dm(mem0: Spied) -> None:
    await mem0.memory.remember(dm(SARA), said("I am secretly job hunting"))
    await mem0.memory.remember(dm(ALI), said("I like tea"))
    await mem0.memory.remember(GROUP, said("The team ships on Fridays"))

    _sara, ali, group = mem0.model.prompts
    for prompt in (ali, group):
        assert "job hunting" not in prompt  # neither Sara's message nor the memory made from it
    assert "I like tea" not in group
    # mem0 searched existing memories only in the scope being written.
    assert [s["run_id"] for s in mem0.searches] == [str(SARA), str(ALI), SHARED]

    # The same member's next DM does see their own earlier one (the context still works).
    await mem0.memory.remember(dm(SARA), said("Remind me on Monday"))
    assert "job hunting" in mem0.model.prompts[-1]


async def test_a_dm_recalls_shared_memories_and_the_members_own_only(mem0: Spied) -> None:
    await mem0.memory.remember(dm(SARA), said("Sara is vegetarian"))
    await mem0.memory.remember(dm(ALI), said("Ali is allergic to nuts"))
    await mem0.memory.remember(GROUP, said("Lunch is at noon"))

    ali_recalls = " ".join(await mem0.memory.recall(dm(ALI), "lunch"))
    assert "nuts" in ali_recalls and "noon" in ali_recalls and "vegetarian" not in ali_recalls
    group_recalls = " ".join(await mem0.memory.recall(GROUP, "lunch"))
    assert "noon" in group_recalls and "nuts" not in group_recalls and "vegetarian" not in group_recalls

    found = await mem0.memory.list_memories(ORG, BOT, [SHARED, str(SARA)], query="lunch", limit=10)
    assert {record.member for record in found} == {SHARED, str(SARA)}


async def test_changing_a_memory_that_is_already_gone_raises_memory_gone(mem0: Spied) -> None:
    await mem0.memory.remember(GROUP, said("Lunch is at noon"))
    [record] = await mem0.memory.list_memories(ORG, BOT, [SHARED], query="lunch", limit=10)
    assert (await mem0.memory.get(record.id)) is not None
    await mem0.memory.delete(record.id)
    with pytest.raises(MemoryGone):
        await mem0.memory.delete(record.id)
    with pytest.raises(MemoryGone):
        await mem0.memory.update(record.id, "Lunch is at one")


# --- newest first, read from mem0's pgvector table ---------------------------------------------

TABLE = "bot_memories"


def _payload(member: str, text: str, created: datetime, updated: datetime | None = None) -> dict[str, Any]:
    return {
        "data": text,
        "user_id": f"org:{ORG}",
        "agent_id": str(BOT),
        "run_id": member,
        "created_at": created.isoformat(),
        **({"updated_at": updated.isoformat()} if updated else {}),
    }


def _fill_table(rows: list[dict[str, Any]]) -> None:
    assert TEST_DATABASE_URL
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        connection.execute(f"DROP TABLE IF EXISTS {TABLE}")
        connection.execute(f"CREATE TABLE {TABLE} (id uuid PRIMARY KEY, payload jsonb)")
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO bot_memories (id, payload) VALUES (%s, %s)", [(uuid.uuid4(), Jsonb(p)) for p in rows]
            )


def _drop_table() -> None:
    assert TEST_DATABASE_URL
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        connection.execute(f"DROP TABLE IF EXISTS {TABLE}")


@pytest.fixture
async def table(pg: Postgres) -> AsyncIterator[None]:
    """A stand-in for mem0's table (the columns these queries read), dropped afterwards."""
    yield
    await asyncio.to_thread(_drop_table)


async def test_the_list_is_the_newest_memories_even_with_more_than_the_limit(table: None) -> None:
    from psycopg_pool import ConnectionPool

    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [_payload(SHARED, f"shared {i}", start + timedelta(hours=i)) for i in range(60)]
    rows += [_payload(str(SARA), f"sara {i}", start + timedelta(hours=i, minutes=30)) for i in range(60)]
    rows += [_payload(str(ALI), "ali's newest", start + timedelta(days=30))]  # not in this view
    # An old memory corrected just now counts as new; timestamps in another offset still sort right.
    rows.append(_payload(SHARED, "corrected", start, updated=datetime(2026, 6, 1, 3, tzinfo=UTC)))
    karachi = timezone(timedelta(hours=5))
    rows.append(_payload(SHARED, "in Karachi time", (start + timedelta(days=20)).astimezone(karachi)))
    rows.sort(key=lambda payload: payload["data"][::-1])  # saved in no particular order
    await asyncio.to_thread(_fill_table, rows)

    assert TEST_DATABASE_URL
    with ConnectionPool(TEST_DATABASE_URL, min_size=1, max_size=1, open=True) as pool:
        store = SimpleNamespace(connection_pool=pool, collection_name=TABLE)
        memory = Mem0Memory(SimpleNamespace(vector_store=store))
        found = await memory.list_memories(ORG, BOT, [SHARED, str(SARA)], limit=50)

    texts = [record.text for record in found]
    expected_tail = [t for i in range(59, -1, -1) for t in (f"sara {i}", f"shared {i}")]
    assert texts == ["corrected", "in Karachi time", *expected_tail][:50]
    assert all(record.member in (SHARED, str(SARA)) for record in found)


async def test_the_migration_moves_old_member_tags_into_run_id(table: None) -> None:
    """Memories saved before `run_id` kept the scope in `metadata.member` only."""
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine

    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = [_payload(m, m, start) for m in (SHARED, str(SARA))]
    for payload in old:
        payload["member"] = payload.pop("run_id")
    untagged = _payload(SHARED, "untagged", start)
    del untagged["run_id"]
    await asyncio.to_thread(_fill_table, [*old, untagged, _payload(str(ALI), "new", start)])

    path = Path(__file__).parents[1] / "migrations/versions/20261113_7d2c4e9a1b3f_memory_scope_in_mem0_run_id.py"
    spec = importlib.util.spec_from_file_location("memory_scope_migration", path)
    assert spec and spec.loader and TEST_DATABASE_URL
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.begin() as sa_connection, Operations.context(MigrationContext.configure(sa_connection)):
        migration.upgrade()
    engine.dispose()

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        rows = connection.execute("SELECT payload->>'data', payload->>'run_id' FROM bot_memories").fetchall()
    assert dict(rows) == {SHARED: SHARED, str(SARA): str(SARA), "untagged": None, "new": str(ALI)}

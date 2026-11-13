"""Bot memory (agents-and-plugins.md §9): recall before answering, remember after, and let
people see, correct and forget what a bot remembers (Settings → Memory).

`MemoryService` is the only code that talks to mem0, and it always sets the scope itself:
organization + bot, and in a DM the member too. A model can never choose the scope. Who may
see and forget what on the memory screen is decided in `services/memory_service.py`.
Memory is a nice-to-have: if it fails, the run carries on without it.

How the scope maps onto mem0's three entity keys. mem0 uses them for every read *and* for the
context its own model sees when it extracts new memories (the scope's last messages and its
closest existing memories):
- `user_id` = `org:<org id>`, `agent_id` = the bot's id,
- `run_id` = the member's id for what was learned in their DM, or `shared` for group chats.
So a DM's extraction never sees another member's DM, and a group chat never sees any DM.
mem0 can't OR across `run_id` values, so a DM's recall searches twice (shared + the member)
and merges by score. Memories saved before `run_id` was used carry their scope in
`metadata.member`; migration 7d2c4e9a1b3f copies it into `run_id` (rows with neither stay
out of every scope; "forget everything" still deletes them).
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.core.config import Settings

logger = logging.getLogger(__name__)

RECALL_LIMIT = 5
SHARED = "shared"  # memories learned in group chats, which any member's chat may recall


class MemoryGone(LookupError):
    """The memory was deleted between being read and being changed (someone else forgot it)."""


@dataclass(frozen=True)
class MemoryScope:
    org_id: uuid.UUID
    bot_id: uuid.UUID
    member_id: uuid.UUID | None  # set in a DM: what's learned there stays in that member's chats

    @property
    def member(self) -> str:
        """mem0's `run_id` for this scope: the DM's member, or SHARED in a group chat."""
        return str(self.member_id) if self.member_id else SHARED


@dataclass(frozen=True)
class MemoryRecord:
    """One saved memory, with the scope it was saved under, so callers can check it."""

    id: str
    text: str
    user_id: str  # org_key(org id)
    agent_id: str  # the bot's id
    member: str  # its mem0 `run_id`: SHARED, or the id of the member whose DM it came from
    created_at: datetime | None
    updated_at: datetime | None


def org_key(org_id: uuid.UUID) -> str:
    """mem0's `user_id` for an organization: every memory of its bots is saved under it."""
    return f"org:{org_id}"


class MemoryService(Protocol):
    @property
    def off_reason(self) -> str | None:
        """Why memory is off on this server, or None when it's on."""
        ...

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        """Up to five memories that may help answer `query`."""
        ...

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        """Let the memory decide what in this exchange is worth keeping. Slow: run it in the background."""
        ...

    async def list_memories(
        self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], *, query: str = "", limit: int
    ) -> list[MemoryRecord]:
        """This bot's memories saved for any of `members`, at most `limit`: the closest to
        `query` first, or without one, the newest first (by when they last changed)."""
        ...

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """One memory by id, whatever its scope. The caller checks the scope before using it."""
        ...

    async def update(self, memory_id: str, text: str) -> None:
        """Raises `MemoryGone` if it no longer exists."""
        ...

    async def delete(self, memory_id: str) -> None:
        """Raises `MemoryGone` if it no longer exists."""
        ...

    async def delete_all(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        """Everything this bot remembers in this organization, from every chat."""
        ...


class NoMemory:
    """The default: remembers nothing, and says why."""

    def __init__(self, reason: str = "Memory is off on this server.") -> None:
        self._reason = reason

    @property
    def off_reason(self) -> str | None:
        return self._reason

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        return []

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        return None

    async def list_memories(
        self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], *, query: str = "", limit: int
    ) -> list[MemoryRecord]:
        return []

    async def get(self, memory_id: str) -> MemoryRecord | None:
        return None

    async def update(self, memory_id: str, text: str) -> None:
        return None

    async def delete(self, memory_id: str) -> None:
        return None

    async def delete_all(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        return None


def _when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _record(item: dict[str, Any]) -> MemoryRecord:
    """A memory as mem0 returns it (`get`, `search`), or a row of its table in that shape."""
    return MemoryRecord(
        id=str(item["id"]),
        text=str(item.get("memory", "")),
        user_id=str(item.get("user_id", "")),
        agent_id=str(item.get("agent_id", "")),
        member=str(item.get("run_id", "")),
        created_at=_when(item.get("created_at")),
        updated_at=_when(item.get("updated_at")),
    )


def _gone_if_missing(error: ValueError) -> Exception:
    """mem0 says "Memory with id … not found" with a ValueError; any other ValueError stays one."""
    return MemoryGone(str(error)) if "not found" in str(error) else error


# mem0's pgvector `list()` has no ORDER BY, so with more memories than the limit it returns an
# arbitrary subset. The memory screen reads the newest straight from mem0's table instead
# (id, vector, payload jsonb), with the same scope keys mem0 filters by.
NEWEST_SQL = """
SELECT id, payload FROM {table}
WHERE payload->>'user_id' = %s AND payload->>'agent_id' = %s AND payload->>'run_id' = ANY(%s)
ORDER BY COALESCE(payload->>'updated_at', payload->>'created_at')::timestamptz DESC NULLS LAST, id
LIMIT %s
"""


def newest_in_table(
    connection: Any, table: str, *, user_id: str, agent_id: str, run_ids: list[str], limit: int
) -> list[dict[str, Any]]:
    """The newest `limit` memories in mem0's pgvector table for this scope, shaped like mem0's
    own results. `connection` is a psycopg 3 connection."""
    from psycopg import sql

    query = sql.SQL(NEWEST_SQL).format(table=sql.Identifier(table))
    with connection.cursor() as cursor:
        cursor.execute(query, (user_id, agent_id, run_ids, limit))
        rows = cursor.fetchall()
    return [{**payload, "id": str(memory_id), "memory": payload.get("data", "")} for memory_id, payload in rows]


class Mem0Memory:
    """mem0 on pgvector, in the same Postgres database."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory  # mem0.AsyncMemory

    @property
    def off_reason(self) -> str | None:
        return None

    @staticmethod
    def _filters(org_id: uuid.UUID, bot_id: uuid.UUID, member: str) -> dict[str, str]:
        """One scope as mem0's entity keys (see the module docstring)."""
        return {"user_id": org_key(org_id), "agent_id": str(bot_id), "run_id": member}

    async def _search(
        self, query: str, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        """The closest memories across `members`: one search per scope, merged by score."""
        found = await asyncio.gather(
            *(self._memory.search(query, top_k=top_k, filters=self._filters(org_id, bot_id, m)) for m in members)
        )
        merged = [item for result in found for item in result.get("results", [])]
        merged.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return merged[:top_k]

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        members = [SHARED, scope.member] if scope.member_id else [SHARED]
        found = await self._search(query, scope.org_id, scope.bot_id, members, RECALL_LIMIT)
        return [str(item["memory"]) for item in found]

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        # All three keys: mem0 builds its extraction context (the scope's last messages and
        # closest memories) from exactly these, so nothing from another member's DM reaches it.
        await self._memory.add(conversation, **self._filters(scope.org_id, scope.bot_id, scope.member))

    async def list_memories(
        self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], *, query: str = "", limit: int
    ) -> list[MemoryRecord]:
        if query.strip():
            found = await self._search(query, org_id, bot_id, members, limit)
        else:
            found = await asyncio.to_thread(self._newest, org_id, bot_id, members, limit)
        return [_record(item) for item in found]

    def _newest(self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], limit: int) -> list[dict[str, Any]]:
        store = self._memory.vector_store  # mem0's PGVector: a psycopg 3 pool and its table's name
        with store.connection_pool.connection() as connection:
            return newest_in_table(
                connection,
                store.collection_name,
                user_id=org_key(org_id),
                agent_id=str(bot_id),
                run_ids=members,
                limit=limit,
            )

    async def get(self, memory_id: str) -> MemoryRecord | None:
        item = await self._memory.get(memory_id)
        return _record(item) if item else None

    async def update(self, memory_id: str, text: str) -> None:
        try:
            await self._memory.update(memory_id, text=text)
        except ValueError as error:
            raise _gone_if_missing(error) from error

    async def delete(self, memory_id: str) -> None:
        try:
            await self._memory.delete(memory_id)
        except ValueError as error:
            raise _gone_if_missing(error) from error

    async def delete_all(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        # No run_id: every scope of this bot, the shared one and every member's DM.
        await self._memory.delete_all(user_id=org_key(org_id), agent_id=str(bot_id))


def memory_off_reason(settings: Settings) -> str | None:
    """Why this server can't remember anything, worded for the memory screen; None when it can."""
    if not settings.memory_enabled:
        return "Memory is off on this server. Set MEMORY_ENABLED=true and add OPENAI_API_KEY to turn it on."
    if not settings.uses_postgres:
        return "Memory needs the Postgres database: it saves memories next to everything else."
    if not settings.openai_api_key.get_secret_value():
        return "Add OPENAI_API_KEY on the server to turn memory on. Memories are read and searched with OpenAI."
    return None


def build_memory(settings: Settings) -> MemoryService:
    """mem0 when it's switched on and can work (Postgres + an OpenAI key for its model and
    embeddings); otherwise no memory, with the reason."""
    if reason := memory_off_reason(settings):
        return NoMemory(reason)
    # mem0 reports usage to its makers unless told not to; this must be set before the import.
    os.environ["MEM0_TELEMETRY"] = "False"
    from mem0 import AsyncMemory

    openai = {"api_key": settings.openai_api_key.get_secret_value()}
    memory = AsyncMemory.from_config(
        {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "connection_string": settings.direct_url,
                    "collection_name": "bot_memories",
                    "embedding_model_dims": 1536,
                    "hnsw": True,
                },
            },
            "llm": {"provider": "openai", "config": {**openai, "model": "gpt-4.1-mini"}},
            "embedder": {"provider": "openai", "config": {**openai, "model": "text-embedding-3-small"}},
        }
    )
    return Mem0Memory(memory)

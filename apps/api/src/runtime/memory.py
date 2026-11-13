"""Bot memory (agents-and-plugins.md §9): recall before answering, remember after, and let
people see, correct and forget what a bot remembers (Settings → Memory).

`MemoryService` is the only code that talks to mem0, and it always sets the scope itself:
organization + bot, and in a DM the member too. A model can never choose the scope. Who may
see and forget what on the memory screen is decided in `services/memory_service.py`.
Memory is a nice-to-have: if it fails, the run carries on without it.
"""

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


@dataclass(frozen=True)
class MemoryScope:
    org_id: uuid.UUID
    bot_id: uuid.UUID
    member_id: uuid.UUID | None  # set in a DM: what's learned there stays in that member's chats


@dataclass(frozen=True)
class MemoryRecord:
    """One saved memory, with the scope it was saved under, so callers can check it."""

    id: str
    text: str
    user_id: str  # org_key(org id)
    agent_id: str  # the bot's id
    member: str  # SHARED, or the id of the member whose DM it came from
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
        """This bot's memories saved for any of `members`: the closest to `query` first, or all."""
        ...

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """One memory by id, whatever its scope. The caller checks the scope before using it."""
        ...

    async def update(self, memory_id: str, text: str) -> None: ...

    async def delete(self, memory_id: str) -> None: ...

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
    """A memory as mem0 returns it. Our "member" tag comes back inside its metadata."""
    metadata = item.get("metadata") or {}
    return MemoryRecord(
        id=str(item["id"]),
        text=str(item.get("memory", "")),
        user_id=str(item.get("user_id", "")),
        agent_id=str(item.get("agent_id", "")),
        member=str(metadata.get("member", "")),
        created_at=_when(item.get("created_at")),
        updated_at=_when(item.get("updated_at")),
    )


class Mem0Memory:
    """mem0 on pgvector, in the same Postgres database."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory  # mem0.AsyncMemory

    @property
    def off_reason(self) -> str | None:
        return None

    @staticmethod
    def _filters(org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str]) -> dict[str, Any]:
        return {"user_id": org_key(org_id), "agent_id": str(bot_id), "member": {"in": members}}

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        members = [SHARED, str(scope.member_id)] if scope.member_id else [SHARED]
        found = await self._memory.search(
            query, top_k=RECALL_LIMIT, filters=self._filters(scope.org_id, scope.bot_id, members)
        )
        return [str(item["memory"]) for item in found.get("results", [])]

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        await self._memory.add(
            conversation,
            user_id=org_key(scope.org_id),
            agent_id=str(scope.bot_id),
            metadata={"member": str(scope.member_id) if scope.member_id else SHARED},
        )

    async def list_memories(
        self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], *, query: str = "", limit: int
    ) -> list[MemoryRecord]:
        filters = self._filters(org_id, bot_id, members)
        if query.strip():
            found = await self._memory.search(query, top_k=limit, filters=filters)
        else:
            found = await self._memory.get_all(filters=filters, top_k=limit)
        return [_record(item) for item in found.get("results", [])]

    async def get(self, memory_id: str) -> MemoryRecord | None:
        item = await self._memory.get(memory_id)
        return _record(item) if item else None

    async def update(self, memory_id: str, text: str) -> None:
        await self._memory.update(memory_id, text=text)

    async def delete(self, memory_id: str) -> None:
        await self._memory.delete(memory_id)

    async def delete_all(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
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

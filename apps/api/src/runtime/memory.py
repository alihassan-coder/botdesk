"""Bot memory (agents-and-plugins.md §9): recall before answering, remember after.

`MemoryService` is the only code that talks to mem0, and it always sets the scope itself:
organization + bot, and in a DM the member too. A model can never choose the scope.
Memory is a nice-to-have: if it fails, the run carries on without it.
"""

import logging
import os
import uuid
from dataclasses import dataclass
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


class MemoryService(Protocol):
    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        """Up to five memories that may help answer `query`."""
        ...

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        """Let the memory decide what in this exchange is worth keeping. Slow: run it in the background."""
        ...


class NoMemory:
    """The default: remembers nothing."""

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        return []

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        return None


class Mem0Memory:
    """mem0 on pgvector, in the same Postgres database."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory  # mem0.AsyncMemory

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        members = [SHARED, str(scope.member_id)] if scope.member_id else [SHARED]
        found = await self._memory.search(
            query,
            top_k=RECALL_LIMIT,
            filters={"user_id": f"org:{scope.org_id}", "agent_id": str(scope.bot_id), "member": {"in": members}},
        )
        return [str(item["memory"]) for item in found.get("results", [])]

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        await self._memory.add(
            conversation,
            user_id=f"org:{scope.org_id}",
            agent_id=str(scope.bot_id),
            metadata={"member": str(scope.member_id) if scope.member_id else SHARED},
        )


def build_memory(settings: Settings) -> MemoryService:
    """mem0 when it's switched on and can work (Postgres + an OpenAI key for its model and
    embeddings); otherwise no memory."""
    if not (settings.memory_enabled and settings.uses_postgres and settings.openai_api_key):
        return NoMemory()
    # mem0 reports usage to its makers unless told not to; this must be set before the import.
    os.environ["MEM0_TELEMETRY"] = "False"
    from mem0 import AsyncMemory

    openai = {"api_key": settings.openai_api_key}
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

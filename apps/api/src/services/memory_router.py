"""Each organization's memory (Settings → Memory): with its own memory key, mem0 with that key and
provider; without one, the server's own memory (OPENAI_API_KEY), if the operator set one up.

`OrgMemory` is the `MemoryService` runs and the memory screen use: every call names its
organization, and goes to that organization's memory. Built memories are kept per organization
and key, so a key change takes effect on the next call (`forget(org)` after saving a key).
"""

import hashlib
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.models import MemoryKey
from src.runtime.memory import (
    NO_POSTGRES,
    MemoryProvider,
    MemoryRecord,
    MemoryScope,
    MemoryService,
    NoMemory,
    build_mem0,
)
from src.services.credential_vault import CredentialVault

Builder = Callable[[Settings, MemoryProvider, str], MemoryService]
MAX_BUILT = 50  # organizations whose memory is kept ready


class OrgMemory:
    def __init__(
        self,
        server_memory: MemoryService,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        vault: CredentialVault,
        build: Builder = build_mem0,
    ) -> None:
        self._server = server_memory
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._vault = vault
        self._build = build
        self._built: dict[uuid.UUID, tuple[str, MemoryService]] = {}  # org → (key fingerprint, memory)

    def forget(self, org_id: uuid.UUID) -> None:
        """The organization's key changed: build its memory again on the next call."""
        self._built.pop(org_id, None)

    async def _for(self, org_id: uuid.UUID) -> MemoryService:
        async with self._sessionmaker() as db:
            row = await db.scalar(select(MemoryKey).where(MemoryKey.org_id == org_id))
        if row is None:
            return self._server
        if not self._settings.uses_postgres:
            return NoMemory(NO_POSTGRES)
        fingerprint = hashlib.sha256(f"{row.provider}:{row.encrypted_key}".encode()).hexdigest()
        built = self._built.get(org_id)
        if built is None or built[0] != fingerprint:
            if len(self._built) >= MAX_BUILT:
                self._built.pop(next(iter(self._built)))
            provider: MemoryProvider = row.provider  # type: ignore[assignment]
            built = (fingerprint, self._build(self._settings, provider, self._vault.unseal(row.encrypted_key)))
            self._built[org_id] = built
        return built[1]

    async def off_reason_for(self, org_id: uuid.UUID) -> str | None:
        return await (await self._for(org_id)).off_reason_for(org_id)

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        return await (await self._for(scope.org_id)).recall(scope, query)

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        await (await self._for(scope.org_id)).remember(scope, conversation)

    async def list_memories(
        self, org_id: uuid.UUID, bot_id: uuid.UUID, members: list[str], *, query: str = "", limit: int
    ) -> list[MemoryRecord]:
        return await (await self._for(org_id)).list_memories(org_id, bot_id, members, query=query, limit=limit)

    async def get(self, org_id: uuid.UUID, memory_id: str) -> MemoryRecord | None:
        return await (await self._for(org_id)).get(org_id, memory_id)

    async def update(self, org_id: uuid.UUID, memory_id: str, text: str) -> None:
        await (await self._for(org_id)).update(org_id, memory_id, text)

    async def delete(self, org_id: uuid.UUID, memory_id: str) -> None:
        await (await self._for(org_id)).delete(org_id, memory_id)

    async def delete_all(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        await (await self._for(org_id)).delete_all(org_id, bot_id)

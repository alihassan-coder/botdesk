"""Handles the memory screen: list, search, correct and forget what a bot remembers.
The bot must belong to the organization in the URL; the rules are in memory_service."""

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.memory import MemoryService
from src.schemas.memory import MemoryKeyIn, MemoryKeyOut, MemoryOut, MemoryStatusOut
from src.services import bot_service, memory_key_service, memory_service
from src.services.credential_vault import CredentialVault
from src.services.memory_router import OrgMemory
from src.services.memory_service import Viewer


async def _viewer(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> Viewer:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another org's bot
    return Viewer(
        org_id=access.org.id, bot_id=bot.id, user_id=access.user.id, is_admin=access.role in ("owner", "admin")
    )


async def memory_status(memory: MemoryService, access: Access) -> MemoryStatusOut:
    return await memory_service.status(memory, access.org.id)


async def list_memories(
    db: AsyncSession, access: Access, memory: MemoryService, bot_id: uuid.UUID, *, query: str, limit: int
) -> list[MemoryOut]:
    return await memory_service.list_memories(memory, await _viewer(db, access, bot_id), query=query, limit=limit)


async def correct_memory(
    db: AsyncSession, access: Access, memory: MemoryService, bot_id: uuid.UUID, memory_id: uuid.UUID, text: str
) -> MemoryOut:
    return await memory_service.correct(memory, await _viewer(db, access, bot_id), str(memory_id), text)


async def forget_memory(
    db: AsyncSession, access: Access, memory: MemoryService, bot_id: uuid.UUID, memory_id: uuid.UUID
) -> None:
    await memory_service.forget(memory, await _viewer(db, access, bot_id), str(memory_id))


async def forget_everything(db: AsyncSession, access: Access, memory: MemoryService, bot_id: uuid.UUID) -> None:
    await memory_service.forget_everything(memory, await _viewer(db, access, bot_id))


# The memory key (Settings → Memory): owners and admins set it; everyone sees which provider.


async def get_memory_key(db: AsyncSession, access: Access) -> MemoryKeyOut:
    return memory_key_service.view_of(await memory_key_service.find(db, access.org.id))


async def save_memory_key(
    db: AsyncSession,
    access: Access,
    body: MemoryKeyIn,
    memory: MemoryService,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None,
) -> MemoryKeyOut:
    access.require_admin()
    row = await memory_key_service.save(
        db, org_id=access.org.id, user_id=access.user.id, body=body, vault=vault, transport=transport
    )
    await db.commit()
    if isinstance(memory, OrgMemory):
        memory.forget(access.org.id)
    return memory_key_service.view_of(row)


async def remove_memory_key(db: AsyncSession, access: Access, memory: MemoryService) -> None:
    """Memory goes back to the server's key, if any. Memories saved with this key stay, but are only
    found again with a key for the same provider."""
    access.require_admin()
    row = await memory_key_service.find(db, access.org.id)
    if row is not None:
        await db.delete(row)
        await db.commit()
    if isinstance(memory, OrgMemory):
        memory.forget(access.org.id)

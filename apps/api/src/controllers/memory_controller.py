"""Handles the memory screen: list, search, correct and forget what a bot remembers.
The bot must belong to the organization in the URL; the rules are in memory_service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.memory import MemoryService
from src.schemas.memory import MemoryOut, MemoryStatusOut
from src.services import bot_service, memory_service
from src.services.memory_service import Viewer


async def _viewer(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> Viewer:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another org's bot
    return Viewer(
        org_id=access.org.id, bot_id=bot.id, user_id=access.user.id, is_admin=access.role in ("owner", "admin")
    )


def memory_status(memory: MemoryService) -> MemoryStatusOut:
    return memory_service.status(memory)


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

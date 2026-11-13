"""What a bot remembers, as people see it on the memory screen (Settings → Memory).

The scope always comes from the URL and the session, never from the client:
- Every call is about one bot in one organization. mem0 is asked with those filters, and a
  memory fetched by id must carry both, or it's "not found" (so ids from another org or bot
  lead nowhere).
- You see the bot's shared memories (learned in group chats) and the ones from your own DM
  with it. Nobody sees another member's DM memories, owners and admins included.
- Owners and admins can forget or correct any memory of the bot; members only their own DM
  ones. Forgetting everything a bot remembers takes an owner or admin.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from src.core.errors import AppError, Forbidden, NotFound, Unavailable
from src.runtime.memory import SHARED, MemoryRecord, MemoryService, org_key
from src.schemas.memory import MemoryOut, MemoryStatusOut

logger = logging.getLogger(__name__)

NOT_FOUND = "Memory not found."
UNAVAILABLE = "Memory isn't answering right now. Try again in a moment."
SHARED_ONLY_ADMINS = "Only owners and admins can change what a bot learned in group chats."
FORGET_ALL_ONLY_ADMINS = "Only owners and admins can make a bot forget everything."


@dataclass(frozen=True)
class Viewer:
    """Who is looking at which bot's memory."""

    org_id: uuid.UUID
    bot_id: uuid.UUID
    user_id: uuid.UUID
    is_admin: bool

    @property
    def visible_members(self) -> list[str]:
        return [SHARED, str(self.user_id)]

    def owns_scope_of(self, record: MemoryRecord) -> bool:
        """The memory belongs to this org and this bot."""
        return record.user_id == org_key(self.org_id) and record.agent_id == str(self.bot_id)


def status(memory: MemoryService) -> MemoryStatusOut:
    reason = memory.off_reason
    return MemoryStatusOut(enabled=reason is None, reason=reason)


def memory_out(record: MemoryRecord, viewer: Viewer) -> MemoryOut:
    return MemoryOut(
        id=record.id,
        text=record.text,
        created_at=record.created_at,
        updated_at=record.updated_at,
        scope="you" if record.member == str(viewer.user_id) else "bot",
    )


@asynccontextmanager
async def _reaching_memory() -> AsyncIterator[None]:
    """mem0 failing (its database, OpenAI) is a 503 in plain words, not a 500."""
    try:
        yield
    except AppError:
        raise
    except Exception as error:
        logger.exception("Memory call failed")
        raise Unavailable(UNAVAILABLE) from error


def _newest_first(record: MemoryRecord) -> datetime:
    return record.updated_at or record.created_at or datetime.min.replace(tzinfo=UTC)


async def list_memories(memory: MemoryService, viewer: Viewer, *, query: str, limit: int) -> list[MemoryOut]:
    """Search when there's a query (closest first), else everything, newest first."""
    query = query.strip()
    async with _reaching_memory():
        records = await memory.list_memories(
            viewer.org_id, viewer.bot_id, viewer.visible_members, query=query, limit=limit
        )
    # Whatever the store returned, show only what this viewer may see.
    records = [r for r in records if viewer.owns_scope_of(r) and r.member in viewer.visible_members]
    if not query:
        records.sort(key=_newest_first, reverse=True)
    return [memory_out(record, viewer) for record in records]


async def _changeable(memory: MemoryService, viewer: Viewer, memory_id: str) -> MemoryRecord:
    """The memory, if it's this bot's and this viewer may change it."""
    async with _reaching_memory():
        record = await memory.get(memory_id)
    if record is None or not viewer.owns_scope_of(record):
        raise NotFound(NOT_FOUND)
    if viewer.is_admin or record.member == str(viewer.user_id):
        return record
    if record.member == SHARED:
        raise Forbidden(SHARED_ONLY_ADMINS)
    raise NotFound(NOT_FOUND)  # another member's DM memory: don't even say it exists


async def forget(memory: MemoryService, viewer: Viewer, memory_id: str) -> None:
    record = await _changeable(memory, viewer, memory_id)
    async with _reaching_memory():
        await memory.delete(record.id)


async def correct(memory: MemoryService, viewer: Viewer, memory_id: str, text: str) -> MemoryOut:
    record = await _changeable(memory, viewer, memory_id)
    async with _reaching_memory():
        await memory.update(record.id, text)
        updated = await memory.get(record.id)
    if updated is None:
        raise NotFound(NOT_FOUND)
    return memory_out(updated, viewer)


async def forget_everything(memory: MemoryService, viewer: Viewer) -> None:
    if not viewer.is_admin:
        raise Forbidden(FORGET_ALL_ONLY_ADMINS)
    async with _reaching_memory():
        await memory.delete_all(viewer.org_id, viewer.bot_id)

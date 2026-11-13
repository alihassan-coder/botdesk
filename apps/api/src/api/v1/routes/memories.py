import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.deps import Db, Memory, OrgAccess
from src.controllers import memory_controller
from src.schemas.memory import MemoryOut, MemoryStatusOut, MemoryUpdate

router = APIRouter(prefix="/orgs/{org_id}", tags=["memory"])


@router.get("/memory/status")
async def memory_status(access: OrgAccess, memory: Memory) -> MemoryStatusOut:
    """Whether bots can remember things on this server, and if not, why."""
    return memory_controller.memory_status(memory)


@router.get("/bots/{bot_id}/memories")
async def list_memories(
    bot_id: uuid.UUID,
    access: OrgAccess,
    db: Db,
    memory: Memory,
    q: Annotated[str, Query(max_length=500)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[MemoryOut]:
    """What this bot remembers that you may see: its shared memories and the ones from your DM.
    With `q`, the closest matches first; without, newest first. Empty when memory is off."""
    return await memory_controller.list_memories(db, access, memory, bot_id, query=q, limit=limit)


@router.delete("/bots/{bot_id}/memories", status_code=status.HTTP_204_NO_CONTENT)
async def forget_everything(bot_id: uuid.UUID, access: OrgAccess, db: Db, memory: Memory) -> None:
    """Make the bot forget everything, from every chat. Owners and admins only."""
    await memory_controller.forget_everything(db, access, memory, bot_id)


@router.patch("/bots/{bot_id}/memories/{memory_id}")
async def correct_memory(
    bot_id: uuid.UUID, memory_id: uuid.UUID, body: MemoryUpdate, access: OrgAccess, db: Db, memory: Memory
) -> MemoryOut:
    """Correct a memory. Owners and admins: any; members: their own DM memories."""
    return await memory_controller.correct_memory(db, access, memory, bot_id, memory_id, body.text)


@router.delete("/bots/{bot_id}/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_memory(bot_id: uuid.UUID, memory_id: uuid.UUID, access: OrgAccess, db: Db, memory: Memory) -> None:
    """Forget one memory. Owners and admins: any; members: their own DM memories."""
    await memory_controller.forget_memory(db, access, memory, bot_id, memory_id)

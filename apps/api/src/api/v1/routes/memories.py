import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.deps import Db, Memory, OrgAccess, Outbound, Vault
from src.controllers import memory_controller
from src.schemas.memory import MemoryKeyIn, MemoryKeyOut, MemoryOut, MemoryStatusOut, MemoryUpdate

router = APIRouter(prefix="/orgs/{org_id}", tags=["memory"])


@router.get("/memory/status")
async def memory_status(access: OrgAccess, memory: Memory) -> MemoryStatusOut:
    """Whether this organization's bots can remember things, and if not, why."""
    return await memory_controller.memory_status(memory, access)


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


@router.get("/memory-key")
async def get_memory_key(access: OrgAccess, db: Db) -> MemoryKeyOut:
    """The organization's memory key: which provider, and its last 4 characters. Never the key."""
    return await memory_controller.get_memory_key(db, access)


@router.put("/memory-key")
async def save_memory_key(
    body: MemoryKeyIn, access: OrgAccess, db: Db, memory: Memory, vault: Vault, outbound: Outbound
) -> MemoryKeyOut:
    """Set a key used only for bots' memory, OpenAI or Gemini (owners and admins). Checked live first."""
    return await memory_controller.save_memory_key(db, access, body, memory, vault, outbound)


@router.delete("/memory-key", status_code=status.HTTP_204_NO_CONTENT)
async def remove_memory_key(access: OrgAccess, db: Db, memory: Memory) -> None:
    """Remove it (owners and admins): memory goes back to the server's key, if there is one."""
    await memory_controller.remove_memory_key(db, access, memory)

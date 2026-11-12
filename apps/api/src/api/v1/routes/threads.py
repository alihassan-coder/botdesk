import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.deps import Db, OrgAccess
from src.controllers import thread_controller
from src.schemas.thread import GroupIn, MessageIn, MessageOut, OpenDmIn, ThreadOut

router = APIRouter(prefix="/orgs/{org_id}/threads", tags=["threads"])


@router.get("")
async def list_threads(access: OrgAccess, db: Db) -> list[ThreadOut]:
    """Your chats in this organization, most recent first."""
    return await thread_controller.list_threads(db, access)


@router.post("/dm")
async def open_dm(body: OpenDmIn, access: OrgAccess, db: Db) -> ThreadOut:
    """Your chat with a bot. Returns the existing one, or starts it."""
    return await thread_controller.open_dm(db, access, body.bot_id)


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupIn, access: OrgAccess, db: Db) -> ThreadOut:
    """A group chat with you plus the people and bots you pick."""
    return await thread_controller.create_group(db, access, body)


@router.get("/{thread_id}")
async def get_thread(thread_id: uuid.UUID, access: OrgAccess, db: Db) -> ThreadOut:
    return await thread_controller.get_thread(db, access, thread_id)


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: uuid.UUID,
    access: OrgAccess,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: datetime | None = None,
) -> list[MessageOut]:
    """Messages, oldest first. For older ones, pass the first message's `createdAt` as `before`."""
    return await thread_controller.list_messages(db, access, thread_id, limit=limit, before=before)


@router.post("/{thread_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(thread_id: uuid.UUID, body: MessageIn, access: OrgAccess, db: Db) -> MessageOut:
    """Send a message. (Bots replying comes in the next slice.)"""
    return await thread_controller.post_message(db, access, thread_id, body)

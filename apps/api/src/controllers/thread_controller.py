"""Handles thread and message requests."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.schemas.thread import GroupIn, MessageIn, MessageOut, ThreadOut
from src.services import thread_service


async def list_threads(db: AsyncSession, access: Access) -> list[ThreadOut]:
    threads = await thread_service.threads_for_user(db, org_id=access.org.id, user_id=access.user.id)
    return [await thread_service.thread_out(db, thread) for thread in threads]


async def get_thread(db: AsyncSession, access: Access, thread_id: uuid.UUID) -> ThreadOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    return await thread_service.thread_out(db, thread)


async def open_dm(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> ThreadOut:
    thread = await thread_service.open_dm(db, org_id=access.org.id, user_id=access.user.id, bot_id=bot_id)
    await db.commit()
    return await thread_service.thread_out(db, thread)


async def create_group(db: AsyncSession, access: Access, body: GroupIn) -> ThreadOut:
    thread = await thread_service.create_group(
        db,
        org_id=access.org.id,
        creator_id=access.user.id,
        title=body.title,
        user_ids=body.user_ids,
        bot_ids=body.bot_ids,
    )
    await db.commit()
    return await thread_service.thread_out(db, thread)


async def list_messages(
    db: AsyncSession, access: Access, thread_id: uuid.UUID, *, limit: int, before: datetime | None
) -> list[MessageOut]:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    messages = await thread_service.list_messages(db, thread, limit=limit, before=before)
    return [thread_service.message_out(message) for message in messages]


async def post_message(db: AsyncSession, access: Access, thread_id: uuid.UUID, body: MessageIn) -> MessageOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    message = await thread_service.post_message(db, thread=thread, user_id=access.user.id, text=body.text)
    await db.commit()
    return thread_service.message_out(message)

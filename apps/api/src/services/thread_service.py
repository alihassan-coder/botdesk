"""Threads (DMs with a bot, and groups) and their messages.

Visibility follows the usual chat-app rule: you see a thread only if you're in it.
Bot replies come in a later slice; for now messages are stored and read back.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utcnow
from src.core.errors import NotFound
from src.models import Bot, Membership, Message, Thread, ThreadParticipant
from src.schemas.thread import AuthorOut, MessageOut, ParticipantOut, ThreadOut

PREVIEW_LENGTH = 80
NOT_FOUND = "This chat doesn't exist."


def text_part(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def message_out(message: Message) -> MessageOut:
    return MessageOut.model_validate(
        {
            "id": message.id,
            "thread_id": message.thread_id,
            "author": AuthorOut.model_validate({"type": message.author_type, "id": message.author_id}),
            "parts": message.parts,
            "status": message.status,
            "created_at": message.created_at,
        }
    )


async def _participants(db: AsyncSession, thread_id: uuid.UUID) -> list[ThreadParticipant]:
    return list(await db.scalars(select(ThreadParticipant).where(ThreadParticipant.thread_id == thread_id)))


async def thread_out(db: AsyncSession, thread: Thread) -> ThreadOut:
    last = await db.scalar(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.desc()).limit(1)
    )
    participants = [
        ParticipantOut.model_validate({"type": p.participant_type, "id": p.participant_id})
        for p in await _participants(db, thread.id)
    ]
    return ThreadOut.model_validate(
        {
            "id": thread.id,
            "kind": thread.kind,
            "title": thread.title,
            "bot_id": thread.bot_id,
            "participants": participants,
            "last_message_at": thread.last_message_at,
            "last_message_preview": last.text[:PREVIEW_LENGTH] if last else "",
        }
    )


async def threads_for_user(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID) -> list[Thread]:
    """Threads the user is in, most recent activity first."""
    rows = await db.scalars(
        select(Thread)
        .join(ThreadParticipant, ThreadParticipant.thread_id == Thread.id)
        .where(
            Thread.org_id == org_id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
        .order_by(Thread.last_message_at.desc())
    )
    return list(rows)


async def get_thread(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID, thread_id: uuid.UUID) -> Thread:
    """The thread, if it's in this organization and the user is in it. Otherwise 404."""
    thread = await db.get(Thread, thread_id)
    if thread is None or thread.org_id != org_id:
        raise NotFound(NOT_FOUND)
    if await db.get(ThreadParticipant, (thread.id, "user", user_id)) is None:
        raise NotFound(NOT_FOUND)
    return thread


def _add_participants(db: AsyncSession, thread: Thread, *, users: set[uuid.UUID], bots: set[uuid.UUID]) -> None:
    for user_id in users:
        db.add(ThreadParticipant(thread_id=thread.id, participant_type="user", participant_id=user_id))
    for bot_id in bots:
        db.add(ThreadParticipant(thread_id=thread.id, participant_type="bot", participant_id=bot_id))


async def open_dm(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID, bot_id: uuid.UUID) -> Thread:
    """Your DM with a bot: the existing one, or a new one."""
    bot = await db.get(Bot, bot_id)
    if bot is None or bot.org_id != org_id:
        raise NotFound("Bot not found.")
    existing = await db.scalar(
        select(Thread)
        .join(ThreadParticipant, ThreadParticipant.thread_id == Thread.id)
        .where(
            Thread.kind == "dm",
            Thread.bot_id == bot_id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
    )
    if existing:
        return existing
    thread = Thread(org_id=org_id, kind="dm", title=bot.name, bot_id=bot.id, created_by=user_id)
    db.add(thread)
    await db.flush()
    _add_participants(db, thread, users={user_id}, bots={bot.id})
    return thread


async def create_group(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: str,
    user_ids: list[uuid.UUID],
    bot_ids: list[uuid.UUID],
) -> Thread:
    """A group with you, the people and the bots you pick. Everyone must be in the organization."""
    users = {creator_id, *user_ids}
    members = set(
        await db.scalars(select(Membership.user_id).where(Membership.org_id == org_id, Membership.user_id.in_(users)))
    )
    bots = set(bot_ids)
    org_bots = set(await db.scalars(select(Bot.id).where(Bot.org_id == org_id, Bot.id.in_(bots)))) if bots else set()
    if members != users or org_bots != bots:
        raise NotFound("Some of those people or bots aren't in this organization.")

    thread = Thread(org_id=org_id, kind="group", title=title.strip(), bot_id=None, created_by=creator_id)
    db.add(thread)
    await db.flush()
    _add_participants(db, thread, users=users, bots=bots)
    return thread


async def list_messages(
    db: AsyncSession, thread: Thread, *, limit: int = 50, before: datetime | None = None
) -> list[Message]:
    """Up to `limit` messages before a moment (default: now), oldest first. Page back with `before`."""
    query = select(Message).where(Message.thread_id == thread.id)
    if before:
        query = query.where(Message.created_at < before)
    newest_first = await db.scalars(query.order_by(Message.created_at.desc()).limit(limit))
    return list(reversed(list(newest_first)))


async def post_message(db: AsyncSession, *, thread: Thread, user_id: uuid.UUID, text: str) -> Message:
    message = Message(
        org_id=thread.org_id,
        thread_id=thread.id,
        author_type="user",
        author_id=user_id,
        parts=[text_part(text.strip())],
        status="complete",
        created_at=utcnow(),
    )
    db.add(message)
    thread.last_message_at = message.created_at
    await db.flush()
    return message

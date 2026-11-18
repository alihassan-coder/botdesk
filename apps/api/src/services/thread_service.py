"""Threads (DMs with a bot, and groups) and their messages.

Visibility follows the usual chat-app rule: you see a thread only if you're in it.
Bot replies come in a later slice; for now messages are stored and read back.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utcnow
from src.core.errors import BadRequest, Forbidden, NotFound
from src.models import Bot, Membership, Message, Thread, ThreadParticipant
from src.models.thread import ParticipantType
from src.schemas.thread import AuthorOut, MessageOut, ParticipantOut, ThreadOut

PREVIEW_LENGTH = 80
NOT_FOUND = "This chat doesn't exist."
LEAD_NOT_IN_GROUP = "The lead must be one of the group's bots."
NOT_IN_ORG = "Some of those people or bots aren't in this organization."


def text_part(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def text_of(parts: list[dict[str, Any]]) -> str:
    """A message's text parts, joined."""
    return "\n".join(str(part.get("text", "")) for part in parts if part.get("type") == "text")


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


async def thread_outs(db: AsyncSession, threads: list[Thread], *, user_id: uuid.UUID | None = None) -> list[ThreadOut]:
    """Threads as the API shows them. Up to four queries in total, however many threads: everyone
    in them, each thread's last message, the names of the DMs' bots, and (for `user_id`) their
    unread counts. A DM is titled with its bot's current name, so renaming a bot renames its chats."""
    if not threads:
        return []
    ids = [thread.id for thread in threads]
    unread = await _unread_counts(db, ids, user_id) if user_id else {}
    participants: dict[uuid.UUID, list[ParticipantOut]] = {thread_id: [] for thread_id in ids}
    for thread_id, kind, participant_id in await db.execute(
        select(ThreadParticipant.thread_id, ThreadParticipant.participant_type, ThreadParticipant.participant_id).where(
            ThreadParticipant.thread_id.in_(ids)
        )
    ):
        participants[thread_id].append(ParticipantOut.model_validate({"type": kind, "id": participant_id}))
    previews = await _last_message_previews(db, ids)
    dm_bots = {thread.bot_id for thread in threads if thread.kind == "dm" and thread.bot_id}
    bot_names: dict[uuid.UUID | None, str] = {}
    if dm_bots:
        bot_names = {
            bot_id: name for bot_id, name in await db.execute(select(Bot.id, Bot.name).where(Bot.id.in_(dm_bots)))
        }
    return [
        ThreadOut.model_validate(
            {
                "id": thread.id,
                "kind": thread.kind,
                "title": bot_names.get(thread.bot_id, thread.title) if thread.bot_id else thread.title,
                "bot_id": thread.bot_id,
                "lead_bot_id": thread.lead_bot_id,
                "created_by": thread.created_by,
                "participants": participants[thread.id],
                "last_message_at": thread.last_message_at,
                "last_message_preview": previews.get(thread.id, ""),
                "unread": unread.get(thread.id, 0),
            }
        )
        for thread in threads
    ]


async def thread_out(db: AsyncSession, thread: Thread, *, user_id: uuid.UUID | None = None) -> ThreadOut:
    return (await thread_outs(db, [thread], user_id=user_id))[0]


async def _unread_counts(db: AsyncSession, thread_ids: list[uuid.UUID], user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """For each thread, the messages after the person last read it that someone else wrote, in
    one query. It walks the (thread_id, created_at) index from each thread's read mark."""
    rows = await db.execute(
        select(ThreadParticipant.thread_id, func.count(Message.id))
        .join(
            Message,
            and_(Message.thread_id == ThreadParticipant.thread_id, Message.created_at > ThreadParticipant.last_read_at),
        )
        .where(
            ThreadParticipant.thread_id.in_(thread_ids),
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
            or_(Message.author_type != "user", Message.author_id.is_(None), Message.author_id != user_id),
        )
        .group_by(ThreadParticipant.thread_id)
    )
    return {thread_id: count for thread_id, count in rows}


async def mark_read(db: AsyncSession, thread: Thread, *, user_id: uuid.UUID) -> None:
    """The person has read the chat up to now. The caller commits."""
    await db.execute(
        update(ThreadParticipant)
        .where(
            ThreadParticipant.thread_id == thread.id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
        .values(last_read_at=utcnow())
    )


async def _last_message_previews(db: AsyncSession, thread_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The start of each thread's newest message, in one query.
    `row_number()` numbers each thread's messages newest first; we keep number 1.
    It uses the (thread_id, created_at) index and reads only the `parts` column."""
    newest_first = func.row_number().over(partition_by=Message.thread_id, order_by=Message.created_at.desc()).label("n")
    ranked = select(Message.thread_id, Message.parts, newest_first).where(Message.thread_id.in_(thread_ids)).subquery()
    rows = await db.execute(select(ranked.c.thread_id, ranked.c.parts).where(ranked.c.n == 1))
    return {thread_id: text_of(parts)[:PREVIEW_LENGTH] for thread_id, parts in rows}


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
    thread = await db.scalar(
        select(Thread)
        .join(ThreadParticipant, ThreadParticipant.thread_id == Thread.id)
        .where(
            Thread.id == thread_id,
            Thread.org_id == org_id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
    )
    if thread is None:
        raise NotFound(NOT_FOUND)
    return thread


def _add_participants(db: AsyncSession, thread: Thread, *, users: set[uuid.UUID], bots: set[uuid.UUID]) -> None:
    for user_id in users:
        db.add(ThreadParticipant(thread_id=thread.id, participant_type="user", participant_id=user_id))
    for bot_id in bots:
        db.add(ThreadParticipant(thread_id=thread.id, participant_type="bot", participant_id=bot_id))


async def _check_in_org(db: AsyncSession, org_id: uuid.UUID, *, users: set[uuid.UUID], bots: set[uuid.UUID]) -> None:
    """Every one of these people and bots belongs to the organization, or 404."""
    members = (
        set(
            await db.scalars(
                select(Membership.user_id).where(Membership.org_id == org_id, Membership.user_id.in_(users))
            )
        )
        if users
        else set()
    )
    org_bots = set(await db.scalars(select(Bot.id).where(Bot.org_id == org_id, Bot.id.in_(bots)))) if bots else set()
    if members != users or org_bots != bots:
        raise NotFound(NOT_IN_ORG)


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
    lead_bot_id: uuid.UUID | None = None,
) -> Thread:
    """A group with you, the people and the bots you pick. Everyone must be in the organization.
    Its lead is `lead_bot_id` (one of the bots) or, left out, the first bot picked (ADR 0009)."""
    if lead_bot_id is not None and lead_bot_id not in bot_ids:
        raise BadRequest(LEAD_NOT_IN_GROUP)
    users = {creator_id, *user_ids}
    bots = set(bot_ids)
    await _check_in_org(db, org_id, users=users, bots=bots)

    lead = lead_bot_id or (bot_ids[0] if bot_ids else None)
    thread = Thread(
        org_id=org_id, kind="group", title=title.strip(), bot_id=None, created_by=creator_id, lead_bot_id=lead
    )
    db.add(thread)
    await db.flush()
    _add_participants(db, thread, users=users, bots=bots)
    return thread


async def set_lead(
    db: AsyncSession, thread: Thread, *, user_id: uuid.UUID, role: str, bot_id: uuid.UUID | None
) -> Thread:
    """Change a group's lead, or clear it (None). Its creator, and the organization's owners and
    admins who are in it, may; other members may not (the caller already checked they're in it).
    The caller commits."""
    if thread.kind != "group":
        raise BadRequest("Only a group has a lead.")
    if thread.created_by != user_id and role not in ("owner", "admin"):
        raise Forbidden("Only the group's creator, owners and admins can change its lead.")
    await _lock(db, thread, user_id=user_id)
    if bot_id is not None:
        in_group = await db.scalar(
            select(ThreadParticipant.participant_id).where(
                ThreadParticipant.thread_id == thread.id,
                ThreadParticipant.participant_type == "bot",
                ThreadParticipant.participant_id == bot_id,
            )
        )
        if in_group is None:
            raise BadRequest(LEAD_NOT_IN_GROUP)
    thread.lead_bot_id = bot_id
    await db.flush()
    return thread


async def _check_can_manage(db: AsyncSession, thread: Thread, *, user_id: uuid.UUID, role: str) -> None:
    """A group (never a DM) whose creator, or an owner or admin of the organization, is asking
    (ADR 0009's rule for the lead). Then the group's row is locked until the caller commits, so
    changes to one group happen one at a time: two at once can't both pass a check (who's in it,
    the last person) that the other is about to break. Under the lock, the asker must still be in
    the group (someone may have removed them a moment ago)."""
    if thread.kind != "group":
        raise BadRequest("Only a group can be changed.")
    if thread.created_by != user_id and role not in ("owner", "admin"):
        raise Forbidden("Only the group's creator, owners and admins can change it.")
    await _lock(db, thread, user_id=user_id)


async def _lock(db: AsyncSession, thread: Thread, *, user_id: uuid.UUID) -> None:
    """Lock the group's row until the caller commits (Postgres; SQLite writes one at a time anyway)
    and read it again, since a change that was waiting for the lock may have moved its lead; then
    check the asker is still in it."""
    locked = select(Thread).where(Thread.id == thread.id).with_for_update()
    await db.execute(locked.execution_options(populate_existing=True))
    if not await _is_in(db, thread.id, user_id):
        raise NotFound(NOT_FOUND)


async def rename_group(db: AsyncSession, thread: Thread, *, user_id: uuid.UUID, role: str, title: str) -> Thread:
    """The caller commits."""
    name = title.strip()
    if not name:
        raise BadRequest("Give the group a name.")
    await _check_can_manage(db, thread, user_id=user_id, role=role)
    thread.title = name
    await db.flush()
    return thread


async def add_participants(
    db: AsyncSession,
    thread: Thread,
    *,
    user_id: uuid.UUID,
    role: str,
    user_ids: list[uuid.UUID],
    bot_ids: list[uuid.UUID],
) -> Thread:
    """Add people and bots of the organization; ones already in the group are skipped. A person
    added starts with nothing unread. The caller commits."""
    await _check_can_manage(db, thread, user_id=user_id, role=role)
    users, bots = set(user_ids), set(bot_ids)
    await _check_in_org(db, thread.org_id, users=users, bots=bots)
    already = set(
        await db.execute(
            select(ThreadParticipant.participant_type, ThreadParticipant.participant_id).where(
                ThreadParticipant.thread_id == thread.id
            )
        )
    )
    _add_participants(
        db,
        thread,
        users={u for u in users if ("user", u) not in already},
        bots={b for b in bots if ("bot", b) not in already},
    )
    await db.flush()
    return thread


async def remove_participant(
    db: AsyncSession,
    thread: Thread,
    *,
    user_id: uuid.UUID,
    role: str,
    kind: ParticipantType,
    participant_id: uuid.UUID,
) -> Thread:
    """Take a person or a bot out of the group. A person removed can't see it any more; removing
    the lead bot leaves the group without a lead. The last person stays. The caller commits (and
    stops the bot's unfinished runs in the group, `run_service.unfinished_in_thread`)."""
    await _check_can_manage(db, thread, user_id=user_id, role=role)
    in_group = ThreadParticipant.thread_id == thread.id
    people = list(
        await db.scalars(
            select(ThreadParticipant.participant_id).where(in_group, ThreadParticipant.participant_type == "user")
        )
    )
    if kind == "user" and participant_id in people and len(people) == 1:
        raise BadRequest("A group needs at least one person.")
    removed = await db.execute(
        delete(ThreadParticipant).where(
            in_group,
            ThreadParticipant.participant_type == kind,
            ThreadParticipant.participant_id == participant_id,
        )
    )
    if removed.rowcount == 0:  # type: ignore[attr-defined]
        raise NotFound("They aren't in this group.")
    if kind == "bot" and thread.lead_bot_id == participant_id:
        thread.lead_bot_id = None
    await db.flush()
    return thread


async def _is_in(db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await db.scalar(
        select(ThreadParticipant.participant_id).where(
            ThreadParticipant.thread_id == thread_id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
    )
    return found is not None


async def can_follow(db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether this person may still hear the chat: they're in it, and still a member of its
    organization (an open stream outlives the request that checked both). One query."""
    found = await db.scalar(
        select(ThreadParticipant.participant_id)
        .join(Thread, Thread.id == ThreadParticipant.thread_id)
        .join(
            Membership, and_(Membership.org_id == Thread.org_id, Membership.user_id == ThreadParticipant.participant_id)
        )
        .where(
            ThreadParticipant.thread_id == thread_id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
    )
    return found is not None


@dataclass
class LeftGroups:
    """What someone leaving the organization did to its groups. The caller saves `changed`'s
    `thread_updated` events, and stops the runs in `emptied` before deleting those (`delete_groups`)."""

    changed: list[ThreadOut] = field(default_factory=list)  # still have people in them
    emptied: list[uuid.UUID] = field(default_factory=list)  # nobody left: no one could reach them again


async def leave_groups(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID) -> LeftGroups:
    """Someone leaving the organization leaves its groups too, so a group shows who can really
    read it. Their DMs stay theirs (no one else is in them). The groups are locked first, in id
    order, as a group change locks its group. A group left with no person in it is to be deleted
    rather than handed to someone: its history was only ever theirs and its bots'. The caller commits."""
    theirs = select(ThreadParticipant.thread_id).where(
        ThreadParticipant.participant_type == "user", ThreadParticipant.participant_id == user_id
    )
    locked = select(Thread).where(Thread.org_id == org_id, Thread.kind == "group", Thread.id.in_(theirs))
    groups = list(await db.scalars(locked.order_by(Thread.id).with_for_update()))
    if not groups:
        return LeftGroups()
    ids = [group.id for group in groups]
    await db.execute(
        delete(ThreadParticipant).where(
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
            ThreadParticipant.thread_id.in_(ids),
        )
    )
    with_people = set(
        await db.scalars(
            select(ThreadParticipant.thread_id)
            .where(ThreadParticipant.thread_id.in_(ids), ThreadParticipant.participant_type == "user")
            .distinct()
        )
    )
    changed = await thread_outs(db, [group for group in groups if group.id in with_people])
    return LeftGroups(changed=changed, emptied=[group.id for group in groups if group.id not in with_people])


async def delete_groups(db: AsyncSession, thread_ids: list[uuid.UUID]) -> None:
    """Delete these groups with their messages and runs (stop the runs first). The caller commits."""
    if thread_ids:
        await db.execute(delete(Thread).where(Thread.id.in_(thread_ids), Thread.kind == "group"))


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

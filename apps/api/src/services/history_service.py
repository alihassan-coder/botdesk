"""Chat history (ADR 0019): the running summary each chat keeps of the messages older than what a
run reads, and deleting messages older than the organization's limit.

This module only reads and writes the database; the model call that writes a summary is in
`runtime.summarizer`, and the jobs that call both are in `jobs.tasks`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Bot, Message, Organization, RunEvent, Thread
from src.services import run_service
from src.services.run_service import HISTORY_LENGTH, SUMMARY_EVERY, ChatLine

# One summary folds in at most this many messages: a chat much older than summaries starts from
# its newest ones. Each message is cut to LINE_MAX_CHARS for it.
FOLD_MAX = 60
LINE_MAX_CHARS = 1_500


@dataclass(frozen=True)
class SummaryBatch:
    """What the next summary of one chat is made from."""

    org_id: uuid.UUID
    thread_id: uuid.UUID
    model_id: str  # the bot's model ("" = the server's default)
    summary: str | None  # the summary so far
    since: datetime | None  # what the summary so far covers up to (None = no summary yet)
    through: datetime  # the newest message folded in
    tainted: bool  # the summary so far was, or a message folded in was written by a tainted run
    lines: list[ChatLine]  # oldest first


def _conversation(thread_id: uuid.UUID, since: datetime | None) -> Any:
    """The chat's messages people and bots wrote (no notices) after `since`."""
    query = run_service.chat_lines(thread_id).where(Message.author_type != "system")
    return query if since is None else query.where(Message.created_at > since)


async def _summary_state(db: AsyncSession, thread_id: uuid.UUID) -> Any:
    return (
        await db.execute(
            select(
                Thread.org_id,
                Thread.summary,
                Thread.summary_through,
                Thread.summary_tainted,
                Organization.history_summaries,
            )
            .join(Organization, Organization.id == Thread.org_id)
            .where(Thread.id == thread_id)
        )
    ).one_or_none()


async def summary_due(db: AsyncSession, thread_id: uuid.UUID) -> bool:
    """Summaries are on and at least `SUMMARY_EVERY` messages have fallen out of the window since
    the summary. Counts at most HISTORY_LENGTH + SUMMARY_EVERY rows, however long the chat."""
    state = await _summary_state(db, thread_id)
    if state is None or not state.history_summaries:
        return False
    window = HISTORY_LENGTH + SUMMARY_EVERY
    newest = select(Message.id).where(Message.thread_id == thread_id, Message.author_type != "system")
    if state.summary_through is not None:
        newest = newest.where(Message.created_at > state.summary_through)
    count = await db.scalar(select(func.count()).select_from(newest.limit(window).subquery()))
    return (count or 0) >= window


async def next_batch(db: AsyncSession, thread_id: uuid.UUID, bot_id: uuid.UUID) -> SummaryBatch | None:
    """The messages since the summary except the newest HISTORY_LENGTH (runs read those word for
    word), at most `FOLD_MAX` of them. None when summaries are off or fewer than SUMMARY_EVERY
    would be folded in (a job that runs twice finds nothing to do the second time)."""
    state = await _summary_state(db, thread_id)
    if state is None or not state.history_summaries:
        return None
    query = _conversation(thread_id, state.summary_through)
    query = query.order_by(Message.created_at.desc(), Message.id.desc()).limit(HISTORY_LENGTH + FOLD_MAX)
    rows = list(reversed((await db.execute(query)).all()))
    fold = rows[:-HISTORY_LENGTH]
    if len(fold) < SUMMARY_EVERY:
        return None
    model_id = await db.scalar(select(Bot.model_id).where(Bot.id == bot_id))
    return SummaryBatch(
        org_id=state.org_id,
        thread_id=thread_id,
        model_id=model_id or "",
        summary=state.summary,
        since=state.summary_through,
        through=fold[-1].created_at,
        tainted=state.summary_tainted or any(row.tainted for row in fold),
        lines=await run_service.as_chat_lines(db, fold, bot_id=bot_id),
    )


async def save_summary(db: AsyncSession, batch: SummaryBatch, text: str) -> bool:
    """Keep the new summary, unless the chat's summary changed since `batch` was read (then this
    one is dropped: it was made from an older summary). The caller commits."""
    unchanged = Thread.summary_through.is_(None) if batch.since is None else Thread.summary_through == batch.since
    saved = cast(
        CursorResult[Any],
        await db.execute(
            update(Thread)
            .where(Thread.id == batch.thread_id, unchanged)
            .values(summary=text, summary_through=batch.through, summary_tainted=batch.tainted)
        ),
    )
    return saved.rowcount == 1


# Deleting old messages


async def retention_limits(db: AsyncSession) -> list[tuple[uuid.UUID, int]]:
    """Each organization that deletes old messages, with its limit in days."""
    rows = await db.execute(
        select(Organization.id, Organization.history_retention_days).where(
            Organization.history_retention_days.is_not(None)
        )
    )
    return [(org_id, days) for org_id, days in rows if days]


async def prune(db: AsyncSession, org_id: uuid.UUID, before: datetime) -> int:
    """Delete the organization's messages written before `before`, and its run events from then.
    Runs, approvals, usage and files stay, and so do chats' summaries. Returns how many messages
    were deleted. The caller commits."""
    in_org = select(Thread.id).where(Thread.org_id == org_id)
    await db.execute(delete(RunEvent).where(RunEvent.org_id == org_id, RunEvent.created_at < before))
    deleted = cast(
        CursorResult[Any],
        # By chat, so it goes over the (thread_id, created_at) index.
        await db.execute(delete(Message).where(Message.thread_id.in_(in_org), Message.created_at < before)),
    )
    return deleted.rowcount

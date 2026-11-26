"""Chat history (ADR 0019): the running summary each chat keeps of the messages older than what a
run reads, and deleting messages older than the organization's limit.

This module only reads and writes the database; the model call that writes a summary is in
`runtime.summarizer`, and the jobs that call both are in `jobs.tasks`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Bot, Message, Organization, Run, RunEvent, Thread
from src.models.run import ACTIVE_STATUSES, PAUSED_STATUSES
from src.services import run_service
from src.services.run_service import HISTORY_LENGTH, SUMMARY_EVERY, ChatLine, after_message

# One summary folds in at most this many messages, each cut to LINE_MAX_CHARS. A chat's first
# summary starts from its newest dropped messages (a chat much older than summaries doesn't pay to
# summarize all of it); after that, each one carries on from where the last stopped, so none are
# skipped even when summaries fell behind (a budget used up, a key removed for a while).
FOLD_MAX = 60
LINE_MAX_CHARS = 1_500
# Deleting old messages goes this many rows at a time, each batch its own transaction.
PRUNE_BATCH = 5_000


@dataclass(frozen=True)
class SummaryBatch:
    """What the next summary of one chat is made from."""

    org_id: uuid.UUID
    thread_id: uuid.UUID
    model_id: str  # the bot's model ("" = the server's default)
    summary: str | None  # the summary so far
    since: datetime | None  # what the summary so far covers up to (None = no summary yet)
    through: datetime  # the newest message folded in: its time…
    through_id: uuid.UUID  # …and its id
    tainted: bool  # the summary so far was, or a message folded in was written by a tainted run
    lines: list[ChatLine]  # oldest first


def _unsummarized(query: Any, state: Any) -> Any:
    """`query` limited to the messages people and bots wrote (no notices) after the summary."""
    query = query.where(Message.author_type != "system")
    if state.summary_through is None:
        return query
    return query.where(after_message(state.summary_through, state.summary_through_id))


async def _summary_state(db: AsyncSession, thread_id: uuid.UUID) -> Any:
    return (
        await db.execute(
            select(
                Thread.org_id,
                Thread.summary,
                Thread.summary_through,
                Thread.summary_through_id,
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
    newest = _unsummarized(select(Message.id).where(Message.thread_id == thread_id), state)
    count = await db.scalar(select(func.count()).select_from(newest.limit(window).subquery()))
    return (count or 0) >= window


async def next_batch(db: AsyncSession, thread_id: uuid.UUID, bot_id: uuid.UUID) -> SummaryBatch | None:
    """The next messages to fold in: those since the summary except the newest HISTORY_LENGTH (runs
    read those word for word), at most `FOLD_MAX` (see there for which). None when summaries are
    off or fewer than SUMMARY_EVERY would be folded in (a job that runs twice finds nothing to do
    the second time)."""
    state = await _summary_state(db, thread_id)
    if state is None or not state.history_summaries:
        return None
    query = _unsummarized(run_service.chat_lines(thread_id), state).limit(HISTORY_LENGTH + FOLD_MAX)
    if state.summary_through is None:  # the first summary: the newest messages that dropped out
        rows = list(reversed((await db.execute(query.order_by(Message.created_at.desc(), Message.id.desc()))).all()))
    else:  # carry on from the summary, oldest first
        rows = list((await db.execute(query.order_by(Message.created_at, Message.id))).all())
    fold = rows[: max(0, len(rows) - HISTORY_LENGTH)]
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
        through_id=fold[-1].id,
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
            .values(
                summary=text,
                summary_through=batch.through,
                summary_through_id=batch.through_id,
                summary_tainted=batch.tainted,
            )
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
    """One batch: up to `PRUNE_BATCH` of the organization's messages written before `before`, and as
    many of its run events from then. The events of runs that haven't ended stay (a paused run's
    card is rebuilt from them). Runs, approvals, usage and files stay, and so do chats' summaries.
    Returns how many rows went; the caller commits, and calls again until none do."""
    unfinished = select(Run.id).where(Run.org_id == org_id, Run.status.in_((*ACTIVE_STATUSES, *PAUSED_STATUSES)))
    old_events = (
        select(RunEvent.id)
        .where(
            RunEvent.org_id == org_id,
            RunEvent.created_at < before,
            or_(RunEvent.run_id.is_(None), RunEvent.run_id.not_in(unfinished)),
        )
        .limit(PRUNE_BATCH)
    )
    # By chat, so it goes over the (thread_id, created_at) index.
    in_org = select(Thread.id).where(Thread.org_id == org_id)
    old_messages = (
        select(Message.id).where(Message.thread_id.in_(in_org), Message.created_at < before).limit(PRUNE_BATCH)
    )
    events = cast(CursorResult[Any], await db.execute(delete(RunEvent).where(RunEvent.id.in_(old_events))))
    messages = cast(CursorResult[Any], await db.execute(delete(Message).where(Message.id.in_(old_messages))))
    return events.rowcount + messages.rowcount

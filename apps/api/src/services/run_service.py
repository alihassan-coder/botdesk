"""Runs: which bots should reply to a message, and the life of a run in the database.

A run moves queued → running → succeeded / failed / cancelled. While running it can pause:
running → waiting_approval (a risky tool call waits for a person) → running again, or
running → needs_attention (a tool may have half run; a person must look). Every change of
state is a single conditional UPDATE, so two API copies (or a double-clicked Stop) can't both win.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import NotFound
from src.core.handles import mentioned_handles
from src.models import Bot, Message, Run, RunEvent, Thread, ThreadParticipant
from src.models.run import ACTIVE_STATUSES, PAUSED_STATUSES
from src.schemas.run import RunOut
from src.services.thread_service import text_of, text_part
from src.services.tool_execution_service import runs_with_a_started_call

HISTORY_LENGTH = 30  # recent messages the bot sees
RESTART_ERROR = "Interrupted by a restart. Send your message again."
LOST_PAUSE_ERROR = "This run can't continue: its saved progress is gone (the API restarted). Send your message again."


def half_run_tool_error(tool_name: str) -> str:
    return (
        f"The API restarted while {tool_name} was running, so we can't tell whether it finished. "
        "Check before trying again."
    )


async def bots_to_reply(db: AsyncSession, *, thread: Thread, text: str) -> list[uuid.UUID]:
    """In a DM, the bot always replies. In a group, only the bots @mentioned that are in the chat."""
    if thread.kind == "dm":
        return [thread.bot_id] if thread.bot_id else []
    handles = mentioned_handles(text)
    if not handles:
        return []
    in_this_chat = select(ThreadParticipant.participant_id).where(
        ThreadParticipant.thread_id == thread.id, ThreadParticipant.participant_type == "bot"
    )
    rows = await db.execute(
        select(Bot.id, Bot.handle).where(Bot.org_id == thread.org_id, Bot.handle.in_(handles), Bot.id.in_(in_this_chat))
    )
    by_handle = {handle: bot_id for bot_id, handle in rows}
    return [by_handle[handle] for handle in handles if handle in by_handle]  # in mention order


async def create_runs(
    db: AsyncSession, *, thread: Thread, message: Message, settings: Settings, text: str
) -> list[Run]:
    """A queued run for each bot that should reply. Saved with the message, in the same transaction."""
    runs = [
        Run(
            org_id=thread.org_id,
            bot_id=bot_id,
            thread_id=thread.id,
            trigger_message_id=message.id,
            status="queued",
            max_steps=settings.run_max_steps,
            max_seconds=settings.run_max_seconds,
            created_at=utcnow(),
        )
        for bot_id in await bots_to_reply(db, thread=thread, text=text)
    ]
    db.add_all(runs)
    await db.flush()
    return runs


async def claim_run(db: AsyncSession, run_id: uuid.UUID, *, bot_cap: int, from_status: str = "queued") -> bool:
    """Try to move a queued run (or, to resume it, a run waiting for approval) to running.
    True if this caller got it.

    It only starts when it's this chat's turn: no older run in the chat is still queued, and
    the bot has fewer than `bot_cap` runs going. A partial unique index allows one running
    run per chat, so if another API copy started one a moment ago, this one fails and waits.
    (The bot cap is a plain count, so two copies starting at the same instant could pass it.)
    """
    this, other = Run, aliased(Run)
    older_queued = exists().where(
        other.thread_id == this.thread_id,
        other.status == "queued",
        other.created_at < this.created_at,
    )
    bot_running = (
        select(func.count()).select_from(other).where(other.bot_id == this.bot_id, other.status == "running")
    ).scalar_subquery()
    try:
        result = await db.execute(
            update(this)
            .where(this.id == run_id, this.status == from_status, ~older_queued, bot_running < bot_cap)
            .values(status="running", started_at=func.coalesce(this.started_at, utcnow()))
            .returning(this.id)
        )
        claimed = result.first() is not None
        await db.commit()
    except IntegrityError:  # another run in this chat is running
        await db.rollback()
        return False
    return claimed


async def run_status(db: AsyncSession, run_id: uuid.UUID) -> str | None:
    return await db.scalar(select(Run.status).where(Run.id == run_id))


async def stop_requested(db: AsyncSession, run_id: uuid.UUID) -> bool:
    return bool(await db.scalar(select(Run.stop_requested).where(Run.id == run_id)))


@dataclass(frozen=True)
class StepStart:
    steps_used: int  # before this step
    stop_requested: bool


async def start_step(db: AsyncSession, run_id: uuid.UUID) -> StepStart:
    """Count one model step and read the Stop flag, in one round trip."""
    row = (
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(steps_used=Run.steps_used + 1)
            .returning(Run.steps_used, Run.stop_requested)
        )
    ).one()
    await db.commit()
    return StepStart(steps_used=row.steps_used - 1, stop_requested=row.stop_requested)


@dataclass(frozen=True)
class RunContext:
    """What a run needs to know before it calls the model."""

    bot_name: str
    instructions: str
    model_id: str
    security_level: str
    tainted: bool
    member_id: uuid.UUID | None  # in a DM, the person the bot is talking to
    history: list[tuple[bool, str]]  # (from this bot?, text), oldest first


async def run_context(db: AsyncSession, run_id: uuid.UUID) -> RunContext:
    """The bot and the chat so far: two queries, only the columns used."""
    row = (
        await db.execute(
            select(
                Run.bot_id,
                Run.thread_id,
                Run.tainted,
                Bot.name,
                Bot.instructions,
                Bot.model_id,
                Bot.security_level,
                Thread.kind,
                Thread.created_by,
            )
            .join(Bot, Bot.id == Run.bot_id)
            .join(Thread, Thread.id == Run.thread_id)
            .where(Run.id == run_id)
        )
    ).one()
    newest_first = await db.execute(
        select(Message.author_type, Message.author_id, Message.parts)
        .where(Message.thread_id == row.thread_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LENGTH)
    )
    history = [
        (author_type == "bot" and author_id == row.bot_id, text_of(parts))
        for author_type, author_id, parts in reversed(list(newest_first))
    ]
    return RunContext(
        bot_name=row.name,
        instructions=row.instructions,
        model_id=row.model_id,
        security_level=row.security_level,
        tainted=row.tainted,
        member_id=row.created_by if row.kind == "dm" else None,
        history=history,
    )


async def save_reply(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str,
    extra_parts: list[dict[str, Any]] | None = None,
) -> Message:
    """The bot's reply becomes a message in the chat. `extra_parts` (approval cards, tool lines) go before
    the text. The caller commits. Safe to call twice: a saved reply is returned as it is."""
    run = (
        await db.execute(select(Run.org_id, Run.thread_id, Run.bot_id, Run.reply_message_id).where(Run.id == run_id))
    ).one()
    if run.reply_message_id and (saved := await db.get(Message, run.reply_message_id)):
        return saved
    message = Message(
        id=message_id,
        org_id=run.org_id,
        thread_id=run.thread_id,
        author_type="bot",
        author_id=run.bot_id,
        parts=[*(extra_parts or []), text_part(text)],
        status="complete",
        created_at=utcnow(),
    )
    db.add(message)
    await db.execute(update(Thread).where(Thread.id == run.thread_id).values(last_message_at=message.created_at))
    await db.execute(update(Run).where(Run.id == run_id).values(reply_message_id=message_id))
    return message


async def finish_run(db: AsyncSession, run_id: uuid.UUID, *, status: str, error: str | None = None) -> bool:
    """End a run that is still going. False if it had already ended (say, it was cancelled). The caller commits."""
    result = await db.execute(
        update(Run)
        .where(Run.id == run_id, Run.status.in_(ACTIVE_STATUSES))
        .values(status=status, error=error, finished_at=utcnow())
        .returning(Run.id)
    )
    return result.first() is not None


async def pause_run(db: AsyncSession, run_id: uuid.UUID, *, status: str, error: str | None = None) -> bool:
    """running → waiting_approval or needs_attention. False if the run isn't running any more
    (Stop was pressed). The caller commits."""
    result = await db.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == "running")
        .values(status=status, error=error)
        .returning(Run.id)
    )
    return result.first() is not None


async def fail_interrupted_runs(db: AsyncSession) -> list[Run]:
    """At startup: runs left queued or running by a crash or restart can't continue (yet).
    They fail, except a run whose tool call was half done: nobody can tell whether it
    happened, so that run waits for a person (needs_attention, ADR 0004 §2). Returns both
    kinds. Runs waiting for approval are untouched: they resume from their checkpoint."""
    stuck = list(await db.scalars(select(Run.id).where(Run.status.in_(ACTIVE_STATUSES))))
    half_run = await runs_with_a_started_call(db, stuck)
    attention: list[Run] = []
    for run_id, tool_name in half_run.items():
        attention += await db.scalars(
            update(Run)
            .where(Run.id == run_id, Run.status.in_(ACTIVE_STATUSES))
            .values(status="needs_attention", error=half_run_tool_error(tool_name))
            .returning(Run)
        )
    failed = await db.scalars(
        update(Run)
        .where(Run.status.in_(ACTIVE_STATUSES))
        .values(status="failed", error=RESTART_ERROR, finished_at=utcnow())
        .returning(Run)
    )
    return [*attention, *failed]


async def get_run(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    """A run in this organization, in a chat the user is in. Otherwise 404."""
    run = await db.scalar(
        select(Run)
        .join(ThreadParticipant, ThreadParticipant.thread_id == Run.thread_id)
        .where(
            Run.id == run_id,
            Run.org_id == org_id,
            ThreadParticipant.participant_type == "user",
            ThreadParticipant.participant_id == user_id,
        )
    )
    if run is None:
        raise NotFound("This run doesn't exist.")
    return run


async def request_stop(db: AsyncSession, run: Run) -> bool:
    """Stop button. A queued or paused run is cancelled on the spot (returns True); a running
    one gets a "stop requested" flag that it checks between steps (returns False). The caller commits."""
    if await cancel_if_not_running(db, run.id):
        return True
    await db.execute(update(Run).where(Run.id == run.id, Run.status == "running").values(stop_requested=True))
    return False


async def cancel_if_not_running(db: AsyncSession, run_id: uuid.UUID) -> bool:
    result = await db.execute(
        update(Run)
        .where(Run.id == run_id, Run.status.in_(("queued", *PAUSED_STATUSES)))
        .values(status="cancelled", finished_at=utcnow())
        .returning(Run.id)
    )
    return result.first() is not None


# Not finished: queued, running, or paused until a person acts.
LIVE_STATUSES = (*ACTIVE_STATUSES, *PAUSED_STATUSES)
THREAD_RUNS_LIMIT = 100


@dataclass(frozen=True)
class ThreadRuns:
    runs: list[Run]
    last_event_id: int  # the chat's newest event when the runs were read
    replay_from: int  # just before the queued/running runs' first events (`last_event_id` if none)


async def thread_runs(db: AsyncSession, thread_id: uuid.UUID, *, active: bool) -> ThreadRuns:
    """A chat's runs, newest first (only the unfinished ones when `active`), and the chat's
    newest event id, read in one statement so they describe the same moment: a stream that
    starts after that id misses nothing that changed these runs. Always one row comes back,
    even with no runs (the position is the left side of the join).

    `replay_from` is where a stream that should rebuild the streaming runs (queued or running)
    starts: just before the first event of any of them. Replaying from there brings back a
    reply's words so far and its tool lines, not only what comes after `last_event_id`.
    Paused runs don't count: their state comes from this list and the approvals list, and one
    can wait for days, so pinning the replay to its start would replay an ever-growing range on
    every page load. (Their words before the pause come back with the reply, when it's saved.)"""
    last_event_id = func.coalesce(func.max(RunEvent.id), 0)
    streaming = select(Run.id).where(Run.thread_id == thread_id, Run.status.in_(ACTIVE_STATUSES))
    first_streaming_event = (
        select(func.min(RunEvent.id))
        .where(RunEvent.thread_id == thread_id, RunEvent.run_id.in_(streaming))
        .scalar_subquery()
    )
    position = (
        select(
            last_event_id.label("last_event_id"),
            func.coalesce(first_streaming_event - 1, last_event_id).label("replay_from"),
        )
        .where(RunEvent.thread_id == thread_id)
        .subquery()
    )
    joined = [Run.thread_id == thread_id]
    if active:
        joined.append(Run.status.in_(LIVE_STATUSES))
    rows = (
        await db.execute(
            select(position.c.last_event_id, position.c.replay_from, Run)
            .select_from(position)
            .outerjoin(Run, and_(*joined))
            .order_by(Run.created_at.desc())
            .limit(THREAD_RUNS_LIMIT)
        )
    ).all()
    first = rows[0] if rows else (0, 0, None)
    return ThreadRuns(runs=[run for _, _, run in rows if run is not None], last_event_id=first[0], replay_from=first[1])


def run_out(run: Run) -> RunOut:
    return RunOut.model_validate(run)

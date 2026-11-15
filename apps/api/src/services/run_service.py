"""Runs: which bots should reply to a message, and the life of a run in the database.

A run moves queued → running → succeeded / failed / cancelled. While running it can pause:
running → waiting_approval (a risky tool call waits for a person) → running again, or
running → needs_attention (a tool may have half run; a person must look). Every change of
state is a single conditional UPDATE, so two API copies (or a double-clicked Stop) can't both win.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import NotFound
from src.core.handles import mentioned_handles
from src.models import Approval, Bot, Message, Run, RunEvent, Thread, ThreadParticipant, User
from src.models.run import ACTIVE_STATUSES, PAUSED_STATUSES
from src.schemas.run import RunOut
from src.services.mention_routing import BotAuthor, ChatBots, Reply, route
from src.services.run_event_service import add_event
from src.services.thread_service import message_out, text_of, text_part
from src.services.tool_execution_service import runs_with_a_started_call

HISTORY_LENGTH = 30  # messages the bot sees: the newest ones up to its trigger
RESTART_ERROR = "Interrupted by a restart. Send your message again."
LOST_PAUSE_ERROR = "This run can't continue: its saved progress is gone (the API restarted). Send your message again."


def half_run_tool_error(tool_name: str) -> str:
    return (
        f"The API restarted while {tool_name} was running, so we can't tell whether it finished. "
        "Check before trying again."
    )


async def _org_bots_by_handle(db: AsyncSession, *, org_id: uuid.UUID, text: str) -> dict[str, uuid.UUID]:
    """The organization's bots that the text @mentions, by handle (no query when it mentions nobody)."""
    handles = mentioned_handles(text)
    if not handles:
        return {}
    rows = await db.execute(select(Bot.handle, Bot.id).where(Bot.org_id == org_id, Bot.handle.in_(handles)))
    return {handle: bot_id for handle, bot_id in rows}


async def _chat_bots(db: AsyncSession, thread: Thread, *, with_guests: bool) -> ChatBots:
    """A group: its bots and its lead. A DM: its own bot, plus (`with_guests`) every bot already
    pulled into it, i.e. any bot that has had a run there."""
    if thread.kind == "group":
        bots = await db.scalars(
            select(ThreadParticipant.participant_id).where(
                ThreadParticipant.thread_id == thread.id, ThreadParticipant.participant_type == "bot"
            )
        )
        return ChatBots(kind="group", bots=frozenset(bots), default_bot=thread.lead_bot_id)
    guests = (
        set(await db.scalars(select(Run.bot_id).where(Run.thread_id == thread.id).distinct())) if with_guests else set()
    )
    own = {thread.bot_id} if thread.bot_id else set()
    return ChatBots(kind="dm", bots=frozenset(own | guests), default_bot=thread.bot_id)


def _queued_run(thread: Thread, reply: Reply, *, trigger: Message, settings: Settings, parent: uuid.UUID | None) -> Run:
    return Run(
        org_id=thread.org_id,
        bot_id=reply.bot_id,
        thread_id=thread.id,
        trigger_message_id=trigger.id,
        parent_run_id=parent,
        hop=reply.hop,
        status="queued",
        max_steps=settings.run_max_steps,
        max_seconds=settings.run_max_seconds,
        created_at=utcnow(),
    )


async def create_runs(
    db: AsyncSession, *, thread: Thread, message: Message, settings: Settings, text: str
) -> list[Run]:
    """A member's message: a queued run (hop 0) for each bot that should reply (see
    `mention_routing`). Saved with the message, in the same transaction."""
    routing = route(
        await _chat_bots(db, thread, with_guests=False),
        text,
        org_bots=await _org_bots_by_handle(db, org_id=thread.org_id, text=text),
        hop_limit=settings.bot_hop_limit,
    )
    runs = [_queued_run(thread, reply, trigger=message, settings=settings, parent=None) for reply in routing.replies]
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
class ChatLine:
    """One message as the run sees it."""

    from_this_bot: bool
    author_type: str  # user | bot | system
    author: str  # "Sara (@sara)"; empty when the account or bot is gone
    text: str


@dataclass(frozen=True)
class RunContext:
    """What a run needs to know before it calls the model."""

    bot_name: str
    instructions: str
    model_id: str
    security_level: str
    memory_enabled: bool
    # Set when the run itself read outside text, or its history holds a reply written by a run
    # that did (a bot quoting an email must not turn it into a clean instruction for the next run).
    tainted: bool
    group: bool
    # A bot pulled into someone's DM by an @mention (ADR 0009): it answers there once.
    guest: bool
    hop: int  # 0 when a person's message started the run, one more per bot reply since
    member_id: uuid.UUID | None  # in a DM, the person the bot is talking to (a guest's too)
    history: list[ChatLine]  # oldest first, ending with the run's trigger message


def _label(name: str | None, handle: str | None) -> str:
    return f"{name} (@{handle})" if name and handle else ""


async def run_context(db: AsyncSession, run_id: uuid.UUID) -> RunContext:
    """The bot and the chat so far, in two queries: the run with its bot, chat and trigger, then the
    last `HISTORY_LENGTH` messages up to and including the trigger, each with its author and
    whether a tainted run wrote it. A queued run answers its own message, not whatever is newest
    when its turn comes.

    When the history carries taint into a clean run, the run is marked tainted here (one UPDATE);
    the caller commits."""
    trigger = aliased(Message)
    row = (
        await db.execute(
            select(
                Run.bot_id,
                Run.thread_id,
                Run.tainted,
                Run.hop,
                Bot.name,
                Bot.instructions,
                Bot.model_id,
                Bot.security_level,
                Bot.memory_enabled,
                Thread.kind,
                Thread.bot_id.label("dm_bot_id"),
                Thread.created_by,
                trigger.created_at.label("trigger_at"),
                trigger.id.label("trigger_id"),
            )
            .join(Bot, Bot.id == Run.bot_id)
            .join(Thread, Thread.id == Run.thread_id)
            .outerjoin(trigger, trigger.id == Run.trigger_message_id)
            .where(Run.id == run_id)
        )
    ).one()
    author_bot, reply_of = aliased(Bot), aliased(Run)
    written_by_tainted_run = (
        exists()
        .where(reply_of.thread_id == row.thread_id, reply_of.reply_message_id == Message.id, reply_of.tainted)
        .label("tainted")
    )
    query = (
        select(
            Message.author_type,
            Message.author_id,
            Message.parts,
            User.name.label("user_name"),
            User.handle.label("user_handle"),
            author_bot.name.label("bot_name"),
            author_bot.handle.label("bot_handle"),
            written_by_tainted_run,
        )
        .outerjoin(User, and_(Message.author_type == "user", User.id == Message.author_id))
        .outerjoin(author_bot, and_(Message.author_type == "bot", author_bot.id == Message.author_id))
        # Notices like "Stopped a chain of bot replies" are for people, not part of the conversation.
        .where(Message.thread_id == row.thread_id, Message.author_type != "system")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(HISTORY_LENGTH)
    )
    if row.trigger_at is not None:  # up to the trigger; ties on the time go by id
        query = query.where(
            or_(
                Message.created_at < row.trigger_at,
                and_(Message.created_at == row.trigger_at, Message.id <= row.trigger_id),
            )
        )
    lines = list(reversed((await db.execute(query)).all()))
    history = [
        ChatLine(
            from_this_bot=line.author_type == "bot" and line.author_id == row.bot_id,
            author_type=line.author_type,
            author=_label(line.user_name, line.user_handle) or _label(line.bot_name, line.bot_handle),
            text=text_of(line.parts),
        )
        for line in lines
    ]
    tainted = row.tainted
    if not tainted and any(line.tainted for line in lines):
        await db.execute(update(Run).where(Run.id == run_id).values(tainted=True))
        tainted = True
    return RunContext(
        bot_name=row.name,
        instructions=row.instructions,
        model_id=row.model_id,
        security_level=row.security_level,
        memory_enabled=row.memory_enabled,
        tainted=tainted,
        group=row.kind == "group",
        guest=row.kind == "dm" and row.dm_bot_id != row.bot_id,
        hop=row.hop,
        member_id=row.created_by if row.kind == "dm" else None,
        history=history,
    )


def chain_stopped_text(hop_limit: int) -> str:
    return f"Stopped a chain of bot replies after {hop_limit} hops."


@dataclass(frozen=True)
class SavedReply:
    message: Message
    runs: list[Run]  # queued runs for the bots the reply @mentions (start them after commit)
    notice: Message | None  # "Stopped a chain…", when a mention passed the hop limit


async def save_reply(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str,
    settings: Settings,
    extra_parts: list[dict[str, Any]] | None = None,
) -> SavedReply:
    """The bot's reply becomes a message in the chat (`extra_parts`, such as approval cards and
    tool lines, go before the text), with its `message_saved` event. Bots the reply @mentions
    get queued runs one hop on (ADR 0009); past the hop limit, a system message says the chain
    stopped instead. The caller commits, then starts `runs`.

    Safe to call twice: a saved reply is returned as it is, and starts nothing again."""
    run = await db.get(Run, run_id)
    if run is None:
        raise NotFound("This run doesn't exist.")
    if run.reply_message_id and (saved := await db.get(Message, run.reply_message_id)):
        return SavedReply(message=saved, runs=[], notice=None)
    thread = await db.get(Thread, run.thread_id)
    assert thread is not None  # a run's chat is removed with it
    message = _message(thread, author_type="bot", author_id=run.bot_id, parts=[*(extra_parts or []), text_part(text)])
    message.id = message_id
    db.add(message)
    await db.flush()  # before the run points at it (no ORM relationships to order the writes)
    thread.last_message_at = message.created_at
    run.reply_message_id = message_id
    _message_saved(db, run, message)

    routing = route(
        await _chat_bots(db, thread, with_guests=True),
        text,
        org_bots=await _org_bots_by_handle(db, org_id=thread.org_id, text=text),
        hop_limit=settings.bot_hop_limit,
        by_bot=BotAuthor(bot_id=run.bot_id, hop=run.hop),
    )
    runs = [_queued_run(thread, reply, trigger=message, settings=settings, parent=run.id) for reply in routing.replies]
    db.add_all(runs)
    notice = None
    if routing.chain_stopped:
        notice = _message(
            thread, author_type="system", author_id=None, parts=[text_part(chain_stopped_text(settings.bot_hop_limit))]
        )
        db.add(notice)
        thread.last_message_at = notice.created_at  # it's the chat's preview now, so it sorts by it too
    await db.flush()
    if notice is not None:
        _message_saved(db, run, notice)
    return SavedReply(message=message, runs=runs, notice=notice)


def _message(thread: Thread, *, author_type: str, author_id: uuid.UUID | None, parts: list[dict[str, Any]]) -> Message:
    return Message(
        org_id=thread.org_id,
        thread_id=thread.id,
        author_type=author_type,
        author_id=author_id,
        parts=parts,
        status="complete",
        created_at=utcnow(),
    )


def _message_saved(db: AsyncSession, run: Run, message: Message) -> None:
    out = message_out(message).model_dump(mode="json", by_alias=True)
    add_event(
        db, org_id=run.org_id, thread_id=run.thread_id, run_id=run.id, kind="message_saved", data={"message": out}
    )


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
    """At startup on SQLite (nothing survives a restart there: jobs and checkpoints live in
    memory): runs left queued or running by a crash or restart can't continue.
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


async def runs_to_pick_up(db: AsyncSession) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(run id, chat id) of every run that should be moving: queued, running, or waiting for an
    approval that has been decided (none of its approvals is pending any more). The job queue
    gives each one without a job a new one (`RunManager.pick_up_stuck_runs`)."""
    decided = and_(
        Run.status == "waiting_approval",
        ~exists().where(Approval.run_id == Run.id, Approval.status == "pending"),
    )
    rows = await db.execute(
        select(Run.id, Run.thread_id).where(or_(Run.status.in_(ACTIVE_STATUSES), decided)).order_by(Run.created_at)
    )
    return [(run_id, thread_id) for run_id, thread_id in rows]


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

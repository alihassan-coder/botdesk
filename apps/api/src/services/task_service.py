"""Tasks (ADR 0014, the handoffs contract): the one module that knows them.

A run hands a task to a teammate bot (`hand_off`); the teammate does it in a **child run** in the
same chat, and the parent run waits (`waiting_handoff`) until all of its open tasks have ended,
then reads their results (`resume_answer`). Everything else here keeps that promise:

    queued ──→ working ──→ done | failed | cancelled
       └──────────────────→ failed | cancelled

- every change of a task is one conditional UPDATE from the statuses it may leave, so only one
  change wins (a task ended twice changes nothing the second time);
- **lock order:** the parent run's row first (`SELECT … FOR UPDATE`), then the task and the
  message holding its card. Every task change and every rewrite of a handoff message happens under
  that lock, which serialises "was that the parent's last open task?" with the parent pausing, so
  a parent is resumed exactly once (`run_ended` / `expire_overdue` / `resume_if_ready`);
- a card (the message's `handoff` part) and a `task_updated` event go with every change.

It never defers jobs or stops runs itself: it returns what the caller must do (`Aftermath`), and
the caller owns the transaction. So it's tested with a plain session.
"""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.config import Settings
from src.core.database import as_utc, utcnow
from src.models import Bot, Message, Run, Task, Thread, User
from src.models.run import FINISHED_STATUSES
from src.models.task import OPEN_TASK_STATUSES
from src.plugins.team import HandoffArgs, normalise_handle
from src.schemas.task import TaskOut
from src.services import run_event_service, tool_execution_service
from src.services.thread_service import message_out, text_of, text_part

RESULT_LIMIT = 8000  # characters of the owner's reply kept as the task's result
PREVIEW_LIMIT = 280  # characters of it on the card
STOPPED = "Stopped before it finished."
LOST_STOP_WINDOW = timedelta(days=1)  # how far back `to_reconcile` looks for children left going
CHILD_GONE = "Its run is gone (its bot or chat was removed)."


@dataclass(frozen=True)
class Aftermath:
    """What the caller must do once the change is saved: defer a `run_bot` job for each run in
    `resume` (in the same transaction), and stop each run in `stop` (after the commit)."""

    resume: list[Run] = field(default_factory=list)
    stop: list[uuid.UUID] = field(default_factory=list)

    def __add__(self, other: "Aftermath") -> "Aftermath":
        resume = {run.id: run for run in [*self.resume, *other.resume]}
        return Aftermath(resume=list(resume.values()), stop=list(dict.fromkeys([*self.stop, *other.stop])))


@dataclass(frozen=True)
class HandedOff:
    task: Task
    child: Run | None  # None only when `created` is False and the child's run is gone
    created: bool  # False: this call had already made the task (the node ran again)


@dataclass(frozen=True)
class Refused:
    message: str  # what the model is told ("The tool failed: <this>")


HandoffResult = HandedOff | Refused


# Handing off


async def hand_off(
    db: AsyncSession,
    *,
    parent_run_id: uuid.UUID,
    tool_call_id: str,
    args: HandoffArgs,
    message_id: uuid.UUID,
    reply_text: str,
    exclude_execution_ids: Collection[str],
    level: str,
    tainted: bool,
    settings: Settings,
) -> HandoffResult:
    """Check the handoff and make its task, the child run and the handoff message (or rewrite
    it with the new card), with `message_saved` and `task_updated`. The caller defers the child's
    job (when `created`) and commits. Calling it again for the same call returns the same task.

    `level` is the parent's effective security level: the child is never looser (it's kept as the
    child run's `security_level`). `tainted`: the parent's state says it read outside text."""
    parent = await _lock_run(db, parent_run_id)
    if parent is None:
        return Refused("This run is gone.")
    existing = await db.scalar(select(Task).where(Task.parent_run_id == parent.id, Task.tool_call_id == tool_call_id))
    if existing is not None:
        # The node ran again: the same task, never a second one. If its child's run is gone (its
        # bot or chat was removed), the task can't finish any more: it fails, and says why.
        child = await db.get(Run, existing.child_run_id) if existing.child_run_id else None
        if child is None and (
            gone := await _change(
                db, existing.id, OPEN_TASK_STATUSES, status="failed", error=CHILD_GONE, finished_at=utcnow()
            )
        ):
            await _show(db, gone)
            existing = gone
        return HandedOff(existing, child, created=False)
    handle = normalise_handle(args.bot)
    target = await db.scalar(select(Bot).where(Bot.org_id == parent.org_id, Bot.handle == handle))
    if refusal := await _refusal(db, parent, target, handle, settings):
        return Refused(refusal)
    assert target is not None
    thread = await db.get(Thread, parent.thread_id)
    assert thread is not None  # a run's chat goes with it
    message = await _handoff_message(db, parent, thread, message_id)
    from src.services.run_service import queued_run  # run_service imports this module

    now = utcnow()
    child = queued_run(
        thread,
        bot_id=target.id,
        trigger=message,
        settings=settings,
        requester_id=parent.requester_id,
        hop=parent.hop + 1,
        parent=parent.id,
    )
    child.id = uuid.uuid4()
    child.tainted = parent.tainted or tainted  # taint goes down the chain
    child.security_level = level  # and the level never loosens
    db.add(child)
    await db.flush()
    task = Task(
        id=uuid.uuid4(),
        org_id=parent.org_id,
        thread_id=parent.thread_id,
        parent_run_id=parent.id,
        tool_call_id=tool_call_id,
        from_bot_id=parent.bot_id,
        to_bot_id=target.id,
        to_bot_name=target.name,
        to_bot_handle=target.handle,
        child_run_id=child.id,
        message_id=message.id,
        requester_id=parent.requester_id,
        task=args.task,
        context=args.context,
        status="queued",
        created_at=now,
        deadline_at=now + timedelta(minutes=settings.handoff_timeout_minutes),
    )
    db.add(task)
    await db.flush()
    message.parts = await segment_parts(db, parent.id, message.id, reply_text, exclude_execution_ids)
    _message_saved(db, parent, message)
    _task_updated(db, task)
    return HandedOff(task, child, created=True)


async def _refusal(db: AsyncSession, parent: Run, target: Bot | None, handle: str, settings: Settings) -> str | None:
    """Why this handoff can't happen (the contract's checks, in order), or None."""
    if target is None:
        return f"There's no bot @{handle} in this organization. Your teammates are listed in your instructions."
    if target.id == parent.bot_id:
        return "You can't hand a task to yourself. Do it yourself."
    if target.id in await _bots_above(db, parent, settings.bot_hop_limit):
        return (
            f"@{handle} is already part of this chain (it handed work down to you). "
            "Do it yourself or answer with what you have."
        )
    limit = settings.bot_hop_limit
    if parent.hop + 1 > limit:
        return (
            f"Can't hand off: this run is already {parent.hop} hops from a person, and the limit is {limit}. "
            "Do it yourself or answer with what you have."
        )
    handed = await db.scalar(select(func.count()).select_from(Task).where(Task.parent_run_id == parent.id)) or 0
    if handed >= settings.handoff_max_tasks_per_run:
        return (
            f"You've already handed off {handed} tasks in this reply, the most allowed. Work with the results you have."
        )
    if db.get_bind().dialect.name == "postgresql":
        # One handoff at a time per organization counts and inserts (until this transaction ends),
        # so handoffs from different chats can't both pass the cap. SQLite serialises writers anyway.
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"tasks:{parent.org_id}"))))
    open_in_org = (
        await db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.org_id == parent.org_id, Task.status.in_(OPEN_TASK_STATUSES))
        )
        or 0
    )
    if open_in_org >= settings.handoff_max_open_tasks_per_org:
        return "Too many handed-off tasks are open in this organization right now. Do it yourself, or try again later."
    return None


async def _bots_above(db: AsyncSession, run: Run, steps: int) -> set[uuid.UUID]:
    """The bots of the runs above this one (its parent, the parent's parent…), at most `steps` up."""
    bots: set[uuid.UUID] = set()
    above = run.parent_run_id
    for _ in range(steps):
        if above is None:
            break
        row = (await db.execute(select(Run.bot_id, Run.parent_run_id).where(Run.id == above))).first()
        if row is None:
            break
        bots.add(row.bot_id)
        above = row.parent_run_id
    return bots


async def _handoff_message(db: AsyncSession, parent: Run, thread: Thread, message_id: uuid.UUID) -> Message:
    """The message holding this stretch's handoff cards (the children's trigger), from the
    parent's bot. Made the first time; its `created_at` never changes after that."""
    message = await db.get(Message, message_id)
    if message is not None:
        return message
    message = Message(
        id=message_id,
        org_id=parent.org_id,
        thread_id=parent.thread_id,
        author_type="bot",
        author_id=parent.bot_id,
        parts=[],
        status="complete",
        created_at=utcnow(),
    )
    db.add(message)
    await db.flush()
    thread.last_message_at = message.created_at
    return message


async def segment_parts(
    db: AsyncSession,
    run_id: uuid.UUID,
    message_id: uuid.UUID,
    reply_text: str,
    exclude_execution_ids: Collection[str],
) -> list[dict[str, Any]]:
    """One of the run's messages: its approval and tool-line cards not shown before (never
    `team.*`), its text, then one handoff card per task it holds, oldest first."""
    parts = await tool_execution_service.reply_cards(db, run_id, exclude_execution_ids=exclude_execution_ids)
    if reply_text.strip():
        parts.append(text_part(reply_text))
    tasks = await db.scalars(select(Task).where(Task.message_id == message_id).order_by(Task.created_at, Task.id))
    return [*parts, *(handoff_part(task) for task in tasks)]


async def save_segment(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    message_id: uuid.UUID,
    reply_text: str,
    exclude_execution_ids: Collection[str],
) -> Message | None:
    """Rewrite the handoff message with every card of this step (a later call in the same step
    may have added one), with `message_saved`. Safe to call twice. None if it doesn't exist."""
    run = await _lock_run(db, run_id)
    message = await db.get(Message, message_id, populate_existing=True)
    if run is None or message is None:
        return None
    message.parts = await segment_parts(db, run_id, message_id, reply_text, exclude_execution_ids)
    _message_saved(db, run, message)
    return message


# The life of a task


async def child_started(db: AsyncSession, run_id: uuid.UUID) -> None:
    """The child run was claimed for the first time: its task is `working`. Nothing for a run
    that isn't a task's child (or whose task already moved on). The caller commits."""
    task = await db.scalar(select(Task).where(Task.child_run_id == run_id, Task.status == "queued"))
    if task is None:
        return
    await _lock_run(db, task.parent_run_id)
    if changed := await _change(db, task.id, ("queued",), status="working", started_at=utcnow()):
        await _show(db, changed)


async def run_ended(
    db: AsyncSession, run_id: uuid.UUID, *, status: str, error: str | None, code: str | None
) -> Aftermath:
    """A run ended (`succeeded`, `failed` or `cancelled`). The caller commits, then resumes and
    stops what this returns.

    - If it was a task's child, the task ends with it: `done` with its reply, or `failed` (with
      `budget`, or `stopped` after a person's Stop). A tainted child taints its parent. The parent
      is resumed when that was its last open task.
    - If it still had open tasks of its own, they're cancelled and their children are stopped."""
    aftermath = Aftermath()
    task = await db.scalar(select(Task).where(Task.child_run_id == run_id))
    if task is not None:
        aftermath += await _end_for_child(db, task.id, task.parent_run_id, run_id, status, error, code)
    return aftermath + await _cancel_open_tasks(db, run_id)


async def _end_for_child(
    db: AsyncSession,
    task_id: uuid.UUID,
    parent_id: uuid.UUID,
    child_id: uuid.UUID,
    status: str,
    error: str | None,
    code: str | None,
) -> Aftermath:
    parent = await _lock_run(db, parent_id)
    child = await db.get(Run, child_id, populate_existing=True)
    if parent is None or child is None:
        return Aftermath()
    now = utcnow()
    if status == "succeeded":
        reply = await db.get(Message, child.reply_message_id) if child.reply_message_id else None
        text = text_of(reply.parts) if reply is not None else ""
        ended = await _change(
            db,
            task_id,
            OPEN_TASK_STATUSES,
            status="done",
            result=text[:RESULT_LIMIT],
            result_message_id=child.reply_message_id,
            finished_at=now,
        )
    elif status == "failed":
        ended = await _change(
            db,
            task_id,
            OPEN_TASK_STATUSES,
            status="failed",
            error=error or child.error or "It failed.",
            error_code="budget" if code == "budget" else None,
            finished_at=now,
        )
    else:  # cancelled: a person pressed Stop on the child
        ended = await _change(
            db, task_id, OPEN_TASK_STATUSES, status="failed", error=STOPPED, error_code="stopped", finished_at=now
        )
    if ended is None:
        return Aftermath()  # it had already ended (timed out, or its parent ended first)
    return await _task_ended(db, parent, ended, child)


async def _cancel_open_tasks(db: AsyncSession, run_id: uuid.UUID) -> Aftermath:
    """The run ended before its tasks did: each is cancelled, and its child must stop."""
    if not await _has_open_tasks(db, run_id):
        return Aftermath()
    run = await _lock_run(db, run_id)
    if run is None:
        return Aftermath()
    bot_name = await db.scalar(select(Bot.name).where(Bot.id == run.bot_id)) or "The bot"
    stop: list[uuid.UUID] = []
    for task_id in list(await db.scalars(_open_tasks_of(run_id).with_only_columns(Task.id))):
        ended = await _change(
            db,
            task_id,
            OPEN_TASK_STATUSES,
            status="cancelled",
            error=f"Cancelled: {bot_name} stopped before it finished.",
            finished_at=utcnow(),
        )
        if ended is not None:
            await _show(db, ended)
            if ended.child_run_id is not None:
                stop.append(ended.child_run_id)
    return Aftermath(stop=stop)


async def resume_if_ready(db: AsyncSession, parent_run_id: uuid.UUID) -> Run | None:
    """The parent just paused for its tasks: the run, if every one of them has already ended
    (resume it now), else None (the last one to end will). Takes the parent's lock."""
    parent = await _lock_run(db, parent_run_id)
    return parent if parent is not None and await _ready(db, parent) else None


async def resume_answer(
    db: AsyncSession, parent_run_id: uuid.UUID, task_ids: Sequence[str] | None = None
) -> dict[str, Any] | None:
    """What the parent's `wait_for_tasks` resumes with, or None while any of its tasks is open.
    `task_ids`: the tasks named in its interrupt (all of the run's tasks when None)."""
    if await _has_open_tasks(db, parent_run_id):
        return None
    child = aliased(Run)
    query = (
        select(
            Task,
            func.coalesce(Bot.name, Task.to_bot_name),
            func.coalesce(Bot.handle, Task.to_bot_handle),
            child.tainted,
        )
        .outerjoin(Bot, Bot.id == Task.to_bot_id)
        .outerjoin(child, child.id == Task.child_run_id)
        .where(Task.parent_run_id == parent_run_id)
        .order_by(Task.created_at, Task.id)
    )
    if task_ids is not None:
        query = query.where(Task.id.in_([uuid.UUID(task_id) for task_id in task_ids]))
    rows = (await db.execute(query)).all()
    return {
        "tasks": [
            {
                "taskId": str(task.id),
                "task": task.task,
                "botName": name,
                "botHandle": handle,
                "status": task.status,
                "result": task.result if task.status == "done" else None,
                "error": task.error,
            }
            for task, name, handle, _ in rows
        ],
        "tainted": any(bool(tainted) for *_, tainted in rows),
    }


def _open_tasks_with(bot_id: uuid.UUID) -> Any:
    return select(Task).where(
        Task.status.in_(OPEN_TASK_STATUSES), or_(Task.to_bot_id == bot_id, Task.from_bot_id == bot_id)
    )


async def parents_with_open_tasks_of(db: AsyncSession, bot_id: uuid.UUID) -> list[uuid.UUID]:
    """The parent runs with an open task handed to this bot or by it, in id order."""
    query = _open_tasks_with(bot_id).with_only_columns(Task.parent_run_id).distinct().order_by(Task.parent_run_id)
    return list(await db.scalars(query))


async def bot_removed(db: AsyncSession, bot_id: uuid.UUID, parent_run_id: uuid.UUID) -> Aftermath:
    """A bot is about to be removed (its runs, and its DMs, go with it), so nothing may wait for
    it: end this parent's open tasks that involve it, under the parent's lock. A task handed
    **to** it fails ("Sales was removed before it finished.") and the parent may resume; a task
    handed **by** its run is cancelled. Their children are returned in `stop`.

    The caller does this for each of `parents_with_open_tasks_of(bot)`, one short transaction
    each (resume, commit), then stops the runs, then deletes the bot."""
    parent = await _lock_run(db, parent_run_id)
    if parent is None:
        return Aftermath()
    name = await db.scalar(select(Bot.name).where(Bot.id == bot_id)) or "The bot"
    aftermath = Aftermath()
    query = _open_tasks_with(bot_id).where(Task.parent_run_id == parent.id).order_by(Task.created_at, Task.id)
    for task in list(await db.scalars(query)):
        if task.to_bot_id == bot_id:
            values = {"status": "failed", "error": f"{name} was removed before it finished."}
        else:
            values = {"status": "cancelled", "error": f"Cancelled: {name} was removed before it finished."}
        ended = await _change(db, task.id, OPEN_TASK_STATUSES, finished_at=utcnow(), **values)
        if ended is None:
            continue
        if ended.status == "failed":
            aftermath += await _task_ended(db, parent, ended, None)
        else:
            await _show(db, ended)
        if ended.child_run_id is not None:
            aftermath += Aftermath(stop=[ended.child_run_id])
    return aftermath


# Timeouts and recovery


async def overdue(db: AsyncSession, *, limit: int = 100, now: datetime | None = None) -> list[uuid.UUID]:
    """Open tasks past their deadline, oldest deadline first."""
    rows = await db.scalars(
        select(Task.id)
        .where(Task.status.in_(OPEN_TASK_STATUSES), Task.deadline_at <= (now or utcnow()))
        .order_by(Task.deadline_at)
        .limit(limit)
    )
    return list(rows)


async def expire_overdue(db: AsyncSession, task_id: uuid.UUID, *, now: datetime | None = None) -> Aftermath:
    """One task past its deadline fails as timed out (card and event). Its parent resumes if that
    was its last open task, and its child is returned in `stop`. Nothing if it ended meanwhile."""
    task = await db.get(Task, task_id)
    if task is None or as_utc(task.deadline_at) > (now or utcnow()):
        return Aftermath()
    parent = await _lock_run(db, task.parent_run_id)
    minutes = round((as_utc(task.deadline_at) - as_utc(task.created_at)).total_seconds() / 60)
    ended = await _change(
        db,
        task_id,
        OPEN_TASK_STATUSES,
        status="failed",
        error=f"Timed out after {minutes} minutes.",
        error_code="timeout",
        finished_at=utcnow(),
    )
    if ended is None or parent is None:
        return Aftermath()
    child = await db.get(Run, ended.child_run_id, populate_existing=True) if ended.child_run_id else None
    aftermath = await _task_ended(db, parent, ended, child)
    return aftermath + Aftermath(stop=[ended.child_run_id] if ended.child_run_id else [])


async def to_reconcile(db: AsyncSession, *, limit: int = 100) -> list[uuid.UUID]:
    """The safety net's work list (recovery, every minute): parent runs with something to put
    right, in id order, at most `limit`. A parent is listed when it has an open task whose child
    already finished (or is gone), it has ended with tasks still open, a task of it ended while
    its child is still going (a timeout whose stop was lost), or it waits for tasks that have all
    ended. `reconcile` each one in its own short transaction."""
    child, parent = aliased(Run), aliased(Run)
    is_open = Task.status.in_(OPEN_TASK_STATUSES)
    tasks = (
        select(Task.parent_run_id.label("run_id"))
        .join(parent, parent.id == Task.parent_run_id)
        .outerjoin(child, child.id == Task.child_run_id)
        .where(
            or_(
                and_(is_open, or_(Task.child_run_id.is_(None), child.status.in_(FINISHED_STATUSES))),
                and_(is_open, parent.status.in_(FINISHED_STATUSES)),
                # Recently ended tasks only, so the pass never scans the whole history.
                and_(~is_open, Task.finished_at >= utcnow() - LOST_STOP_WINDOW, child.status.not_in(FINISHED_STATUSES)),
            )
        )
    )
    waiting = select(Run.id.label("run_id")).where(Run.status == "waiting_handoff", ~_open_tasks_of(Run.id).exists())
    both = union(tasks, waiting).subquery()
    return list(await db.scalars(select(both.c.run_id).order_by(both.c.run_id).limit(limit)))


async def reconcile(db: AsyncSession, parent_run_id: uuid.UUID) -> Aftermath:
    """Put one parent right, under its lock only (so passes never deadlock): end each open task
    whose child already finished, the way `run_ended` would (or fail it if the child is gone);
    cancel its open tasks if it has ended; stop the children still going after their task ended;
    and resume it if it waits for tasks that have all ended. The caller commits."""
    parent = await _lock_run(db, parent_run_id)
    if parent is None:
        return Aftermath()
    aftermath = Aftermath()
    child = aliased(Run)
    rows = (
        await db.execute(
            select(Task.id, Task.status, Task.child_run_id, child.status, child.error)
            .outerjoin(child, child.id == Task.child_run_id)
            .where(Task.parent_run_id == parent.id)
            .order_by(Task.created_at, Task.id)
        )
    ).all()
    for task_id, task_status, child_id, child_status, error in rows:
        if task_status not in OPEN_TASK_STATUSES:
            if child_id is not None and child_status not in FINISHED_STATUSES:
                aftermath += Aftermath(stop=[child_id])
        elif child_id is None:
            if ended := await _change(
                db, task_id, OPEN_TASK_STATUSES, status="failed", error=CHILD_GONE, finished_at=utcnow()
            ):
                aftermath += await _task_ended(db, parent, ended, None)
        elif child_status in FINISHED_STATUSES:
            aftermath += await _end_for_child(db, task_id, parent.id, child_id, child_status, error, None)
    if parent.status in FINISHED_STATUSES:
        aftermath += await _cancel_open_tasks(db, parent.id)
    elif await _ready(db, parent):
        aftermath += Aftermath(resume=[parent])
    return aftermath


# Shapes


def preview(result: str | None) -> str | None:
    """The first 280 characters of a result, whitespace collapsed; None when there's none."""
    if not result:
        return None
    return " ".join(result.split())[:PREVIEW_LIMIT] or None


def handoff_part(task: Task) -> dict[str, Any]:
    """The task's card: a `handoff` message part (stored in `messages.parts`, served as is)."""
    return {
        "type": "handoff",
        "taskId": str(task.id),
        "fromBotId": str(task.from_bot_id) if task.from_bot_id else None,
        "toBotId": str(task.to_bot_id) if task.to_bot_id else None,
        "task": task.task,
        "status": task.status,
        "resultMessageId": str(task.result_message_id) if task.result_message_id else None,
        "resultPreview": preview(task.result),
        "error": task.error,
        "errorCode": task.error_code,
    }


def task_json(task: Task) -> dict[str, Any]:
    """TaskOut: the whole state of the task (the `task_updated` event's `data.task`)."""
    out = TaskOut.model_validate(
        {
            "id": task.id,
            "thread_id": task.thread_id,
            "parent_run_id": task.parent_run_id,
            "child_run_id": task.child_run_id,
            "message_id": task.message_id,
            "from_bot_id": task.from_bot_id,
            "to_bot_id": task.to_bot_id,
            "task": task.task,
            "status": task.status,
            "result_message_id": task.result_message_id,
            "result_preview": preview(task.result),
            "error": task.error,
            "error_code": task.error_code,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "deadline_at": task.deadline_at,
        }
    )
    return out.model_dump(mode="json", by_alias=True)


async def handoff_lines(db: AsyncSession, parts: list[dict[str, Any]]) -> list[str]:
    """How another run reads a handoff message's cards in its history:
    `(handed @sales a task: "Draft openers", done)`, one line per card."""
    cards = [part for part in parts if part.get("type") == "handoff"]
    if not cards:
        return []
    ids = {uuid.UUID(str(card["toBotId"])) for card in cards if card.get("toBotId")}
    handles = dict((await db.execute(select(Bot.id, Bot.handle).where(Bot.id.in_(ids)))).tuples().all())
    lines = []
    for card in cards:
        to_bot = card.get("toBotId")
        handle = handles.get(uuid.UUID(str(to_bot)), "a teammate") if to_bot else "a teammate"
        task = str(card.get("task", "")).replace('"', "'")
        lines.append(f'(handed @{handle} a task: "{task}", {card.get("status", "queued")})')
    return lines


async def requester_name(db: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    return await db.scalar(select(User.name).where(User.id == user_id)) if user_id else None


# Inside


async def _lock_run(db: AsyncSession, run_id: uuid.UUID) -> Run | None:
    """The run's row, locked until the transaction ends (SQLite serialises writers anyway)."""
    return await db.scalar(
        select(Run).where(Run.id == run_id).with_for_update().execution_options(populate_existing=True)
    )


def _open_tasks_of(run_id: Any) -> Any:
    return select(Task).where(Task.parent_run_id == run_id, Task.status.in_(OPEN_TASK_STATUSES))


async def _has_open_tasks(db: AsyncSession, run_id: uuid.UUID) -> bool:
    return bool(await db.scalar(_open_tasks_of(run_id).exists().select()))


async def _ready(db: AsyncSession, parent: Run) -> bool:
    """The parent waits for tasks and none is open any more: it should resume."""
    return parent.status == "waiting_handoff" and not await _has_open_tasks(db, parent.id)


async def _task_ended(db: AsyncSession, parent: Run, ended: Task, child: Run | None) -> Aftermath:
    """A task of this (locked) parent just ended, however it ended: its card and event; a tainted
    child taints the parent (in its row: the parent's state learns it from `resume_answer`); and
    the parent resumes if that was its last open task."""
    await _show(db, ended)
    if child is not None and child.tainted and not parent.tainted:
        await db.execute(update(Run).where(Run.id == parent.id).values(tainted=True))
    return Aftermath(resume=[parent]) if await _ready(db, parent) else Aftermath()


async def _change(db: AsyncSession, task_id: uuid.UUID, from_statuses: Sequence[str], **values: Any) -> Task | None:
    """One conditional UPDATE: the task, changed, if it was in `from_statuses`; else None."""
    result = await db.scalars(
        update(Task)
        .where(Task.id == task_id, Task.status.in_(from_statuses))
        .values(**values)
        .returning(Task)
        .execution_options(populate_existing=True)
    )
    return result.first()


async def _show(db: AsyncSession, task: Task) -> None:
    """The task changed: rewrite its card in place (every other part of the message kept), and
    send `task_updated` on the parent run."""
    if task.message_id is not None:
        message = await db.get(Message, task.message_id, populate_existing=True)
        if message is not None:
            card, key = handoff_part(task), str(task.id)
            message.parts = [
                card if part.get("type") == "handoff" and part.get("taskId") == key else part for part in message.parts
            ]
    _task_updated(db, task)


def _task_updated(db: AsyncSession, task: Task) -> None:
    run_event_service.add_event(
        db,
        org_id=task.org_id,
        thread_id=task.thread_id,
        run_id=task.parent_run_id,
        kind="task_updated",
        data={"task": task_json(task)},
    )


def _message_saved(db: AsyncSession, run: Run, message: Message) -> None:
    out = message_out(message).model_dump(mode="json", by_alias=True)
    run_event_service.add_event(
        db, org_id=run.org_id, thread_id=run.thread_id, run_id=run.id, kind="message_saved", data={"message": out}
    )

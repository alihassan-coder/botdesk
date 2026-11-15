"""Routines: saved tasks a bot repeats on a schedule, and firing them.

Firing a routine (on its schedule, or Run now) happens in one transaction:

1. Checks: its bot still exists, its creator is still in the organization, and the bot and the
   organization are under budget. On schedule, a routine that fails a check is switched off with
   the reason (`disabled_reason`); Run now just says why it can't.
2. Its previous run must have finished: a slot that comes while it's still going (say, waiting
   for an approval) is recorded as `skipped`, so runs never pile up.
3. In the creator's DM with the bot (opened if missing), a system message "Routine: {name}"
   carries the routine's instructions in a `routine-run` part; a queued run (hop 0) answers it.
   The run acts for the creator (the requester: their DM) at the strictest of the bot's and the
   routine's security levels (`run_service.run_context`).

A slot missed while the server was down runs once when it's back (its `next_run_at` is in the
past), then the schedule carries on from now: never a backlog.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.errors import Conflict, Forbidden, NotFound
from src.models import Bot, Membership, Message, Run, Thread
from src.models.routine import Routine, RoutineRun
from src.schemas.routine import RoutineIn, RoutineOut, RoutineRunOut, RoutineUpdate
from src.services import bot_service, run_service, thread_service, usage_service
from src.services.routine_schedule import check_schedule, next_run
from src.services.run_event_service import add_event

NOT_FOUND = "This routine doesn't exist."
NOT_ALLOWED = "Only the routine's creator, owners and admins can change it."
STILL_GOING = "This routine's last run is still going."
BOT_REMOVED = bot_service.BOT_REMOVED
CREATOR_LEFT = "Its creator left the organization."
RECENT_RUNS = 20
# Reading


async def _last_results(db: AsyncSession, routine_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each routine's latest result: its run's status, or "skipped"."""
    if not routine_ids:
        return {}
    newest = func.row_number().over(partition_by=RoutineRun.routine_id, order_by=RoutineRun.started_at.desc())
    ranked = (
        select(RoutineRun.routine_id, RoutineRun.status, Run.status.label("run_status"), newest.label("n"))
        .outerjoin(Run, Run.id == RoutineRun.run_id)
        .where(RoutineRun.routine_id.in_(routine_ids))
        .subquery()
    )
    rows = await db.execute(select(ranked.c.routine_id, ranked.c.status, ranked.c.run_status).where(ranked.c.n == 1))
    return {routine_id: run_status or status for routine_id, status, run_status in rows}


def _out(routine: Routine, last_result: str | None) -> RoutineOut:
    return RoutineOut.model_validate(routine).model_copy(update={"last_result": last_result})


async def routine_outs(db: AsyncSession, routines: list[Routine]) -> list[RoutineOut]:
    results = await _last_results(db, [r.id for r in routines])
    return [_out(r, results.get(r.id)) for r in routines]


async def list_routines(db: AsyncSession, org_id: uuid.UUID, *, bot_id: uuid.UUID | None = None) -> list[Routine]:
    query = select(Routine).where(Routine.org_id == org_id)
    if bot_id:
        query = query.where(Routine.bot_id == bot_id)
    return list(await db.scalars(query.order_by(Routine.created_at)))


async def get_routine(db: AsyncSession, org_id: uuid.UUID, routine_id: uuid.UUID) -> Routine:
    routine = await db.get(Routine, routine_id)
    if routine is None or routine.org_id != org_id:
        raise NotFound(NOT_FOUND)
    return routine


async def recent_runs(db: AsyncSession, routine: Routine) -> list[RoutineRunOut]:
    rows = await db.execute(
        select(RoutineRun, Run.thread_id, Run.status, Run.error)
        .outerjoin(Run, Run.id == RoutineRun.run_id)
        .where(RoutineRun.routine_id == routine.id)
        .order_by(RoutineRun.started_at.desc())
        .limit(RECENT_RUNS)
    )
    return [
        RoutineRunOut(
            id=row.id,
            run_id=row.run_id,
            thread_id=thread_id,
            started_at=row.started_at,
            status=run_status or row.status,
            error=error,
        )
        for row, thread_id, run_status, error in rows
    ]


# Saving


def require_can_change(routine: Routine, *, user_id: uuid.UUID, role: str) -> None:
    if routine.created_by != user_id and role not in ("owner", "admin"):
        raise Forbidden(NOT_ALLOWED)


def _reschedule(routine: Routine, now: datetime) -> None:
    routine.next_run_at = next_run(routine.cron, routine.timezone, after=now) if routine.enabled else None


async def create_routine(
    db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID, data: RoutineIn, now: datetime
) -> Routine:
    await bot_service.get_bot(db, org_id, data.bot_id)
    check_schedule(data.cron, data.timezone)
    routine = Routine(org_id=org_id, created_by=user_id, **data.model_dump())
    _reschedule(routine, now)
    db.add(routine)
    await db.flush()
    return routine


async def update_routine(db: AsyncSession, routine: Routine, changes: RoutineUpdate, *, now: datetime) -> Routine:
    fields = changes.model_dump(exclude_unset=True)
    for required in ("bot_id", "name", "instructions", "cron", "timezone", "enabled"):
        if fields.get(required, ...) is None:
            fields.pop(required)  # null means "unchanged" for these
    if "bot_id" in fields:
        await bot_service.get_bot(db, routine.org_id, fields["bot_id"])
    check_schedule(fields.get("cron", routine.cron), fields.get("timezone", routine.timezone))
    for field, value in fields.items():
        setattr(routine, field, value)
    if fields.get("enabled"):
        if routine.bot_id is None:
            raise Conflict("Pick a bot for this routine first: its bot was removed.")
        routine.disabled_reason = None
    if {"cron", "timezone", "enabled"} & fields.keys():
        _reschedule(routine, now)
    return routine


async def delete_routine(db: AsyncSession, routine: Routine) -> None:
    await db.delete(routine)


def _system_message(db: AsyncSession, thread: Thread, parts: list[dict[str, Any]]) -> Message:
    message = Message(
        org_id=thread.org_id,
        thread_id=thread.id,
        author_type="system",
        author_id=None,
        parts=parts,
        status="complete",
    )
    db.add(message)
    return message


async def _saved(db: AsyncSession, message: Message, thread: Thread, run_id: uuid.UUID | None) -> None:
    await db.flush()
    thread.last_message_at = message.created_at
    out = thread_service.message_out(message).model_dump(mode="json", by_alias=True)
    add_event(db, org_id=thread.org_id, thread_id=thread.id, run_id=run_id, kind="message_saved", data={"message": out})


async def announce_created(db: AsyncSession, routine: Routine) -> Thread:
    """The "Created a routine" card in the creator's DM with the bot. The caller commits."""
    assert routine.bot_id and routine.created_by
    thread = await thread_service.open_dm(db, org_id=routine.org_id, user_id=routine.created_by, bot_id=routine.bot_id)
    part = {"type": "routine-created", "routineId": str(routine.id), "name": routine.name}
    message = _system_message(db, thread, [part])
    await _saved(db, message, thread, None)
    return thread


# Firing


async def due(db: AsyncSession, now: datetime) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(Routine.id).where(Routine.enabled, Routine.next_run_at <= now).order_by(Routine.next_run_at)
    )
    return list(rows)


@dataclass(frozen=True)
class Fired:
    run: Run | None  # the queued run to start after commit; None if nothing started
    thread_id: uuid.UUID | None = None
    problem: str | None = None  # why it couldn't run (switched off on schedule)


async def _problem(db: AsyncSession, routine: Routine, now: datetime) -> str | None:
    if routine.bot_id is None or await db.get(Bot, routine.bot_id) is None:
        return BOT_REMOVED
    member = routine.created_by and await db.scalar(
        select(Membership.user_id).where(Membership.org_id == routine.org_id, Membership.user_id == routine.created_by)
    )
    if not member:
        return CREATOR_LEFT
    return await usage_service.budget_stop(db, org_id=routine.org_id, bot_id=routine.bot_id, estimate_usd=0.0, now=now)


async def _still_going(db: AsyncSession, routine: Routine) -> bool:
    last = await db.scalar(
        select(Run.status)
        .join(RoutineRun, RoutineRun.run_id == Run.id)
        .where(RoutineRun.routine_id == routine.id)
        .order_by(RoutineRun.started_at.desc())
        .limit(1)
    )
    return last in run_service.LIVE_STATUSES


async def _start(db: AsyncSession, routine: Routine, *, now: datetime, settings: Settings) -> Run:
    assert routine.bot_id and routine.created_by  # checked by _problem
    thread = await thread_service.open_dm(db, org_id=routine.org_id, user_id=routine.created_by, bot_id=routine.bot_id)
    trigger = _system_message(
        db,
        thread,
        [
            thread_service.text_part(f"Routine: {routine.name}"),
            {
                "type": run_service.ROUTINE_RUN_PART,
                "routineId": str(routine.id),
                "name": routine.name,
                "instructions": routine.instructions,
            },
        ],
    )
    await db.flush()
    run = run_service.queued_run(thread, bot_id=routine.bot_id, trigger=trigger, settings=settings)
    db.add(run)
    await db.flush()
    await _saved(db, trigger, thread, run.id)
    db.add(RoutineRun(routine_id=routine.id, run_id=run.id, started_at=now, status="started"))
    routine.last_run_at = now
    return run


async def fire_on_schedule(db: AsyncSession, routine_id: uuid.UUID, *, now: datetime, settings: Settings) -> Fired:
    """The every-minute job, for one due routine. Safe to run twice: the routine's row is locked
    and must still be due, and firing moves `next_run_at` past `now`. The caller commits, then
    starts the run."""
    routine = await db.scalar(select(Routine).where(Routine.id == routine_id).with_for_update())
    if routine is None or not routine.enabled or routine.next_run_at is None or routine.next_run_at > now:
        return Fired(run=None)
    if problem := await _problem(db, routine, now):
        routine.enabled, routine.next_run_at, routine.disabled_reason = False, None, problem
        return Fired(run=None, problem=problem)
    _reschedule(routine, now)
    if await _still_going(db, routine):
        db.add(RoutineRun(routine_id=routine.id, run_id=None, started_at=now, status="skipped"))
        return Fired(run=None)
    run = await _start(db, routine, now=now, settings=settings)
    return Fired(run=run, thread_id=run.thread_id)


async def run_now(db: AsyncSession, routine: Routine, *, now: datetime, settings: Settings) -> Run:
    """Run now: the same run as on schedule, without moving the schedule. The caller commits."""
    if problem := await _problem(db, routine, now):
        raise Conflict(problem)
    if await _still_going(db, routine):
        raise Conflict(STILL_GOING)
    return await _start(db, routine, now=now, settings=settings)

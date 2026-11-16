"""Routines: saved tasks a bot repeats on a schedule, and firing them.

Firing a routine (on its schedule, or Run now) happens in one transaction:

1. Checks: its bot still exists and its creator is still in the organization. On schedule, a
   routine that fails one is switched off with the reason (`disabled_reason`): only these two
   switch a routine off. Run now just says why it can't.
2. The bot and the organization must be under budget, and its previous run must have finished
   (say, not waiting for an approval). Otherwise the slot is recorded as `skipped` with the
   reason and the routine moves on to its next slot, so runs never pile up and a new month's
   budget picks it up again.
3. In the creator's DM with the bot (opened if missing), a system message "Routine: {name}"
   carries the routine's instructions in a `routine-run` part; a queued run (hop 0) answers it.
   The run acts for the creator (the requester: their DM) at the strictest of the bot's and the
   routine's security levels, kept on the run (`Run.security_level`) so a routine removed or
   loosened mid-run can't loosen it.

A slot missed while the server was down runs once when it's back (its `next_run_at` is in the
past), then the schedule carries on from now: never a backlog.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.errors import Conflict, Forbidden, NotFound
from src.models import Bot, Membership, Message, Run, Thread
from src.models.bot import SecurityLevel
from src.models.routine import Routine, RoutineRun
from src.runtime.policy import strictest_level
from src.schemas.routine import RoutineIn, RoutineOut, RoutineRunOut, RoutineUpdate
from src.services import bot_service, run_service, thread_service, usage_service
from src.services.routine_schedule import check_schedule, next_run
from src.services.run_event_service import add_event

NOT_FOUND = "This routine doesn't exist."
NOT_ALLOWED = "Only the routine's creator, owners and admins can change it."
CREATOR_ONLY = "Only the routine's creator can edit it or run it now: its runs act for them."
RUNS_HIDDEN = "Only the routine's creator, owners and admins can see its runs."
STILL_GOING = "This routine's last run is still going."
BOT_REMOVED = bot_service.BOT_REMOVED
CREATOR_LEFT = "Its creator left the organization."
RECENT_RUNS = 20
# History kept per routine: the newest `KEEP_RUNS`, none older than `KEEP_FOR`.
KEEP_RUNS = 200
KEEP_FOR = timedelta(days=90)
# Reading


async def _last_results(db: AsyncSession, routine_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each routine's latest result: its run's status, or "skipped". One query that reads only the
    newest row per routine (a correlated LIMIT 1 over the (routine_id, started_at) index)."""
    if not routine_ids:
        return {}
    newest = (
        select(RoutineRun.id)
        .where(RoutineRun.routine_id == Routine.id)
        .order_by(RoutineRun.started_at.desc(), RoutineRun.id.desc())
        .limit(1)
        .correlate(Routine)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Routine.id, RoutineRun.status, Run.status)
        .join(RoutineRun, RoutineRun.id == newest)
        .outerjoin(Run, Run.id == RoutineRun.run_id)
        .where(Routine.id.in_(routine_ids))
    )
    return {routine_id: run_status or status for routine_id, status, run_status in rows}


@dataclass(frozen=True)
class Viewer:
    user_id: uuid.UUID
    role: str  # owner | admin | member

    def manages(self, routine: Routine) -> bool:
        """The routine's creator, owners and admins: they read its instructions and runs, and can
        switch it on or off or remove it."""
        return routine.created_by == self.user_id or self.role in ("owner", "admin")


def _out(routine: Routine, last_result: str | None, viewer: Viewer) -> RoutineOut:
    out = RoutineOut.model_validate(routine)
    # Everyone sees what runs when; only those who manage it read what it does.
    instructions = out.instructions if viewer.manages(routine) else None
    return out.model_copy(update={"last_result": last_result, "instructions": instructions})


async def routine_outs(db: AsyncSession, routines: list[Routine], viewer: Viewer) -> list[RoutineOut]:
    results = await _last_results(db, [r.id for r in routines])
    return [_out(r, results.get(r.id), viewer) for r in routines]


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


async def recent_runs(db: AsyncSession, routine: Routine, viewer: Viewer) -> list[RoutineRunOut]:
    if not viewer.manages(routine):
        raise Forbidden(RUNS_HIDDEN)
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
            reason=row.reason,
        )
        for row, thread_id, run_status, error in rows
    ]


# Saving


def require_can_manage(routine: Routine, viewer: Viewer) -> None:
    """Switching it on or off, and removing it: its creator, owners and admins."""
    if not viewer.manages(routine):
        raise Forbidden(NOT_ALLOWED)


def require_creator(routine: Routine, viewer: Viewer) -> None:
    """Editing it and Run now: only its creator, since its runs act for them (their DM, their
    connections). An admin who could change its instructions would act as that member."""
    if routine.created_by != viewer.user_id:
        raise Forbidden(CREATOR_ONLY)


def _changes(routine: Routine, changes: RoutineUpdate) -> dict[str, Any]:
    """The fields `changes` really changes (null means "unchanged" for the required ones)."""
    fields = changes.model_dump(exclude_unset=True)
    for required in ("bot_id", "name", "instructions", "cron", "timezone", "enabled"):
        if fields.get(required, ...) is None:
            fields.pop(required)
    return {field: value for field, value in fields.items() if getattr(routine, field) != value}


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


async def update_routine(
    db: AsyncSession, routine: Routine, changes: RoutineUpdate, *, viewer: Viewer, now: datetime
) -> Routine:
    """Only the fields that change are checked: owners and admins may switch a member's routine
    on or off, but anything else is its creator's alone."""
    fields = _changes(routine, changes)
    if fields.keys() - {"enabled"}:
        require_creator(routine, viewer)
    else:
        require_can_manage(routine, viewer)
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


async def delete_routine(db: AsyncSession, routine: Routine, viewer: Viewer) -> None:
    require_can_manage(routine, viewer)
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


async def prune_runs(db: AsyncSession, now: datetime) -> None:
    """Forget routine runs older than `KEEP_FOR`, and all but each routine's newest `KEEP_RUNS`.
    The runs themselves (and their chats) stay. The caller commits."""
    await db.execute(delete(RoutineRun).where(RoutineRun.started_at < now - KEEP_FOR))
    rank = func.row_number().over(
        partition_by=RoutineRun.routine_id, order_by=(RoutineRun.started_at.desc(), RoutineRun.id.desc())
    )
    ranked = select(RoutineRun.id, rank.label("n")).subquery()
    beyond = select(ranked.c.id).where(ranked.c.n > KEEP_RUNS)
    await db.execute(delete(RoutineRun).where(RoutineRun.id.in_(beyond)))


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
    problem: str | None = None  # why it was switched off
    skipped: str | None = None  # why this slot didn't run


async def _gone(db: AsyncSession, routine: Routine) -> str | None:
    """Why the routine can't run at all (its bot or its creator is gone), or None."""
    if routine.bot_id is None or await db.get(Bot, routine.bot_id) is None:
        return BOT_REMOVED
    member = routine.created_by and await db.scalar(
        select(Membership.user_id).where(Membership.org_id == routine.org_id, Membership.user_id == routine.created_by)
    )
    return None if member else CREATOR_LEFT


async def _wait(db: AsyncSession, routine: Routine, now: datetime) -> str | None:
    """Why it can't run right now (over budget, or its last run is still going), or None."""
    assert routine.bot_id  # checked by _gone
    if stop := await usage_service.budget_stop(
        db, org_id=routine.org_id, bot_id=routine.bot_id, estimate_usd=0.0, now=now
    ):
        return stop
    return STILL_GOING if await _still_going(db, routine) else None


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
    assert routine.bot_id and routine.created_by  # checked by _gone
    bot = await db.get(Bot, routine.bot_id)
    assert bot is not None  # checked by _gone
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
    # The member who set the routine up is its runs' requester (their DM with the bot, too).
    run = run_service.queued_run(
        thread, bot_id=routine.bot_id, trigger=trigger, settings=settings, requester_id=routine.created_by
    )
    # The strictest of the bot's and the routine's levels, kept on the run (ADR 0004).
    bot_level = cast("SecurityLevel", bot.security_level)
    run.security_level = strictest_level(bot_level, cast("SecurityLevel", routine.security_level or bot_level))
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
    if problem := await _gone(db, routine):
        routine.enabled, routine.next_run_at, routine.disabled_reason = False, None, problem
        return Fired(run=None, problem=problem)
    _reschedule(routine, now)
    if reason := await _wait(db, routine, now):
        db.add(RoutineRun(routine_id=routine.id, run_id=None, started_at=now, status="skipped", reason=reason))
        return Fired(run=None, skipped=reason)
    run = await _start(db, routine, now=now, settings=settings)
    return Fired(run=run, thread_id=run.thread_id)


async def run_now(db: AsyncSession, routine: Routine, *, viewer: Viewer, now: datetime, settings: Settings) -> Run:
    """Run now (its creator only): the same run as on schedule, without moving the schedule.
    The caller commits."""
    require_creator(routine, viewer)
    if problem := await _gone(db, routine) or await _wait(db, routine, now):
        raise Conflict(problem)
    return await _start(db, routine, now=now, settings=settings)

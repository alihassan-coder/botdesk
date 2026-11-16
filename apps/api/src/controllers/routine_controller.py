"""Handles routine requests. Any member can create a routine for a bot of the organization and
sees every routine's name and schedule. Only its creator edits it or runs it now (its runs act
for them, in their DM); its creator, owners and admins read its instructions and runs, switch it
on or off and remove it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.database import utcnow
from src.models import Routine
from src.runtime.runner import RunManager
from src.schemas.routine import RoutineIn, RoutineOut, RoutineRunOut, RoutineUpdate, RunNowOut
from src.services import routine_service


def _viewer(access: Access) -> routine_service.Viewer:
    return routine_service.Viewer(user_id=access.user.id, role=access.role)


async def list_routines(db: AsyncSession, access: Access, bot_id: uuid.UUID | None) -> list[RoutineOut]:
    routines = await routine_service.list_routines(db, access.org.id, bot_id=bot_id)
    return await routine_service.routine_outs(db, routines, _viewer(access))


async def _one(db: AsyncSession, access: Access, routine: Routine) -> RoutineOut:
    [out] = await routine_service.routine_outs(db, [routine], _viewer(access))
    return out


async def create_routine(db: AsyncSession, access: Access, runs: RunManager, body: RoutineIn) -> RoutineOut:
    routine = await routine_service.create_routine(
        db, org_id=access.org.id, user_id=access.user.id, data=body, now=utcnow()
    )
    thread = await routine_service.announce_created(db, routine)
    await db.commit()
    runs.bus.announce(thread.id)
    return await _one(db, access, routine)


async def update_routine(db: AsyncSession, access: Access, routine_id: uuid.UUID, body: RoutineUpdate) -> RoutineOut:
    routine = await routine_service.get_routine(db, access.org.id, routine_id)
    await routine_service.update_routine(db, routine, body, viewer=_viewer(access), now=utcnow())
    await db.commit()
    return await _one(db, access, routine)


async def delete_routine(db: AsyncSession, access: Access, routine_id: uuid.UUID) -> None:
    routine = await routine_service.get_routine(db, access.org.id, routine_id)
    await routine_service.delete_routine(db, routine, _viewer(access))
    await db.commit()


async def run_now(db: AsyncSession, access: Access, runs: RunManager, routine_id: uuid.UUID) -> RunNowOut:
    routine = await routine_service.get_routine(db, access.org.id, routine_id)
    run = await routine_service.run_now(db, routine, viewer=_viewer(access), now=utcnow(), settings=runs.settings)
    await runs.start(db, [run])
    await db.commit()
    runs.bus.announce(run.thread_id)
    return RunNowOut(run_id=run.id, thread_id=run.thread_id)


async def recent_runs(db: AsyncSession, access: Access, routine_id: uuid.UUID) -> list[RoutineRunOut]:
    routine = await routine_service.get_routine(db, access.org.id, routine_id)
    return await routine_service.recent_runs(db, routine, _viewer(access))

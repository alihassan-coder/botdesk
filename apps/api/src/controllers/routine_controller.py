"""Handles routine requests. Any member can create a routine for a bot of the organization; the
routine's creator, owners and admins can change, run or remove it. Runs go to the creator's DM."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.database import utcnow
from src.models import Routine
from src.runtime.runner import RunManager
from src.schemas.routine import RoutineIn, RoutineOut, RoutineRunOut, RoutineUpdate, RunNowOut
from src.services import routine_service


async def list_routines(db: AsyncSession, access: Access, bot_id: uuid.UUID | None) -> list[RoutineOut]:
    routines = await routine_service.list_routines(db, access.org.id, bot_id=bot_id)
    return await routine_service.routine_outs(db, routines)


async def _one(db: AsyncSession, routine: Routine) -> RoutineOut:
    [out] = await routine_service.routine_outs(db, [routine])
    return out


async def create_routine(db: AsyncSession, access: Access, runs: RunManager, body: RoutineIn) -> RoutineOut:
    routine = await routine_service.create_routine(
        db, org_id=access.org.id, user_id=access.user.id, data=body, now=utcnow()
    )
    thread = await routine_service.announce_created(db, routine)
    await db.commit()
    runs.bus.announce(thread.id)
    return await _one(db, routine)


async def _changeable(db: AsyncSession, access: Access, routine_id: uuid.UUID) -> Routine:
    routine = await routine_service.get_routine(db, access.org.id, routine_id)
    routine_service.require_can_change(routine, user_id=access.user.id, role=access.role)
    return routine


async def update_routine(db: AsyncSession, access: Access, routine_id: uuid.UUID, body: RoutineUpdate) -> RoutineOut:
    routine = await _changeable(db, access, routine_id)
    await routine_service.update_routine(db, routine, body, now=utcnow())
    await db.commit()
    return await _one(db, routine)


async def delete_routine(db: AsyncSession, access: Access, routine_id: uuid.UUID) -> None:
    await routine_service.delete_routine(db, await _changeable(db, access, routine_id))
    await db.commit()


async def run_now(db: AsyncSession, access: Access, runs: RunManager, routine_id: uuid.UUID) -> RunNowOut:
    routine = await _changeable(db, access, routine_id)
    run = await routine_service.run_now(db, routine, now=utcnow(), settings=runs.settings)
    await runs.start(db, [run])
    await db.commit()
    runs.bus.announce(run.thread_id)
    return RunNowOut(run_id=run.id, thread_id=run.thread_id)


async def recent_runs(db: AsyncSession, access: Access, routine_id: uuid.UUID) -> list[RoutineRunOut]:
    routine = await routine_service.get_routine(db, access.org.id, routine_id)
    return await routine_service.recent_runs(db, routine)

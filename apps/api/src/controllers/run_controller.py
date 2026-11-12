"""Handles run requests: look at a run, or stop it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.runner import RunManager
from src.schemas.run import RunOut
from src.services import run_event_service, run_service


async def get_run(db: AsyncSession, access: Access, run_id: uuid.UUID) -> RunOut:
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    return run_service.run_out(run)


async def cancel_run(db: AsyncSession, access: Access, runs: RunManager, run_id: uuid.UUID) -> RunOut:
    """Stop a run. Stopping one that already ended changes nothing."""
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    if await run_service.request_stop(db, run):  # it hadn't started: cancelled right here
        run_event_service.add_event(
            db,
            org_id=run.org_id,
            thread_id=run.thread_id,
            run_id=run.id,
            kind="run_finished",
            data={"status": "cancelled"},
        )
    await db.commit()
    runs.bus.announce(run.thread_id)
    runs.stop_now(run.id)  # if it's running in this process, stop it now, not at its next step
    await db.refresh(run)
    return run_service.run_out(run)

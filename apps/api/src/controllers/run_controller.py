"""Handles run requests: look at a run, or stop it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.runner import RunManager
from src.schemas.run import RunOut
from src.services import approval_service, run_event_service, run_service


async def get_run(db: AsyncSession, access: Access, run_id: uuid.UUID) -> RunOut:
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    return run_service.run_out(run)


async def cancel_run(db: AsyncSession, access: Access, runs: RunManager, run_id: uuid.UUID) -> RunOut:
    """Stop a run. Stopping one that already ended changes nothing. A run waiting for approval
    stops at once, and its pending approval expires."""
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    if await run_service.request_stop(db, run):  # it wasn't running: cancelled right here
        for approval_id in await approval_service.expire_for_run(db, run.id):
            view = await approval_service.view_by_id(db, approval_id)
            run_event_service.add_event(
                db,
                org_id=run.org_id,
                thread_id=run.thread_id,
                run_id=run.id,
                kind="approval_decided",
                data={"approval": approval_service.approval_json(view, runs.registry)},
            )
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

"""Handles run requests: look at a run, or stop it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.runner import RunManager
from src.schemas.run import RunOut
from src.services import run_service


async def get_run(db: AsyncSession, access: Access, run_id: uuid.UUID) -> RunOut:
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    return run_service.run_out(run)


async def cancel_run(db: AsyncSession, access: Access, runs: RunManager, run_id: uuid.UUID) -> RunOut:
    """Stop a run (`RunManager.stop`). Stopping one that already ended changes nothing. A paused
    run stops at once: its pending approval expires, and the tasks it handed off are cancelled.
    Stopping a task's child fails only that task."""
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    await db.commit()  # end this read before the stop's own transaction
    await runs.stop(run.id)
    await db.refresh(run)
    return run_service.run_out(run)

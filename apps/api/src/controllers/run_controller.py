"""Handles run requests: look at a run, stop it, or answer one that needs attention."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.runner import RunManager
from src.runtime.tool_pipeline import finished_event
from src.schemas.run import ResolveIn, RunOut
from src.services import run_event_service, run_service


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


async def resolve_run(db: AsyncSession, access: Access, runs: RunManager, run_id: uuid.UUID, body: ResolveIn) -> RunOut:
    """It was done / It wasn't done, for a run that needs attention. The answer, its tool line
    (`tool_finished` with the real status) and the job that resumes the run are saved in one
    transaction, like an approval's decision. The resumed run reads the answer; the call never
    runs again."""
    run = await run_service.get_run(db, org_id=access.org.id, user_id=access.user.id, run_id=run_id)
    call = await run_service.resolve_attention(db, run, user_id=access.user.id, done=body.outcome == "done")
    run_event_service.add_event(
        db,
        org_id=run.org_id,
        thread_id=run.thread_id,
        run_id=run.id,
        kind="tool_finished",
        data=finished_event(call.id, call.tool_name, result=call.result, error=call.error),
    )
    await runs.resume(db, run)
    await db.commit()
    runs.bus.announce(run.thread_id)
    return run_service.run_out(run)

"""BotDesk's background jobs (ADR 0013). `JOBS` is the registry every worker runs.

- `run_bot` (deferred): move one run forward (`RunManager.take_turn`).
- `expire_approvals` (every minute): approvals nobody answered in `APPROVAL_EXPIRY_HOURS`
  expire, and their runs carry on told "no" (approvals fail closed, ADR 0004).
- `recover_runs` (every minute): tasks whose child already ended are closed, children still going
  after their task ended are stopped, and parents resume (`RunManager.reconcile_tasks`, one short
  transaction per parent); on Postgres, runs that should be moving but lost their job (a
  crashed worker) get one again.
- `expire_tasks` (every minute): handed-off tasks past their deadline fail as timed out, their
  children are stopped, and parents whose last task that was resume (ADR 0014).
- `fire_routines` (every minute): each routine that is due starts a run in its creator's DM
  (`routine_service`).
- `prune_routine_runs` (daily): routine runs older than 90 days, or beyond each routine's
  newest 200, are forgotten.

To add a job (routines, Gmail polling…), declare it on `JOBS` in a module this one imports, then
defer it with `queue.defer(Job("name", {...}))`, or give it a `cron` to run on a schedule. See the
backend guide, "Background jobs".
"""

import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from src.core.database import utcnow
from src.jobs.queue import JobEnv, JobRegistry
from src.models import Run, Task
from src.runtime.runner import RUN_BOT, run_job
from src.services import approval_service, routine_service, run_event_service, task_service

JOBS = JobRegistry()
log = logging.getLogger(__name__)

# A run that can't start yet (its chat's turn, or its bot is busy) tries again this much later.
# A new job, not a retry: it goes to the back of its chat's line, behind the run it waits for.
TURN_RETRY = timedelta(seconds=1)


@JOBS.task(RUN_BOT, retry_after_shutdown=True)
async def run_bot(env: JobEnv, run_id: str, thread_id: str) -> None:
    if not await env.runs.take_turn(uuid.UUID(run_id)):
        job = run_job(uuid.UUID(run_id), uuid.UUID(thread_id))
        await env.queue.defer(replace(job, run_at=utcnow() + TURN_RETRY))


@JOBS.task("expire_approvals", cron="* * * * *")
async def expire_approvals(env: JobEnv, timestamp: int) -> None:
    """Each overdue approval in its own short transaction: expired, its `approval_decided` event,
    and the job that resumes its run (the run reads "expired" and carries on told no)."""
    async with env.sessionmaker() as db:
        overdue = await approval_service.overdue(db)
    for approval_id in overdue:
        async with env.sessionmaker() as db:
            if not await approval_service.expire(db, approval_id):
                continue  # someone decided it meanwhile
            view = await approval_service.view_by_id(db, approval_id)
            approval = view.approval
            run_event_service.add_event(
                db,
                org_id=approval.org_id,
                thread_id=approval.thread_id,
                run_id=approval.run_id,
                kind="approval_decided",
                data={"approval": approval_service.approval_json(view, env.runs.registry)},
            )
            run = await db.get(Run, approval.run_id)
            if run is not None and run.status == "waiting_approval":
                await env.runs.resume(db, run)
            await db.commit()
        env.runs.bus.announce(approval.thread_id)


@JOBS.task("recover_runs", cron="* * * * *")
async def recover_runs(env: JobEnv, timestamp: int) -> None:
    await env.runs.reconcile_tasks()
    if env.settings.uses_postgres:  # on SQLite no job is lost while the process runs
        await env.runs.pick_up_stuck_runs()


@JOBS.task("expire_tasks", cron="* * * * *")
async def expire_tasks(env: JobEnv, timestamp: int) -> None:
    """Each overdue task in its own short transaction: failed as timed out (card and event), and
    its parent's job when that was its last open task. Then its child is stopped; the child's own
    end finds the task already ended and changes nothing."""
    async with env.sessionmaker() as db:
        overdue = await task_service.overdue(db)
    for task_id in overdue:
        async with env.sessionmaker() as db:
            aftermath = await task_service.expire_overdue(db, task_id)
            task = await db.get(Task, task_id)
            for parent in aftermath.resume:
                await env.runs.resume(db, parent)
            await db.commit()
        if task is not None:
            env.runs.bus.announce(task.thread_id)
        for child_id in aftermath.stop:
            await env.runs.stop(child_id)


@JOBS.task("fire_routines", cron="* * * * *")
async def fire_routines(env: JobEnv, timestamp: int) -> None:
    """Each due routine in its own short transaction: its trigger message, its run and the run's
    job together. `timestamp` is the minute this job is for, so a late job fires what was due
    then, and running it twice fires nothing twice (the routine moved on to its next slot). One
    routine that fails is logged and left for the next minute: the others still fire."""
    now = datetime.fromtimestamp(timestamp, UTC)
    async with env.sessionmaker() as db:
        due = await routine_service.due(db, now)
    for routine_id in due:
        try:
            async with env.sessionmaker() as db:
                fired = await routine_service.fire_on_schedule(db, routine_id, now=now, settings=env.settings)
                if fired.run is not None:
                    await env.runs.start(db, [fired.run])
                await db.commit()
        except Exception:
            log.exception("Routine %s failed to fire; the other due routines carry on.", routine_id)
            continue
        if fired.thread_id is not None:
            env.runs.bus.announce(fired.thread_id)


@JOBS.task("prune_routine_runs", cron="17 3 * * *")
async def prune_routine_runs(env: JobEnv, timestamp: int) -> None:
    """Once a day: keep each routine's history short (`routine_service.prune_runs`)."""
    async with env.sessionmaker() as db:
        await routine_service.prune_runs(db, datetime.fromtimestamp(timestamp, UTC))
        await db.commit()

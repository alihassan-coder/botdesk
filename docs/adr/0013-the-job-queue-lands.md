# 0013: The job queue lands

- Status: accepted
- Date: 2026-11-15
- Supersedes: [ADR 0007](0007-runs-in-the-api-process-for-now.md) (runs started inside the API process)
- Finishes: [ADR 0005](0005-job-queue-and-scaling.md) decisions 1–4 (job queue, worker modes, API ↔ worker through Postgres only, `LISTEN/NOTIFY` for live events)

## Context

ADR 0007 started runs as asyncio tasks inside the API, with a chat lock, a database guard and an in-process event bus. It said when to revisit: before approvals that wait for a person, routines or triggers, or more than one API copy. All of these are now close: approvals wait for days and must expire without anyone clicking, and the owner decided that the Gmail new-email trigger and routines run as scheduled jobs on this queue, with no pollers inside the API process (ADR 0011 amendment rejected). A restart also stopped every reply half way.

## Decision

1. **Runs are jobs.** Posting a message, a reply that @mentions bots, and deciding an approval each save a `run_bot` job **in the same transaction** as the run or the decision (procrastinate defers through the caller's connection). The run and its job exist together or not at all. The job carries only ids; `RunManager.take_turn` reads what to do from the database, so running a job twice is harmless:
   - `queued` → start it (when it's the chat's turn);
   - `waiting_approval` whose approval was decided or expired → resume the checkpoint with the answer read from the approval (`approved`/`edited` → yes, `denied` → no, `expired` → no, told it expired);
   - `running` → a restart interrupted it: carry on from the last saved LangGraph step;
   - anything else → nothing.
2. **One run at a time per chat:** every run job of a chat shares the procrastinate lock `chat:{thread_id}`, so they run one at a time in the order they were saved. The database guard from ADR 0007 stays as defence in depth (a partial unique index, and `claim_run`'s conditional `UPDATE` that also enforces the per-bot cap of `BOT_MAX_RUNNING_RUNS`). A run that can't start yet ends its job and defers a new one a second later, at the back of the chat's line, so it never blocks the run it waits for.
3. **Where the worker runs:** `WORKER_MODE=embedded` (default) runs procrastinate's worker inside the API process; `WORKER_MODE=separate` makes the API only add jobs, and `python -m src.worker` (a `worker` service in docker compose) runs them. Same code, same image. The embedded path is the supported default; `separate` is a thin entrypoint on top of it.
4. **Restarts:** a worker that stops waits 5 seconds for running jobs, then aborts them and puts their jobs back in the queue; the run stays `running` and carries on after the restart. A worker that dies without stopping (a crash) is noticed by its missing heartbeat, and its jobs are put back by the `recover_runs` job (at worker start, then every minute), which also gives a job to any run that should be moving but has none. A tool call that was half done is never run again blindly: the tool pipeline stops the run as `needs_attention`, as before. The "Interrupted by a restart" failure stays **only on SQLite**, where jobs and checkpoints live in memory and nothing can resume.
5. **Timers:** periodic jobs are declared with a cron line on the job registry (`JOBS.task("name", cron="* * * * *")`, `src/jobs/tasks.py`); delayed jobs are deferred with `Job(..., run_at=...)`. `expire_approvals` runs every minute: each pending approval past `APPROVAL_EXPIRY_HOURS` becomes `expired` (its tool call denied, an `approval_decided` event saved) and its run resumes told "no". Routines and Gmail polling use the same hook.
6. **Live events across processes:** every transaction that saves `run_events` sends `NOTIFY botdesk_run_events, '<chat id>'` (in the statement that already takes the chat's advisory lock, so no extra round trip). Each API process `LISTEN`s on one connection to the direct address and wakes its streams. The in-process bus stays for events saved in the same process, and streams still re-read every 5 seconds as a fallback.
7. **Connections:** the queue's pool and both `LISTEN` connections use `DATABASE_URL_DIRECT` (Neon's direct address: `LISTEN` doesn't work through a transaction pooler). Idle connections are tested before use and recycled before Neon's 5 minutes (`IdleCheck`, as for every other pool); a dead `LISTEN` connection is replaced, and the embedded worker restarts itself after a failure.
8. **Schema:** procrastinate's SQL schema (pinned to 3.11.0, vendored in `apps/api/migrations/sql/`) is applied by an Alembic migration, so `alembic upgrade head` stays the one migration step. Upgrading procrastinate means a new migration with its SQL migration files; the dependency is pinned below the next minor version.

## Consequences

- The queue needs Postgres. On SQLite an in-process adapter (`LocalQueue`) keeps the same interface, so local development without Postgres still works, but nothing survives a restart there.
- `JobQueue` (`src/jobs/queue.py`) is the seam: `defer`, `abort` (Stop reaches a run on any worker), `recover`, `wait_until_idle`. Two adapters: `ProcrastinateQueue` and `LocalQueue`.
- A running worker polls and sends heartbeats, so a Neon compute with a worker attached never suspends.
- A run resumed after a restart repeats the model step it was in (its words so far stream again; the step counts again). A stalled worker that wasn't really dead (a 60-second network stall) could see its job put back and run twice; tool calls stay idempotent by their `tool_executions` row.
- Stop on a run in another process goes through procrastinate's abort (notified at once, polled every 10 s as a fallback).

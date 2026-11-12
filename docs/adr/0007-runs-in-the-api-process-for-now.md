# 0007: Runs start inside the API process, for now

- Status: accepted
- Date: 2026-11-12
- Changes: [ADR 0005](0005-job-queue-and-scaling.md) decisions 1 and 2 (the job queue and the worker) are deferred

## Context

ADR 0005 chose procrastinate as a job queue from the first agent step, with a worker that runs inside the API or as its own process. For the first slice (bots reply in chat) the owner wants fewer moving parts: one process, one database, and code a learner can follow from the message to the reply.

## Decision

1. **No job queue yet.** Posting a message saves the message and a `queued` run in one transaction. The API then starts the run itself, as an asyncio task it keeps track of (so the task isn't garbage-collected), and logs and fails the run if anything goes wrong.
2. **One run at a time per chat**, two ways:
   - an asyncio lock per chat, so runs in this process take turns in order;
   - a database guard that holds across API copies: a partial unique index allows one `running` run per chat, and a run starts only with a conditional `UPDATE` (queued → running, if no older run in the chat is still queued and the bot has fewer than 2 running).
3. **After a restart**, runs left `queued` or `running` are marked `failed` with "Interrupted by a restart. Send your message again."
4. **Everything else from ADR 0004 and 0005 stays:** `runs`, `run_events` (the SSE stream replays from it with `Last-Event-ID`), the LangGraph Postgres checkpointer keyed by run id, and the rule that a run only talks to the rest of the app through the database. Live updates use an in-process bus; streams also re-check `run_events` every few seconds.
5. **procrastinate is still the planned queue** when we need it. Adding it changes who *starts* a run (a job instead of `RunManager.start`), not what a run does.

## Trade-offs

- **A restart stops a reply half way.** The person sees the run fail and sends the message again. With the queue, a worker would pick it up.
- **One API process is the supported setup.** A second copy keeps the one-run-per-chat rule (the database guard) and its streams still see every event (they re-check the table), but a restart of any copy fails every unfinished run, and live updates from another copy arrive a few seconds late. Running many copies needs the queue and the Postgres `LISTEN/NOTIFY` bus.
- **The per-bot cap is a plain count**, so two copies starting runs at the same instant could pass it.
- **Nothing runs on a timer yet** (approval expiry, routines). Those need the queue's scheduled jobs and arrive with it.

## When to revisit

Before any of: approvals that wait for a person (build step 2), routines or triggers, or running more than one API copy.

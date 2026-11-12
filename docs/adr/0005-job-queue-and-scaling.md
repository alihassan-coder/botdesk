# 0005: Job queue, worker and how BotDesk scales

> **Partly deferred by [ADR 0007](0007-runs-in-the-api-process-for-now.md):** no job queue or worker yet; runs start inside the API process.

- Status: accepted
- Date: 2026-11-12
- Based on: [architecture review](../architecture/review-2026-11-12.md) (findings 2, 4, 5) and [agents-and-plugins.md §12 Scaling](../architecture/agents-and-plugins.md)

## Context

Bot runs take seconds to days. If they run inside a web request, a restart kills them, nothing fires approval expiry or routines, and nothing stops two copies of the same run. Self-hosters also need BotDesk to stay simple to run: the fewer services, the better.

## Decisions

1. **Job queue: [procrastinate](https://github.com/procrastinate-org/procrastinate)** (MIT). It runs on **Postgres only**, so no Redis is needed, and its queueing locks give us "one run per chat". It's used from the first agent step.
2. **The worker lives inside `apps/api`.** It's a second entrypoint in the same code and the same image. There's no `apps/worker`. Two modes:
   - `WORKER_MODE=embedded` (default for local work): the worker runs inside the API process.
   - `WORKER_MODE=separate`: API and worker run as separate processes. Scale them independently.
3. **The API and the worker talk only through Postgres:** jobs, `run_events` and notifications. That rule is what makes splitting them later a configuration change, not a rewrite.
4. **Live updates (streaming):** the worker writes each event to `run_events` and announces it with Postgres `LISTEN/NOTIFY`. The API streams events to browsers over SSE, and a reconnecting browser catches up with `Last-Event-ID`. Valkey pub/sub is an optional profile for very large installs.
5. **Database connections:** the API may use Neon's pooled address. The queue and `LISTEN` need the **direct** (unpooled) address, set as `DATABASE_URL_DIRECT`. Migrations run once, as their own step, not on every API boot.
6. **Tests touching the runtime run on real Postgres** (Docker locally, a Postgres service in CI). SQLite stays only for pure-logic tests.
7. **Row-level security in Postgres** comes before hosted sign-ups open. Tenancy tests (one org can never see another's rows) are written now.

## Scaling stages

| Stage | What runs | When |
|---|---|---|
| 1 · Laptop | One process: API + embedded worker + Postgres | Development, small self-hosts |
| 2 · Server | API and worker as two processes (docker compose) | A team in production |
| 3 · Many | Several API and worker replicas, pooled connections, optional Valkey | Hosted service, large orgs |

## Consequences

- New settings: `WORKER_MODE`, `DATABASE_URL_DIRECT`.
- A `deploy/docker-compose.yml` arrives with stage 2, before the first public release.
- The build order gains a step 0: Postgres for tests, and CI (CI is already running).

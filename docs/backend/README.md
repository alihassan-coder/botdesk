# Backend guide (apps/api)

The BotDesk API: one backend for the web, desktop and mobile apps. Python, FastAPI, SQLAlchemy, Alembic. Why this stack: [ADR 0003](../adr/0003-python-backend.md).

## Run it

You need [uv](https://docs.astral.sh/uv/) and Python 3.13 (uv can install it: `uv python install 3.13`).

```bash
uv sync --all-packages   # from the repo root: the API, plugin SDK and plugins into .venv (one uv workspace)
cd apps/api
cp .env.example .env     # then set DATABASE_URL (Neon) — or leave it unset for local SQLite
cd ../..
pnpm dev:api             # applies migrations, then serves http://localhost:8000
```

Open **http://localhost:8000/api/docs** to see and try every route.

| Command (repo root) | What it does |
|---|---|
| `pnpm dev:api` | Migrate, then run the API with auto-reload on :8000 |
| `pnpm start:api` | Migrate, then run without reload. In production, migrations will move to their own `migrate` step ([ADR 0005](../adr/0005-job-queue-and-scaling.md)) |
| `pnpm test:api` | pytest: unit and HTTP tests on in-memory SQLite (seconds, no network), plus the Postgres tests when `TEST_DATABASE_URL` is set |
| `pnpm db:migrate` | Apply migrations to `DATABASE_URL` |
| `pnpm --filter @botdesk/api worker` | The job worker as its own process, for `WORKER_MODE=separate` (not needed by default: the API runs one inside) |
| `pnpm db:seed` | Add the demo team (ali@acme.dev / botdesk123, Sara, Omar in Acme Labs) and three bots. Not in production |
| `pnpm check` | typecheck (mypy) + lint (ruff) + tests, for web, API, plugin SDK and plugins together |

Inside `apps/api`: `pnpm db:revision "add bots"` writes a new migration from model changes; `pnpm format` formats and fixes lint.

### Settings

Every setting is in [`apps/api/.env.example`](../../apps/api/.env.example). The ones for bots:

| Setting | Default | What it does |
|---|---|---|
| `DATABASE_URL` | local SQLite | The app database. On Neon the **pooled** address is fine |
| `DATABASE_URL_DIRECT` | = `DATABASE_URL` | The **direct** address (Neon: no `-pooler` in the host). The job queue, live events (`LISTEN`), run checkpoints and mem0 keep their own connections here |
| `TEST_DATABASE_URL` | empty | A **separate** database for the Postgres tests. They wipe it. Empty = those tests are skipped |
| `ENVIRONMENT` | development | `development`, `test` or `production`. Only an **explicit** `development` or `test` relaxes the `SECRET_KEY` rules below; left unset, the API treats `SECRET_KEY` as production does (fails closed) |
| `SECRET_KEY` | empty | Encrypts the model keys organizations save. **Required, at least 32 characters**, unless `ENVIRONMENT` is explicitly `development` or `test` (the API refuses to start otherwise); those fall back to a fixed, public development key with a warning. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. To change it, rotate with `SECRET_KEY_OLD` |
| `SECRET_KEY_OLD` | empty | Earlier `SECRET_KEY`s while rotating (comma-separated). Saved keys still decrypt and are re-encrypted with `SECRET_KEY` the next time they're saved. See [How keys are protected](#how-keys-are-protected) |
| `DEFAULT_MODEL_ID` | `anthropic:claude-sonnet-4-5` | The model for bots that don't name one (`provider:model`) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` | empty | Instance-wide provider keys, the fallback after an organization's own key (handy when self-hosting for one team). A bot whose provider has neither answers with a **stand-in reply**, so everything works offline |
| `ALLOW_PRIVATE_MODEL_URLS` | false | Let custom model servers live on private, loopback or link-local addresses (see [Custom servers and SSRF](#custom-servers-and-ssrf)). Refused by default **everywhere**, development included; set it to `true` in your local `.env` to use Ollama on `localhost` |
| `ALLOW_PRIVATE_MCP_URLS` | false | The same for MCP servers, as its own switch: set it to `true` in development to add an MCP server running on your own machine. Plain `http://` is refused either way |
| `RUN_MAX_STEPS`, `RUN_MAX_SECONDS` | 25, 900 | Limits on every run; a run that hits one fails with a clear message |
| `BOT_MAX_RUNNING_RUNS` | 2 | Runs one bot may have going at once (across chats) |
| `BOT_HOP_LIMIT` | 3 | How many hops a chain of bot replies may go from a person's message. A bot @mention past it starts nothing; the chat gets a "Stopped a chain…" notice ([Bots working together](#bots-working-together)) |
| `WORKER_MODE` | `embedded` | Where background jobs (bot runs, approval expiry, timers) run. `embedded`: a worker inside the API process. `separate` (Postgres only): the API only adds jobs; run `python -m src.worker` (`pnpm worker` in `apps/api`) as its own process. See [Background jobs](#background-jobs) |
| `WORKER_CONCURRENCY` | 10 | Jobs one worker runs at once (runs mostly wait on the model) |
| `PLUGINS` | `demo` | Allowlist of plugin ids to load (comma-separated), found through `botdesk.plugins` entry points. An id nobody provides stops startup; a broken plugin is skipped with a log line. `demo` = fake tools for trying approvals; `gmail` = connect Google accounts; search, read, label, archive, draft, send and trash mail, and react to new email. `.env.example` lists both |
| `API_PUBLIC_URL` | `http://localhost:8000` | The API's address as browsers reach it. OAuth providers send people back to `{API_PUBLIC_URL}/api/v1/oauth/callback` |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | empty | The server's own Google OAuth client ([guide](../self-hosting/google-oauth.md)). Until both are set, Gmail is "not set up" on Connect apps. The secret is a `SecretStr` |
| `GOOGLE_OAUTH_BASE_URL`, `GMAIL_API_BASE_URL` | empty | **Tests only** (ignored unless `ENVIRONMENT=test`): a fake Google for sign-in, token and revoke calls, and a fake Gmail API for the account lookup and Gmail tool calls |
| `TOOL_TIMEOUT_SECONDS` | 30 | A tool call that takes longer fails |
| `APPROVAL_EXPIRY_HOURS` | 72 | An approval nobody answers in time expires and counts as "no" (a job checks every minute) |
| `MEMORY_ENABLED` | false | mem0 memory on pgvector, in the same database. Also needs Postgres and `OPENAI_API_KEY` |
| `BREVO_API_KEY` | empty | Sends real email through Brevo. Empty = emails are only written to the log (see [Email](#email)) |
| `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME` | empty, BotDesk | The sender. The address must be verified in Brevo |
| `PASSWORD_RESET_MINUTES` | 60 | How long a password reset link works |
| `SIGNUP_MODE` | `open` | Who may create an account: `open` (anyone who reaches the server; each gets their own organization), `invite-only` (only with an unused, unexpired invite link for that email; the account joins the inviting organization) or `closed` (no new accounts; existing people sign in and accept invites). See [Sign-up modes](#sign-up-modes) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,::1` | Proxies whose `X-Forwarded-For` / `X-Forwarded-Proto` are believed (IPs or CIDRs, comma-separated). Never `*` where clients can reach the API directly: anyone could then pick their own address and dodge the limits. Rate limits key on the client address, so behind a reverse proxy list the proxy here. The same variable uvicorn uses; the app applies it itself (uvicorn runs with `--no-proxy-headers`) |

### Tests on Postgres

There's no Docker here, so the Postgres tests use a second database on the same Neon project:

1. In the Neon SQL editor (or `psql`): `CREATE DATABASE botdesk_test;`
2. In `apps/api/.env`: `TEST_DATABASE_URL=` the **direct** address with `/botdesk_test` as the database. Never your dev database: the tests refuse to run if it's the same as `DATABASE_URL`.
3. `pnpm test:api`. The first test creates the tables; each test then empties them.

Neon is far from a laptop, so these take a few minutes. CI runs them on a Postgres service in seconds.

### Neon

1. Create a project at [neon.tech](https://neon.tech) (free plan is fine).
2. Dashboard → **Connect** → copy the connection string. Keep `?sslmode=require`.
3. Put it in `apps/api/.env` as `DATABASE_URL=postgresql://…`. The API adds the async driver itself.
4. `pnpm db:migrate`, then `pnpm db:seed` for the demo accounts.

## Folders

```
apps/api/
  src/                       the app's code; imports read `from src.core.config import …`
    main.py                  create_app(): settings, database, CORS, error handler, /api/v1 router
    core/                    things every layer uses
      config.py              Settings from env / .env
      database.py            Base model class, engine, one session per request
      security.py            password hashing, session and reset tokens
      secrets.py             SecretBox: encrypts saved model keys (Fernet, key from SECRET_KEY)
      url_guard.py           checks custom model server addresses (SSRF guard)
      errors.py              AppError → NotFound, Conflict, Unauthorized, Forbidden
      handles.py             names → handles and slugs
    models/                  SQLAlchemy tables (one file per area)
    schemas/                 Pydantic request/response shapes (JSON is camelCase)
    services/                business rules + database queries. No HTTP here.
      email_service.py       EmailSender: Brevo, or the log when there's no key
    emails/                  email templates: (subject, html, text)
    controllers/             one request at a time: call services, commit, set cookies
    jobs/                    background work (ADR 0013): the JobQueue seam and its two adapters
      queue.py               Job, JobQueue (defer / abort / recover), JobRegistry (how a task is declared)
      tasks.py               JOBS: run_bot, expire_approvals, recover_runs, fire_routines (each every minute), prune_routine_runs (daily)
      postgres.py            ProcrastinateQueue: procrastinate on Postgres, the worker and its restarts
      local.py               LocalQueue: asyncio tasks in this process (SQLite, unit tests)
      background.py          puts runs + queue + live-events listener together for the API or the worker
    worker.py                `python -m src.worker`: the worker as its own process (WORKER_MODE=separate)
    runtime/                 how a bot run happens
      runner.py              RunManager: defers run jobs; take_turn starts, resumes or carries on a run; Stop; restart recovery
      graph.py               the LangGraph graph: model ↔ tool pipeline loop, approval_gate (interrupt), save_reply
      tool_pipeline.py       one door for every tool call: validate → risk → policy → record → execute at most once
      policy.py              security level × risk class → auto / ask / deny, plus taint (pure)
      chat_model.py          ModelResolver: a bot's model_id → a chat model with the org's key (or env key), or the stand-in (which obeys `/tool …`)
      prompt.py              instructions + memories + the chat → what the model sees
      token_batcher.py       streamed tokens → a few database writes, not one per token
      limits.py              steps and time per run
      memory.py              MemoryService: NoMemory (with the reason), or mem0 when switched on
      event_bus.py           wakes a chat's live streams when new events are saved (in-process, plus Postgres LISTEN)
      reporter.py            saves a run's events
    model_providers/         one small adapter per model provider: list models (= test a key), build a chat model
    plugins/                 what bots can do (the contract itself is packages/plugin-sdk)
      loader.py              finds `botdesk.plugins` entry points, imports only allowlisted ones, skips broken ones
      registry.py            ToolRegistry: allowlisted plugins' tools by full name (`demo.send_email`)
    api/
      deps.py                Db, CurrentUser, OrgAccess
      v1/router.py           mounts every route file under /api/v1
      v1/routes/*.py         the HTTP surface: path, method, status, inputs
  migrations/                Alembic (env.py reads DATABASE_URL from settings)
  tests/                     pytest: conftest.py builds a fresh app + client per test
```

### How a request flows

```
route (api/v1/routes/auth.py)      declares POST /api/v1/auth/sign-in
  → controller (auth_controller)   runs it: service call, commit, set cookie
    → service (auth_service)       the rule: check password, create session
      → models (User, Session)     the tables
```

### How a reply flows

```
POST /threads/{id}/messages       one transaction: the message, a queued run per bot that should reply, a run_bot
                                  job per run (lock chat:{thread}) and a message_saved event. Returns at once.
  → worker takes the job          RunManager.take_turn: one run per chat (the job lock + a guarded UPDATE);
                                  not its turn yet → a new job a second later
    → graph                       load_context → recall → call_model (streams message_delta events)
                                  → tool calls? one at a time through the tool pipeline (see Tools and approvals)
                                  → save_reply (the message + message_saved, and in the same transaction a queued
                                    run and its job per bot the reply @mentions, or the "chain stopped" notice)
                                  → remember (in the background)
    → run_finished / run_failed, or paused: approval_requested (waiting_approval) / run_needs_attention
GET /threads/{id}/events          SSE: replays run_events after Last-Event-ID, then follows new ones (woken by
                                  this process's bus, by Postgres NOTIFY from other processes, or every 5 s)
```

### Background jobs

[ADR 0013](../adr/0013-the-job-queue-lands.md). Bot runs and timers are **jobs** on a queue: [procrastinate](https://procrastinate.readthedocs.io/) on Postgres (MIT; its tables come from the migration `b7f3a9c1d2e4`, so `pnpm db:migrate` is still the one step). Code reaches it only through `JobQueue` (`src/jobs/queue.py`):

- `await queue.defer(Job("task", {...}, lock=…, queueing_lock=…, run_at=…), db=session)`: with `db`, the job is saved in that transaction (only if it commits). Jobs with the same `lock` run one at a time in order; one *waiting* job per `queueing_lock`; `run_at` delays it.
- `abort(queueing_lock)` stops the running job with that key on any worker (Stop uses it); `recover(jobs)` puts back jobs of dead workers and defers the given ones that have no job; `wait_until_idle()` is for tests.
- **Adding a job** (routines, Gmail polling): declare it on `JOBS` in `src/jobs/tasks.py` (or a module it imports). A handler gets a `JobEnv` (runs, queue, sessionmaker, settings) and the job's arguments, and must be safe to run twice (read what to do from the database):

  ```python
  @JOBS.task("routines.fire")                    # deferred: queue.defer(Job("routines.fire", {"routine_id": id}, run_at=when))
  async def fire(env: JobEnv, routine_id: str) -> None: ...

  @JOBS.task("gmail.poll", cron="*/2 * * * *")  # periodic: every 2 minutes, on one worker (also gets `timestamp`)
  async def poll(env: JobEnv, timestamp: int) -> None: ...
  ```

| Database | `WORKER_MODE` | API process | `python -m src.worker` |
|---|---|---|---|
| SQLite | (ignored) | jobs are asyncio tasks here (`LocalQueue`); lost on restart | refuses to start |
| Postgres | `embedded` (default) | procrastinate worker inside, + `LISTEN` for live events | not needed |
| Postgres | `separate` | only adds jobs, + `LISTEN` for live events | runs every job; start as many as you like |

- **Restarts.** A stopping worker gives running jobs 5 s, then aborts them and puts them back; the run stays `running` and, after the restart, carries on from its last saved step (`run_resumed`; the step it was in runs again). A crashed worker's jobs come back once its heartbeat is a minute old (`recover_runs`, at worker start and every minute, which also re-defers any run that should be moving but has no job). A tool call left half done stops the run as `needs_attention`. On SQLite nothing can resume, so a restart fails unfinished runs ("Interrupted by a restart. Send your message again.").
- **Triggers.** `poll_triggers` (every minute) polls each bot trigger that is on, each on its own (see [Gmail](#gmail-tools-and-the-new-email-trigger)).
- **Approval expiry.** `expire_approvals` (every minute) expires pending approvals past `APPROVAL_EXPIRY_HOURS`: the tool call is denied, an `approval_decided` event (status `expired`) is saved, and the run resumes told "Nobody approved this action in time".
- **Live events across processes.** The statement that takes a chat's advisory lock before saving its events also sends `pg_notify('botdesk_run_events', '<chat id>')`, delivered at commit. Each API process keeps one `LISTEN` connection (direct address, pinged every minute, reconnecting with backoff) that wakes its streams.
- **Neon.** The queue's pool and `LISTEN` use `DATABASE_URL_DIRECT` (`LISTEN` doesn't work through the pooler); idle connections are tested before use and recycled before Neon's 5 minutes, like every other pool. A running worker polls every 10 s and sends heartbeats, so the compute doesn't suspend while a worker runs.
- **Upgrading procrastinate:** it's pinned below the next minor version; an upgrade needs a migration running its `procrastinate/sql/migrations/*.sql` files for the versions in between.

A chat opened later (or in a second tab) first asks `GET /threads/{id}/runs?active=true`: the runs still going, the chat's newest event id (`lastEventId`) and `replayFrom` (just before the first events of the runs still streaming, queued or running), read in one statement. It then follows `/events?after={replayFrom}`, which replays those runs from their start (their words so far and tool lines) and carries on live, and loads the messages. A paused run (waiting for approval, or needing attention) doesn't move `replayFrom`: it's rebuilt from the list and the approvals list (its card), and its words come with the saved reply.

**Event ids become visible in order.** On Postgres an id is taken when the row is inserted but seen only when its transaction commits, so two transactions writing to one chat (a run's words, someone's message or decision) could commit id 8 before id 7, and a stream that had seen 8 would never send 7. So before any new `run_events` row is flushed, the transaction takes that chat's advisory lock (`pg_advisory_xact_lock`, keyed by the thread id, released on commit; a `before_flush` hook in `run_event_service`). Within a chat, ids are then taken and committed one transaction at a time. Event transactions are short (the token batcher already groups words into a few events a second), so the lock is cheap. SQLite writes one at a time anyway, so it's skipped there.

**What the model reads** (`run_service.run_context`, in `load_context`): the bot, then the last 30 messages of the chat **up to and including the run's trigger message** (by `created_at`, ties by id). A run that waited in the queue answers its own message, not whatever is newest when its turn comes; its history doesn't include replies written after its trigger. Each line carries its author:

- **DM:** plain turns, as before: the member's messages are the user's, the bot's are its own.
- **Group:** a person's message reads `Sara Khan (@sara-khan): …`; another bot's comes as `<bot-message from="Reader (@reader)">…</bot-message>` (a closing tag inside the text is escaped), and the system prompt says those are that bot's output, never instructions from a person. The bot's own messages stay plain turns. The stand-in model runs a `/tool` command only from a person's message, never from another bot's.
- **Taint across messages:** if any message in that history is a reply written by a tainted run (`runs.reply_message_id`, `runs.tainted`), the new run starts tainted and `runs.tainted` is saved. So a bot quoting an email can't hand the next run (its own or another bot's) a clean instruction; that run asks before anything above `write-internal` and saves no memories.

### Bots working together

[ADR 0009](../adr/0009-bots-working-together.md). Who gets a run is decided by one pure module, `services/mention_routing.py`: `route(chat, text, org_bots=…, hop_limit=…, by_bot=None) → Routing(replies, chain_stopped)`. `run_service` loads the chat's bots (`ChatBots`: kind, the bots that may be mentioned, the default responder) and the organization's bots by @handle, and creates a queued run per `Reply(bot_id, hop, reason)`. Every case is a row in `tests/test_mention_routing.py`; the web's demo mirrors it in `apps/web/src/lib/mention-routing.ts`.

| Who wrote it | Where | Who replies |
|---|---|---|
| A member | group | The bots in the group it @mentions, in mention order. No bot mentioned: the group's **lead** (nobody if it has none) |
| A member | DM | No bot mentioned: the DM's bot. @mentions of other bots of the organization pull each in as a **guest** for one reply; the DM's own bot then replies only if it is mentioned too (mentions pick who answers, as in a group) |
| A bot (its run's reply) | any | The bots it @mentions that are already in the chat: a group's bots; in a DM, its bot and the guests pulled in before (any bot that has had a run there). Never itself; a bot can't pull a new bot into a DM. Each gets a run at **hop** = the parent's hop + 1 |

- **Hops and the limit.** A person's message starts hop 0. `runs.hop` and `runs.parent_run_id` (the run whose reply did the mentioning) record the chain; the child's `trigger_message_id` is that reply. A mention that would make hop > `BOT_HOP_LIMIT` starts nothing, and a system message (`author.type = "system"`) "Stopped a chain of bot replies after 3 hops." is saved with a `message_saved` event on the parent run. System messages are for people: they're left out of every run's history.
- **One at a time.** Child runs are created in `save_reply`'s transaction (saving the same reply twice starts nothing twice) and started after commit; they wait for the parent to finish (the chat lock and the one-running-run-per-chat index), and the per-bot cap, budgets and step limits apply to each. A chain is a sequence of runs, never runs inside runs. They come to the web as ordinary `run_started` / `message_delta` / `message_saved` events with their own `runId`.
- **Taint.** A child's history ends at the parent's reply, so a tainted parent's reply taints it (history-based taint, above), all along the chain. Tested on Postgres (`tests/test_bots_together_postgres.py`).
- **Guests.** A guest's prompt says it was @mentioned into a member's direct chat with another bot and should answer once; other bots' messages are wrapped in `<bot-message>` in every chat, and a DM where another bot spoke explains them too. The DM stays the DM's bot's: its title, participants and chat list don't change.
- **Memory.** A guest reads and saves its *own* memories scoped to that DM's member (`MemoryScope(bot=guest, member=the DM's member)`), exactly as if the member had DMed it: only that member is in the chat, so nothing reaches anyone else. A run another bot started (hop > 0) **recalls but never saves** memories: what a bot remembers comes from people, not from one bot's output steering another's.
- **What a mentioned bot is told.** A run another bot started (hop > 0) is told so in its system prompt: help with what the bot asks using what it knows, but take actions (tools) only for what the people in the chat asked. The bot's message stays wrapped as `<bot-message>` (never an instruction), and the stand-in model never runs a `/tool` from it; this keeps ADR 0009 §5's no-laundering rule even for an untainted chain.
- **Guests stay reachable.** "Replies once" is per mention: a member's mention starts one run. After that the guest counts as in the DM, so the DM's bot (or another guest) may @mention it back; each such run is one more hop.
- **Known gaps (next slices).** Stop ends one run, not a whole chain: runs its reply already queued still go (stop them one by one). Runs are claimed in the order they were created, so a member message posted while a chain runs is answered before the chain's next hop. Removing the lead bot from a group (or deleting the bot) clears the lead.
- **Managing a group.** Rename (`PATCH /threads/{id}`), add (`POST …/participants`) and remove (`DELETE …/participants/{type}/{id}`) follow the lead's rule below: the group's creator, or an org owner or admin in the group. Each change (and a lead change) saves a `thread_updated` event, so everyone with the group open sees it live. The event stream checks on every wake-up (at least every 5 s) that you're still in the chat and ends if you were removed. Removing the lead bot clears the lead (`thread_service.remove_participant`). Tests: `test_group_management.py`.
- **The lead.** `threads.lead_bot_id` (FK to bots, `ON DELETE SET NULL`). `POST /threads/groups` sets it to `leadBotId` (one of `botIds`, else 400) or the first bot picked. `PUT /threads/{id}/lead` `{botId | null}` changes or clears it: the group's **creator**, or an org **owner or admin** in the group; other members get 403 "Only the group's creator, owners and admins can change its lead.". 400 for a bot not in the group or for a DM. Groups made before migration `dca6e06f506b` have no lead and behave as before.

**Dropped connections.** Neon suspends after 5 idle minutes and closes every connection (networks drop idle TLS connections too). Every pool tests a connection that sat idle 10 s or more before handing it out (one short round trip; busy connections are never tested), and replaces it if it's dead: the SQLAlchemy engine through a `checkout` listener (`pool_recycle=240` as well), the LangGraph checkpoint pool and mem0's pool through psycopg_pool's `configure`/`check`/`reset` callbacks (`IdleCheck` in `core/database.py`), with `max_lifetime` and `max_idle` of 240 s. mem0 gets its pool from us (`memory_pool`) instead of opening its own.

**Round trips on a run's path:** the model is looked up (org keys) once per run, not at every step; the bot's memory switch comes with the run's context; the budget check is one statement (budgets and this month's spend, summed only when a budget is set). New @handles and slugs read only the handles that start with the same base (`LIKE 'base%'`), not the whole table.

The web app reads one stream per open chat. Tokens arrive in batches (about every 50 ms) as `message_delta`; when the reply is saved, `message_saved` carries the whole message, which replaces the streamed text.

A service raises `NotFound("…")`, `Conflict("…")` and so on. `main.py` turns those into `{"detail": "…"}` with the right status, so services never touch HTTP. Controllers own the transaction (`db.commit()`).

### Routines

A **routine** (`routines`, migration `e1c4d7a92b30`) is a saved task a bot repeats: `instructions` (what to do), a 5-field `cron` line read in `timezone` (IANA; the web sends the creator's browser zone), `enabled`, an optional `securityLevel` (stricter only: the run uses the strictest of the bot's and the routine's), `lastRunAt`, `nextRunAt`, `disabledReason`. `routine_runs` records each time it was due: the run it started (`started`) or `skipped` with its `reason` (migration `c3d81f2a6b57`). A daily job, `prune_routine_runs`, forgets routine runs older than 90 days or beyond each routine's newest 200 (the runs and chats stay).

- **Routes** (`/orgs/{org}/routines`): `GET` (`?botId=`), `POST` (any member, for a bot of the org; a "Created a routine" card, a system message with a `routine-created` part, goes into the creator's DM with the bot), `PATCH /{id}` (switch on/off, edit), `DELETE /{id}`, `POST /{id}/run-now` (202 `{runId, threadId}`; 409 while its last run is still going), `GET /{id}/runs` (20 newest, with each run's status, or a skipped slot's `reason`). Who may do what, since a routine's runs act for its creator:
  - **Its creator only**: edit it (`instructions`, `botId`, `securityLevel`, name, schedule) and Run now (403 "Only the routine's creator can edit it or run it now: its runs act for them."). A `PATCH` is checked on the fields it really changes.
  - **Its creator, owners and admins**: switch it on or off, remove it (403 "Only the routine's creator, owners and admins can change it."), read its `instructions` and `GET /{id}/runs` (403 "Only the routine's creator, owners and admins can see its runs.").
  - **Every member**: sees each routine's name, schedule and on/off state; `instructions` is `null` for routines they can't read.
- **Schedule** (`services/routine_schedule.py`, croniter, already a dependency of procrastinate): the cron line is walked in the zone's wall-clock time, so 09:00 stays 09:00 across DST; a time skipped by spring-forward runs an hour later, once; one repeated by fall-back runs the first time. Saving checks the line (400 with a sentence): 5 fields, fixed times (no random or hashed `R`/`H`), a date that exists ("0 0 30 2 *" never comes), and at least 5 minutes between runs (checked over a day of its times, so `0,1 9 * * *` is refused too).
- **Firing** (`fire_routines`, every minute, `src/jobs/tasks.py`): each routine with `enabled` and `nextRunAt <= the job's minute`, in its own transaction with its row locked: checks (bot removed, creator left the org → switched off with `disabledReason`; nothing else switches a routine off), moves `nextRunAt` to the next slot after now, then (unless the bot or org is over budget, or its previous run is still queued, running or paused: `skipped` with the reason, and it fires again at its next slot, say when a new month's budget starts) opens the creator's DM if needed, saves a system message "Routine: {name}" whose hidden `routine-run` part holds the instructions, and a queued run (hop 0) answering it, with its job. The run reads that part as a person's message (`run_service.run_context`): the requester is the creator (their DM). The run keeps its level from the start, the strictest of the bot's and the routine's, in `runs.security_level` (it still obeys the bot's level if that gets stricter), so removing or loosening the routine mid-run can't loosen it. One routine that fails to fire is logged and retried next minute; the other due routines still fire. A slot missed while the server was down runs once when it's back, never as a backlog. Removing a bot switches its routines off ("Its bot was removed.").

### Handoffs

[ADR 0014](../adr/0014-handoffs-and-tasks.md), built to the [handoffs contract](../architecture/handoffs-contract.md) (migrations `4a7e2c9d1b03` and `b7d2f4a9c615`). A run hands a **task** to a teammate bot with the tool `team.handoff` (`{bot: "@sales", task, context?}`); the teammate does it in a **child run** in the same chat, and the run that handed off (the **parent**) pauses as `waiting_handoff` until all of its open tasks have ended, then reads their results and writes a new message.

- **The Team plugin** (`src/plugins/team.py`) is a core plugin: always registered first, its id reserved (naming `team` in `PLUGINS`, or installing a package that claims it, stops startup with "The plugin id 'team' is reserved."), left out of `GET /plugins`, and listed on `GET /bots/{bot}/tools` as "Team · Hand off". Every bot has its binding on (new bots through `create_bot`, existing ones through the migration's backfill); switching it off hides the tool. `team.*` calls send no `tool_started` / `tool_finished` events and no tool line: the **handoff card** (a `handoff` message part) is what people see.
- **`services/task_service.py`** is the one module that knows tasks: `hand_off` (checks, the task, the child run, the handoff message), `child_started`, `run_ended` → `Aftermath(resume, stop)`, `resume_if_ready`, `resume_answer`, `overdue` / `expire_overdue`, `to_reconcile` / `reconcile`, `parents_with_open_tasks_of` / `bot_removed`, `task_json` (TaskOut), `handoff_part`. Every task change is one conditional `UPDATE … RETURNING` under the parent run's row lock (`SELECT … FOR UPDATE`), with the card rewritten in place and a `task_updated` event on the parent run. It never defers jobs or stops runs itself: callers do what the `Aftermath` says. On Postgres, `hand_off` counts and inserts under a per-organization advisory lock (`pg_advisory_xact_lock(hashtext('tasks:<org>'))`), so concurrent handoffs from different chats can't pass `HANDOFF_MAX_OPEN_TASKS_PER_ORG`. Calling `hand_off` again for a task whose child run is gone returns that task (failed, "Its run is gone…") instead of inserting a second one.
- **Checks, in order** (the model reads "The tool failed: …"): the bot exists in this organization; it isn't the run's own bot; it isn't the bot of a run above in the chain; `hop + 1 <= BOT_HOP_LIMIT` (shared with mentions); fewer than `HANDOFF_MAX_TASKS_PER_RUN` (5) tasks over the run's life; fewer than `HANDOFF_MAX_OPEN_TASKS_PER_ORG` (20) open tasks in the organization (a soft cap). A refusal makes nothing and sends no event.
- **The graph** gains `hand_off` (after `prepare_call` or an approved `approval_gate`), `save_progress` (rewrites the handoff message with every card of the step) and `wait_for_tasks` (only an `interrupt({"taskIds": …})`). The resume answer becomes a user message `<task-results>…</task-results>` right after the step's tool results (other bots' output, never instructions; the stand-in model never runs a `/tool` from it). Both provider adapters accept that order: Anthropic merges it into the tool results' user turn after the `tool_result` blocks, OpenAI-compatible APIs get `assistant` → `tool`… → `user` (`tests/test_handoff_message_order.py`).
- **The runner:** an interrupt with `taskIds` pauses the run as `waiting_handoff` with `run_waiting_handoff {status, taskIds}` and asks `resume_if_ready` in the same transaction (tasks that already ended resume it at once). Each run's end calls `run_ended` in `_finish`'s transaction: the last open task to end defers its parent's `run_bot` job; the parent resumes with `run_resumed {botId, after: "tasks"}` (after an approval it's now `after: "approval"`). The parent's chat lock is free while it waits, so the children (same chat, one at a time) can run.
- **Safety.** Taint goes down (the child starts tainted when the parent is) and comes back up (a tainted child taints its parent's row and its resumed state; a handoff message of a tainted run taints later runs that read it). A child's level is capped at its parent's effective level: the cap is kept in **`runs.security_level`**, the same column a routine's run uses, so the effective level is still `strictest(bot, runs.security_level or bot)` (no separate `level_cap` column). The child inherits the parent's requester; the connections rule is unchanged. Children have hop > 0, so they save no memories. A child's reply never starts a run for the bot that handed it the task (`BotAuthor.skip`), and a handoff message never routes mentions.
- **Prompts.** A bot with the tool is told how to hand off and gets a roster (`- Sales Outbound (@sales): Sales`, at most 30 by name). A child's system prompt says who handed it the task, for whom, and that its reply goes back automatically; its trigger reads `Task from Chief (@chief): …` as its request. Other runs read a handoff message as its text plus `(handed @sales a task: "…", done)` per card.
- **Stop, timeouts, recovery.** `RunManager.stop(run_id)` (the Stop route, the cascade and the timeout job share it): a paused or queued run is cancelled on the spot, its approvals expire and its open tasks are cancelled, and their children are stopped in turn (grandchildren follow). Stopping a child fails only its task (`stopped`), and the parent resumes with that result. A child out of budget fails its task with `budget`. `expire_tasks` (every minute) fails tasks past `deadline_at` (`HANDOFF_TIMEOUT_MINUTES`, 60, counted from creation, so time waiting for an approval counts) as `timeout`, stops the child and resumes the parent. `recover_runs` and `recover_after_restart` also run `reconcile_tasks`: `to_reconcile` lists at most 100 parents in id order (an open task whose child already ended or is gone, a parent that ended with open tasks, a child still going after its task ended (a timeout whose stop was lost), a waiting parent with nothing open), and each is `reconcile`d in its own short transaction holding only that parent's lock, so passes on several workers and `expire_tasks` never deadlock; a tainted child taints its parent whether its task ended, timed out or was reconciled; `runs_to_pick_up` includes waiting parents with no open task. On SQLite a restart fails the children and then the parent (`LOST_PAUSE_ERROR`).
- **Removing a bot** (`DELETE /bots/{id}`) ends its handoffs first, one parent per short transaction (`bot_removed`): a task handed **to** it fails ("Sales was removed before it finished.") and its parent carries on; one handed **by** it is cancelled. Then its live runs, every run in its DMs (they're deleted with it) and those tasks' children are stopped, and only then is it deleted. Tasks outlive it: `tasks.to_bot_id` is `SET NULL` like `from_bot_id`, and `to_bot_name` / `to_bot_handle` keep who it was for the parent's results. `tasks` has indexes on `thread_id`, `from_bot_id`, `to_bot_id` and `message_id` (the cascade targets).
- **API.** No new routes. `RunOut.status` may be `waiting_handoff` (a paused status: Stop works, the active-runs list includes it, it doesn't move `replayFrom`), and in `GET /threads/{id}/runs` such a run carries `taskIds`, the open tasks it waits for (empty for other runs). Messages carry handoff parts as stored. Tests: `test_task_service.py`, `test_handoffs.py` (SQLite, a scripted model playing every bot), `test_handoffs_postgres.py` (concurrency and restarts).

## API v1 so far

| Method & path | What it does |
|---|---|
| `GET /api/v1/health` | Up, and the database answers |
| `GET /api/v1/auth/options` | Public: `{signUpMode: "open" \| "invite-only" \| "closed"}`, so the sign-up screen can adapt |
| `POST /api/v1/auth/sign-up` | Create an account and sign in. Without `inviteToken`: a first organization of your own (you're owner). With `inviteToken` (from an invite link, for that email): you join that organization instead. 403 when `SIGNUP_MODE` doesn't allow it. 429 after 20 an hour from one address |
| `POST /api/v1/auth/sign-in` | Email + password → session cookie. 429 after 10 a minute from one address or 5 a minute for one email |
| `POST /api/v1/auth/sign-out` | Ends this session everywhere it was used |
| `GET /api/v1/auth/me` | You, and your organizations with your role |
| `PATCH /api/v1/auth/me` | Change your name or @handle (unique) |
| `POST /api/v1/auth/change-password` | Needs the current password (wrong one: 400, so the app keeps you signed in); signs out your other devices |
| `POST /api/v1/auth/forgot-password` | Emails a reset link if the account exists. Always the same 202 answer (doesn't reveal accounts). 429 after 5 an hour for one email or 20 an hour from one address |
| `POST /api/v1/auth/reset-password` | `{token, password}`: sets a new password from the link (once, before it expires) and signs out every device. 429 after 20 an hour from one address |
| `GET /api/v1/orgs` | Your organizations |
| `GET /api/v1/orgs/{id}` | One organization |
| `PATCH /api/v1/orgs/{id}` | Rename / change address / set the monthly budget `monthlyBudgetUsd` (null or 0 = no limit) / set `defaultSecurityLevel` (owner or admin; members 403) |
| `GET /api/v1/orgs/{id}/members` | People and their roles |
| `PATCH /api/v1/orgs/{id}/members/{userId}` | Change a role (owners and admins; only owners touch owners) |
| `DELETE /api/v1/orgs/{id}/members/{userId}` | Remove someone, or leave (your own id). There's always one owner |
| `POST /api/v1/orgs/{id}/invitations` | Invite an email as admin or member (owners and admins only; members get 403); emails them the link, and returns it once |
| `GET /api/v1/orgs/{id}/invitations` | Pending invites (owners and admins) |
| `DELETE /api/v1/orgs/{id}/invitations/{invId}` | Revoke an invite |
| `POST /api/v1/invitations/accept` | Join from an invite link (signed in with the invited email) |
| `GET /api/v1/orgs/{id}/bots` | The organization's bots |
| `POST /api/v1/orgs/{id}/bots` | Hire a bot (any member); @handle comes from the name. Without `securityLevel` it gets the org's `defaultSecurityLevel` (`read-only` / `ask-before-acting` / `autonomous`; new orgs: `ask-before-acting`). Members may set `monthlyBudgetUsd` from 1 up to the default ($50); more, or 0 (no limit), is 403 for them |
| `GET /api/v1/orgs/{id}/bots/{botId}` | One bot |
| `PATCH /api/v1/orgs/{id}/bots/{botId}` | Edit a bot (only the fields you send). Changing `monthlyBudgetUsd` takes an owner or admin (403 "Only owners and admins can change budgets."); sending the current value is fine |
| `DELETE /api/v1/orgs/{id}/bots/{botId}` | Remove a bot (owners and admins); its chats go too |
| `GET /api/v1/orgs/{id}/memory/status` | `{enabled, reason}`: whether bots can remember on this server, and if not, what to set |
| `GET /api/v1/orgs/{id}/bots/{botId}/memories?q=&limit=` | What the bot remembers that you may see: its shared memories and your own DM ones. With `q`, closest first. See [Memory](#memory) |
| `PATCH /api/v1/orgs/{id}/bots/{botId}/memories/{memoryId}` | `{text}`: correct a memory (owners and admins: any; members: their own DM ones) |
| `DELETE /api/v1/orgs/{id}/bots/{botId}/memories/{memoryId}` | Forget one memory (same rule) |
| `DELETE /api/v1/orgs/{id}/bots/{botId}/memories` | Forget everything the bot remembers, from every chat (owners and admins) |
| `GET /api/v1/orgs/{id}/threads` | Your chats, most recent first, with a preview of the last message and `unread` (see [Unread counts](#unread-counts)) |
| `POST /api/v1/orgs/{id}/threads/dm` | Your chat with a bot (`{botId}`): the existing one or a new one. Private to you |
| `POST /api/v1/orgs/{id}/threads/groups` | Group chat with you plus the people and bots you pick. `leadBotId` (one of `botIds`) answers messages that mention no bot; left out, the first bot picked. Chats carry `leadBotId` and `createdBy` |
| `PUT /api/v1/orgs/{id}/threads/{threadId}/lead` | `{botId}` (one of the group's bots) or `{botId: null}`: change or clear a group's lead. Its creator, owners and admins; others 403 |
| `GET /api/v1/orgs/{id}/threads/{threadId}` | One chat (404 unless you're in it) |
| `POST /api/v1/orgs/{id}/threads/{threadId}/read` | 204: you've read the chat up to now, so its `unread` drops to 0 |
| `PATCH /api/v1/orgs/{id}/threads/{threadId}` | `{title}`: rename a group. The group's creator, owners and admins (others 403 "Only the group's creator, owners and admins can change it."); a DM 400 "Only a group can be changed." |
| `POST /api/v1/orgs/{id}/threads/{threadId}/participants` | `{userIds, botIds}`: add people and bots of the org to a group (same rule; outsiders 404). Ones already in it are skipped; a person added starts with nothing unread |
| `DELETE /api/v1/orgs/{id}/threads/{threadId}/participants/{user\|bot}/{participantId}` | Remove someone from a group (same rule; 404 if they aren't in it). A removed person can't open it and their open stream ends; removing the lead bot clears the lead; the last person can't be removed (400 "A group needs at least one person.") |
| `GET /api/v1/orgs/{id}/threads/{threadId}/messages` | Messages oldest first; `limit` (1–200) and `before` to page back |
| `POST /api/v1/orgs/{id}/threads/{threadId}/messages` | Send a message (`{text}`). Who replies: [Bots working together](#bots-working-together) (a DM's bot or guests; a group's mentioned bots, else its lead). Returns the message plus `runIds` (the hop-0 runs; bot-to-bot runs arrive on the stream) |
| `GET /api/v1/orgs/{id}/threads/{threadId}/runs` | The chat's runs, newest first (max 100). `?active=true`: only `queued`, `running`, `waiting_approval` and `needs_attention`. Returns `{runs, lastEventId, replayFrom}` (see below) |
| `GET /api/v1/orgs/{id}/threads/{threadId}/events` | Live updates (SSE). Resumes after the `Last-Event-ID` header, or `?after=`; otherwise from now. `?follow=false` sends what's saved and closes |
| `GET /api/v1/orgs/{id}/runs/{runId}` | One run: status, steps used, limits, error |
| `POST /api/v1/orgs/{id}/runs/{runId}/cancel` | Stop a run (queued or paused: at once, and its pending approval expires; running: within moments) |
| `GET /api/v1/orgs/{id}/approvals` | Approvals in chats you're in, newest first, max 100. `status` = `pending` (default) / `approved` / `denied` / `edited` / `expired` / `all`; filter with `botId`, `threadId` |
| `GET /api/v1/orgs/{id}/approvals/{approvalId}` | One approval (404 unless you're in its chat) |
| `GET /api/v1/orgs/{id}/connectors` | Connect apps: one per loaded plugin, `[{id, name, description, version, authType: oauth2\|api_key\|null, setup: ready\|not-configured, accessLevels, defaultAccess, tools}]` (see [OAuth connections](#oauth-connections)). Any member |
| `GET /api/v1/orgs/{id}/mcp-servers` | The organization's MCP servers with their tool snapshots, `[{id, pluginId, name, url, authKind (none\|header\|oauth), authHeader, status (active\|unreachable\|needs_sign_in\|needs_reconnect), statusReason, tools, toolsHash, toolsChanged, lastCheckedAt}]`; each tool has `state` (approved\|changed\|pending\|removed), `enabled`, `risk`, its schemas and, when changed, `previous`. Never a key, token or client secret. Any member (see [MCP servers](#mcp-servers)) |
| `POST /api/v1/orgs/{id}/mcp-servers` | `{name, url, apiKeyHeader?, apiKeyValue?}` or `{name, url, signIn?, oauthClientId?, oauthClientSecret?}`: connect, list the tools, save the snapshot with every tool **pending** (owners and admins; 403 otherwise). A server that answers 401 (or `signIn: true`) is saved waiting for its sign-in and comes back with `authorizeUrl`. 400 for a private, loopback or plain-http address (the server's or its sign-in's); 502/504 when the server can't be reached |
| `POST /api/v1/orgs/{id}/mcp-servers/{serverId}/refresh` | List the tools again; changed and new tools wait for the review, never trusted by a refresh (owners and admins). Unreachable: keeps the snapshot, `status: unreachable` |
| `PUT /api/v1/orgs/{id}/mcp-servers/{serverId}/tools` | Review tools: `{toolsHash, tools: [{serverName, enabled, risk}]}` approves the named tools as they are now, offered or not, at `risk` (read … destructive; each change audited, `lowered` when below external-send). 409 when the tools changed since `toolsHash`; 400 an unknown tool (owners and admins) |
| `POST /api/v1/orgs/{id}/mcp-servers/{serverId}/sign-in` | `{authorizeUrl}`: sign in (or reconnect) the organization's sign-in to an OAuth server (owners and admins) |
| `DELETE /api/v1/orgs/{id}/mcp-servers/{serverId}` | Remove the server and every bot's binding to it; its sign-in is revoked in the vault and at the authorization server (owners and admins) |
| `GET /api/v1/oauth/client-metadata/{serverId}.json` | Public: BotDesk's Client ID Metadata Document for a server that signs in with one (no secrets). 404 for anything else |
| `GET /api/v1/orgs/{id}/plugins` | The plugins this server loaded and their tools: `[{id, name, version, description, tools: [{name, title, description, risk}]}]`, `name` in full (`demo.send_email`). No handlers or schemas. Any member |
| `GET /api/v1/orgs/{id}/providers` | Every supported model provider: connected or not, where the key comes from, its last 4 characters, last check. Never the key. Any member |
| `PUT /api/v1/orgs/{id}/providers/{provider}` | `{apiKey, baseUrl?, label?}`: add or replace a key (owners and admins). Checked live first; a bad one is 400 `"That key didn't work: …"`. `provider` = `anthropic` / `openai` / `gemini` / `openrouter` / `groq`, `custom` for a new server, `custom-<id>` to change one |
| `POST /api/v1/orgs/{id}/providers/{provider}/test` | Check a saved key again; saves the result (owners and admins) |
| `DELETE /api/v1/orgs/{id}/providers/{provider}` | Remove the org's key or custom server (owners and admins) |
| `GET /api/v1/orgs/{id}/models` | Live models of every connected provider, merged; `?provider=` for one, `?refresh=true` skips the 10 minute cache. A provider that's down is listed in `errors`, the rest still come back. Any member |
| `GET /api/v1/orgs/{id}/usage` | Daily spend for `?days=` (default 14, max 90), this month's total, the org's budget and each bot's spend against its budget. Any member. See [Usage and budgets](#usage-and-budgets) |
| `GET /api/v1/orgs/{id}/bots/{botId}/usage` | One bot's spend this month, its budget and daily totals. Any member |
| `POST /api/v1/orgs/{id}/approvals/{approvalId}/decide` | `{decision: "approve" or "deny", editedArgs?}`. Decides once and resumes the run. 409 if already decided or expired, 400 if `editedArgs` don't fit the tool |

#### Live events

Each SSE message has `id:` (a growing number), `event:` (the kind) and `data:` JSON in one shape: `{id, kind, runId, threadId, createdAt, data}`. The kinds and their `data`:

| Kind | `data` |
|---|---|
| `message_saved` | `{message}`: the full message, as in the messages list (yours, someone else's, a bot's reply, or a system notice such as "Stopped a chain of bot replies after 3 hops."). `runId` is null for people's messages |
| `run_started` | `{botId}` |
| `message_delta` | `{messageId, botId, text}`: the next piece of a reply. `messageId` is the id the saved reply will have |
| `run_finished` | `{status}`: `succeeded` or `cancelled` |
| `run_failed` | `{status: "failed", error, code?}`: `error` is ready to show; `code` is `"budget"` when the bot or the org reached its monthly budget |
| `tool_started` | `{toolExecutionId, tool, risk, args}`: a tool call is about to run (`tool` like `demo.send_email`) |
| `tool_finished` | `{toolExecutionId, tool, status, result, error}`: `status` is `succeeded` (with `result`), `failed` (with `error`), `denied` (refused by the policy; it never ran, `error` says why) or `unknown` (it failed after it may have been done; the run stops as `needs_attention`, `error` says why). Bad arguments or an unknown tool also come as `failed` without a `tool_started` |
| `approval_requested` | `{approval}`: the run paused on a risky call and is now `waiting_approval`. `approval` is the [Approval JSON](#approval-json) |
| `approval_decided` | `{approval}`: someone decided (`approved` / `edited` / `denied`), or it `expired` (run stopped, or decided too late) |
| `run_resumed` | `{botId}`: a paused run carries on after a decision, or a run carries on after a restart interrupted it |
| `run_needs_attention` | `{status: "needs_attention", error}`: a tool may have half run (the API restarted mid-call, or a send failed after it may have gone out); a person must check. Stop is the only action so far |
| `thread_updated` | `{thread}`: a group was renamed, its lead changed, or people or bots were added or removed. The chat as `GET /threads/{id}` returns it, without `unread` (the stream is shared, the count is per person). `runId` is null |

Run `status` values: `queued`, `running`, `waiting_approval`, `needs_attention`, `succeeded`, `failed`, `cancelled`.

#### Unread counts

Each person in a chat has `thread_participants.last_read_at` (migration `4c1e9b7d2a80`; it starts when they join, and existing rows were set to the migration's time, so nothing old shows as unread). A chat's `unread` is the number of its messages created after that moment that someone else wrote (a bot, another person or a system notice); your own never count. The chat list counts every chat in one grouped query (`thread_service._unread_counts`, over the `(thread_id, created_at)` index), so it stays four queries however many chats you have. `POST /threads/{id}/read` moves your mark to now; the web calls it when you open a chat, come back to its tab, and when a message arrives while you look at it. Tests: `test_unread.py` (one-query check with `sql_statements`), `test_unread_postgres.py`.

#### A chat's runs

`GET …/threads/{threadId}/runs?active=true` answers:

```jsonc
{
  "runs": [
    {
      "id": "uuid", "botId": "uuid", "threadId": "uuid",
      "triggerMessageId": "uuid", "replyMessageId": null,
      "parentRunId": null, "hop": 0,         // the run whose reply @mentioned this bot, and how far from a person
      "status": "waiting_approval",          // queued | running | waiting_approval | needs_attention (active=true)
      "stepsUsed": 1, "maxSteps": 25, "maxSeconds": 900,
      "error": null,                         // why it needs attention (or failed); ready to show
      "createdAt": "…", "startedAt": "…", "finishedAt": null
    }
  ],
  "lastEventId": 42,                         // the chat's newest event when the runs were read; 0 for a chat with no events
  "replayFrom": 30                           // first event of the queued/running runs, minus 1 (= lastEventId if none)
}
```

Follow `/events?after={replayFrom}` to rebuild the streaming runs (a reply's words so far and its tool lines) and miss nothing after; `after={lastEventId}` gives only what happens next. **Only `queued` and `running` runs move `replayFrom`.** A paused run can wait for days while the chat goes on, so replaying from its start would replay an ever-growing range on every page load; its state comes from `runs` (paused, with the needs-attention error) and the approvals list (its card), and the words it wrote before pausing come back in the saved reply when it finishes. Both numbers come from the same SQL statement as the runs (a one-row subquery with `max(run_events.id)` and the streaming runs' `min(run_events.id)`, left-joined to the runs), so they describe the same moment on Postgres. Indexes `ix_runs_thread_id_status` and `ix_run_events_thread_id_id` cover both. 404 unless you're in the chat.

Error messages match the web app's wording, e.g. `401 "That email and password don't match."`.

## Models and keys

Settings → Models & keys. An organization's owners and admins add an API key per **model provider**; the app then lists that provider's models live, members pick one per bot, and runs use the org's key.

| Provider | Calls | Model list |
|---|---|---|
| Anthropic | native (`langchain-anthropic`) | `GET https://api.anthropic.com/v1/models` (`x-api-key`, `anthropic-version: 2023-06-01`); `display_name`, `max_input_tokens`; deprecated and retired models left out |
| OpenAI | `ChatOpenAI` | `GET https://api.openai.com/v1/models`; only chat families (`gpt-*`, `o1`/`o3`/`o4…`, `chatgpt-*`), no embeddings, tts, whisper, dall-e, moderation, audio, realtime, image |
| Google Gemini | `ChatOpenAI` on Google's OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/v1beta/openai` | `GET …/v1beta/openai/models` (Bearer key). Ids come as `models/gemini-…`; the prefix is dropped. Only `gemini*`/`gemma*` chat models (no embedding, tts, image, live, imagen, veo, aqa). No context sizes on this endpoint |
| OpenRouter | `ChatOpenAI`, base `https://openrouter.ai/api/v1` | `GET …/models`; keeps `name`, `context_length` and prices (dollars per token → per million) |
| Groq | `ChatOpenAI`, base `https://api.groq.com/openai/v1` | `GET …/models`; keeps `context_window`; drops whisper, tts, orpheus, guard models and inactive ones. Has a free tier |
| Custom | `ChatOpenAI` with the server's base URL (e.g. Ollama `http://localhost:11434/v1`, LM Studio, vLLM); the key is optional | `GET {base}/models`, everything it lists |

The code: `src/model_providers/` holds one small adapter per provider behind one interface (`list_models(http, key, base_url)`, which is also the key test, and `chat_model(model, key, base_url, transport=…)`); `services/provider_service.py` stores keys and finds the one a run uses; `services/model_catalog.py` lists models live with an in-memory cache; `core/secrets.py` encrypts; `core/url_guard.py` checks custom addresses and pins their connections.

```jsonc
// GET …/providers → a list of
{"id": "openai", "kind": "openai", "name": "OpenAI", "hint": "GPT and o-series models. …",
 "connected": true, "source": "org",          // "org" (saved here), "env" (server's key) or null
 "keyHint": "abcd", "status": "ok",           // last 4 characters; "ok" | "invalid" from the last check
 "lastVerifiedAt": "2026-11-13T10:00:00Z", "baseUrl": null}   // baseUrl: custom servers only

// PUT …/providers/{provider} body: {"apiKey": "…", "baseUrl": "http://…/v1", "label": "Ollama", "noKey": false}  → the provider, as above
// POST …/providers/{provider}/test → {"ok": false, "error": "That key didn't work: 401: …", "provider": {…}}

// GET …/models
{"models": [{"id": "openrouter:x-ai/grok-4.5", "provider": "openrouter", "name": "xAI: Grok 4.5",
             "contextWindow": 256000, "pricing": {"inputPerMtok": 3.0, "outputPerMtok": 15.0}}],   // null when unknown
 "errors": [{"provider": "groq", "message": "Groq: 503: Service unavailable"}]}
```

- **Model ids** are `provider:model`; a custom server's are `custom-<id>:<model>`. Only the first colon splits, so Ollama tags (`llama3.2:latest`) and OpenRouter slashes work.
- **Which key a run uses:** the org's key for that provider, else the server's environment key, else the stand-in model. The key is decrypted inside the run, right before the model is built (`runtime/chat_model.py`, `ModelResolver`).
- **Bots:** a bot's `modelId` must name a connected provider (org key or env key), or the bot isn't saved (400 `"OpenAI isn't connected. Add a key in Settings → Models & keys first."`). The model itself isn't checked against the live list, since lists change; a model that's gone fails its run with "The provider doesn't offer this model any more…".
- **Run errors** are rewritten into something to act on: a refused key, a model that can't use tools ("This model can't use tools. Pick another model in the bot's settings."), a missing model, a rate limit. Anything else is shown scrubbed: the exact key the failed request carried (read from the error's request headers) and anything key-shaped become `[key]`.
- **Editing a custom server:** an empty `apiKey` keeps the saved key while the base URL stays the same. A saved key is never sent to a new address, so a changed `baseUrl` needs the key again or `"noKey": true` (400 otherwise). Two admins saving the first key for the same provider at once end with one key (the second insert hits the unique index and becomes an update), not a 500.
- **Timeouts:** chat calls connect within 10 s and fail if the provider sends nothing for 60 s (httpx's read timeout is per chunk, so a long streamed answer is fine).
- **Speed:** the providers list is one query. Saving, testing and listing end the database transaction before calling a provider (calls time out after 8 s) and open a short new one to save the result. Model lists are cached per organization and provider for 10 minutes, keyed by a hash of the key and base URL, so a replaced key never serves the old list; saving a key fills the cache.

### How keys are protected

- **At rest:** Fernet (AES-128-CBC + HMAC-SHA256, `cryptography`), with a key derived from `SECRET_KEY` by HKDF-SHA256. The database holds the token and `key_hint` (last 4 characters, only for keys of 12+ characters).
- **In answers:** no route returns a key; only `keyHint`. Provider error messages are scrubbed: the key itself and anything key-shaped (`sk-…`, `gsk_…`, `AIza…`, long tokens) become `[key]`, and they're cut to 200 characters.
- **In logs:** keys are never logged; a `ProviderAccess` (a decrypted key in memory) prints without it. A test checks the key appears in no response and no log line.
- **Who:** owners and admins add, replace, test and remove keys; every member can see providers (without keys) and models.
- **Fails closed:** without an explicit `ENVIRONMENT=development` or `test`, the API refuses to start without a `SECRET_KEY` of at least 32 characters, so a forgotten setting never puts a real server on the public development key.
- **Rotation:** set the new `SECRET_KEY` and move the old one to `SECRET_KEY_OLD` (comma-separate several). `MultiFernet` encrypts with the new key and decrypts with any of them; each key is re-encrypted with the new one the next time it's saved. Once every key has been saved again (or re-added), drop `SECRET_KEY_OLD`.
- **Environment keys** (`ANTHROPIC_API_KEY` …) are `SecretStr` in the settings, so they never show up in a repr or a log line.

### Custom servers and SSRF

A custom base URL is an address the API itself will call, so it goes through an SSRF guard (`core/url_guard.py`), on in every environment:

- only `http` and `https`, and no user name or password in the URL;
- the host must resolve only to public addresses: private (10/8, 172.16/12, 192.168/16), loopback, link-local (169.254/16, where cloud metadata lives), shared (100.64/10) and reserved ones are refused, unless `ALLOW_PRIVATE_MODEL_URLS=true`. One private address among public ones is enough to refuse;
- **redirects are never followed**, on model lists and on chat calls. The OpenAI and Anthropic SDKs follow redirects by default, so every chat model gets BotDesk's own HTTP client (`follow_redirects=False`, `model_providers/base.py`); otherwise a server could answer with a 307 to `169.254.169.254` and the SDK would re-send the conversation there. Sync calls to a custom server are refused, since only the async client is pinned (runs are async);
- **DNS rebinding is closed:** checking a name and then letting httpx resolve it again leaves a gap (a short-TTL name can answer "public" to the check and `127.0.0.1` to the connection). Every call to a custom server (model lists and chat) goes through `GuardedTransport`: httpx's normal transport with a network backend that resolves the name once, checks every address, and opens the TCP connection to the checked IP. The Host header and TLS (SNI and the certificate check) still use the original name, because httpcore takes those from the URL. Environment proxies are ignored for these calls, since a proxy would choose the destination instead.

`check_base_url` also runs when a key is saved and before a run starts, to turn a bad address into a message people can act on; the transport is what enforces it. Built-in providers have fixed public addresses and use httpx's own transport (still without redirects). Turn on `ALLOW_PRIVATE_MODEL_URLS` only on a machine whose network you trust.

## Tools and approvals

Build step 2 ([ADR 0004](../adr/0004-agent-runtime-and-safety.md)). Every tool call goes through one pipeline, as separate graph nodes:

```
call_model ──(tool calls, one at a time)──→ prepare_call: validate args → risk class → policy → save the decision
   ↑                                           ├ auto → execute_tool ──────────────────────────┐
   │                                           ├ ask  → approval_gate: interrupt() (run pauses)│
   │                                           │        … decide → Command(resume) ────────────┤
   │                                           └ deny / bad args ──────────────────────────────┤
   └────────── finish_call: the model gets the result, or why it didn't run ←──────────────────┘
```

- **Policy** (`runtime/policy.py`, pure): the ADR 0004 table, 3 levels × 7 risk classes (`read`, `write-internal`, `write-external`, `external-send`, `spend`, `destructive`, `credential`). The bot's `securityLevel` is the level, made stricter for a routine's run by its routine's (`runs.security_level`); there's no org ceiling yet (the org's `defaultSecurityLevel` is only where new bots start).
- **Taint** (strict, run-level): a tool that returns outside text (`untrusted_output`) sets `runs.tainted`, and so does a history holding a reply that a tainted run wrote (see How a reply flows). After that, anything above `write-internal` asks, even for Autonomous bots, and the run saves no memories. Outside text reaches the model wrapped in `<untrusted-content>`. An `open`-egress read in a tainted run counts as `external-send`.
- **`tool_executions`** records every call; run id + the model's tool call id is the idempotency key. Status: `ready` → `started` → `succeeded` / `failed`; `waiting_approval` → `ready` (approved) / `denied`; refused calls are saved as `denied` / `failed`. It also stores `risk`, `decision`, `decision_trace`, `args` and `args_hash`. Running a call that already `succeeded` reuses its result; one left `started` stops the run as `needs_attention` unless the tool is idempotent. A tool also gets `ctx.idempotency_key` (`"{runId}:{toolCallId}"`) to pass to services that accept one.
- **A failed call that may still have happened** (ADR 0004 §2, 2026-11-18). A tool that isn't idempotent, with a risk above `write-internal`, that times out, raises, or returns something unusable is not reported to the model as failed when it may already have acted (an email out before Gmail's answer was lost): the model would try again, and under Autonomous a second email would go out with nobody asked. Instead the row stays `started` (with why in `error`), a `tool_finished` event says `status: "unknown"`, and the run stops as `needs_attention` (`OutcomeUnknown`, a `NeedsAttention`); coming back to that call later never runs it again. It ends `failed` as before when it certainly didn't happen: the tool never ran (unknown tool, `ACCOUNT_CHANGED`, the time ran out while its account was opened), or its plugin declares `egress` (so `ctx.http` saw every request) and no request that can change something (anything but GET, HEAD, OPTIONS) may have been acted on, which `AuthorisedHttp.may_have_changed_something` tracks: a request counts from the moment it is sent and stops counting only on a 4xx refusal or when no connection could be made (a 5xx, a dropped connection, a read timeout or a redirect keep it counted). A plugin without `egress` (and an MCP tool, whose requests BotDesk doesn't see) says it changed nothing by raising the SDK's `NotDone`; `HostNotAllowed` and `NotConnected` are `NotDone`, and an MCP call raises it for anything that fails before the tool is called (a changed tool, signing in, the re-check). Idempotent tools, and `read` / `write-internal` ones, fail as they always did. A call cancelled midway (Stop, the run's time limit, a worker shutting down) that may have happened gets the same note and `unknown` line on the way out (shielded from a second cancellation), and a run that ran out of time with such a call ends `needs_attention` instead of `failed`. `ctx.http` counts each request that may have changed something on its own, so requests sent at once can't clear each other. Coming back to a noted call repeats its reason without another event. Arguments that no longer fit the tool fail before it runs, and failing to record a connection's use never fails a call that worked.
- **Pausing:** `approval_gate` only calls `interrupt({"approvalId"})`. The run task ends, the run becomes `waiting_approval`, and the checkpoint waits in Postgres (it survives restarts; SQLite's in-memory checkpoints don't, and resuming then fails the run with a clear message).
- **Deciding** is one conditional `UPDATE … WHERE status = 'pending'`, together with the tool call's update and the run's `run_bot` job in one transaction, so a double click or two people can only decide once; the other gets 409. The job resumes the same checkpoint (thread id = run id) with `Command(resume={"approved", "message"})`, the answer read from the approval's status. The tool runs with the arguments saved on the `tool_executions` row (the edited ones after an edit), never with arguments from the resume value.
- **Who:** members of the organization who are in the approval's chat (the same people who can see the run; a DM stays private). Any role can decide.
- **Expiry:** approvals expire after `APPROVAL_EXPIRY_HOURS`: the `expire_approvals` job (every minute) expires them and resumes their runs told "no". Deciding one that is overdue but not swept yet also expires it (409, and the run is told "no"); stopping the run expires its pending approvals.
- **Short transactions:** none is open during a model call, a tool call, or the wait for a person.
- **Results must be JSON objects.** A handler that returns something else (a list, None, a dict holding a `datetime` or `UUID`) fails that call with a clear message: the row ends `failed`, not `started`, and the run goes on. For a tool that may have changed something outside BotDesk (above) it ran to the end, so it may have been done: that call stops the run as `needs_attention` instead.

### Plugins

Build step 3 ([ADR 0006](../adr/0006-repo-structure-plugins-and-project.md)). The plugin contract is its own package, [`packages/plugin-sdk`](../../packages/plugin-sdk/README.md) (`botdesk-plugin-sdk`, import `botdesk_plugin_sdk`): `PluginManifest`, `ToolSpec`, `RiskClass`, `Egress`, `ToolContext`, `ToolResult`, `NoArgs`, `validate_manifest`, and test helpers. Manifest version 2 adds `auth`, `egress` hosts, per-tool `scopes`, settings models, `triggers`, `ctx.http` and `ctx.connection` (see [Connections](#connections)); version-1 plugins load unchanged. It depends only on Pydantic. The API imports the SDK; plugins import only the SDK; the API never imports a plugin by name.

- **Layout:** one uv workspace at the repo root (`pyproject.toml`, `uv.lock`, `.venv`), members `apps/api`, `packages/plugin-sdk` and `plugins/*`. Built-in plugins live in `plugins/<name>/`, each its own package (`plugins/demo` = `botdesk-plugin-demo`, import `botdesk_demo`). The API lists them as workspace dependencies in `apps/api/pyproject.toml`.
- **Finding:** a plugin package declares `[project.entry-points."botdesk.plugins"] <id> = "module:function"`; the function returns its `PluginManifest`, fresh each call so every app and test gets its own state.
- **Allowlist first:** `src/plugins/loader.py` reads the entry points without importing anything, and imports only the ids in `PLUGINS`. Installed never means trusted.
- **Checks at load** (`validate_manifest`, the same function plugin authors run in their tests): id is lowercase letters, digits and dashes and matches the entry-point name; tool names are lowercase with underscores and unique; title and description set; risk is one of the 7 classes and egress `fixed` / `open`; `args_model` is a Pydantic `BaseModel` class; the handler is `async`. A plugin that fails, or fails to import, or raises while building its manifest, or is provided by two packages, is **skipped with one `ERROR` log line** (`Plugin 'x' skipped: …`) and the API starts without it. An allowlisted id that no package provides is a settings typo and stops startup.
- **Adding one:** see the SDK README's five-minute guide and [CONTRIBUTING.md](../../CONTRIBUTING.md#write-a-plugin).

### Connections

Slice 5.1 of [ADR 0010](../adr/0010-connections-and-credentials.md) ([build plan](../architecture/connections-gmail-mcp.md)). A **connection** is one authorised account on one connector (a plugin with `auth`), owned by a member, a bot or the organization.

- **Table** `connections` (`models/connection.py`): owner kind and id (check constraint), `auth_type`, `account_label`, `account_ref`, `encrypted_secret`, granted `scopes`, `status` (`active` / `needs_reconnect` / `revoked`). One row per account per owner (unique index), so connecting the same account again replaces its credential. `tool_executions.connection_id` and `approvals.connection_id` record the account each call works on (saved when the call is recorded). `audit_log` gets a row on create, reconnect and disconnect (append-only, no secrets).
- **Routes** (API keys here; OAuth apps in [OAuth connections](#oauth-connections)): `GET /orgs/{id}/connections`, `GET …/{connectionId}`, `POST` `{connectorId, ownerKind: member|bot|org, botId?, accountLabel?, apiKey}` (201), `DELETE …/{connectionId}` (204, idempotent). A member creates and sees their own; owners and admins create org-owned ones and see that members' exist; owners, admins and a bot's creator create bot-owned ones. Another org's connection, or another member's to a non-admin, is 404. No response ever holds a credential; the key is a `SecretStr`, one line, at most 4 KB.
- **Credential vault** (`services/credential_vault.py`): `save(connection, secret)`, `open(connection) → Credential`, `revoke(connection, reason)`. `SecretBox` with its own HKDF purpose (`botdesk:connections:v1`), so a model key's ciphertext can't decrypt as a connection's; rotation as for model keys. `open` refuses a connection that isn't active. A `Credential` prints as `<hidden>` and only gives out the request headers that carry it.
- **Which connection a run uses:** the one chosen in the bot's binding (see [Bindings](#bindings-a-bots-tools)). With none, the tool fails with "Demo isn't connected for this bot…" and the run goes on. Disconnecting sets `bot_tools.connection_id` to NULL on every binding that used it (the plugin stays on).
- **`ctx.http`** (`plugins/authorised_http.py`, built per tool call by `runtime/tool_access.py`): the SDK's `HttpClient`. It allows only `https` URLs whose host is in the manifest's `egress` (checked with httpx's parser before anything is sent), adds the credential after the tool's headers (a tool can't set or replace that header), decrypts it only on the first request, never follows redirects (a 3xx fails the call), connects through `GuardedTransport` with private addresses always refused, reads at most 10 MB, times out with the tool timeout, and logs only method, host, path and status. Refusals are SDK `HttpError`s (`HostNotAllowed`, `ResponseTooLarge`, `NotConnected`) with messages safe to show. A plugin without `egress` gets an `http` that refuses everything.
- **Settings:** `API_PUBLIC_URL` (the API's public address, for OAuth callbacks).

### OAuth connections

Slice 5.3 ([contract](../architecture/connections-api-contract.md), ADR 0010 §5-§6, ADR 0011 §6-§7). Connectors whose plugin declares `OAuth2Auth` connect by signing in with the provider. Google is the first: the built-in **`plugins/gmail`** declares provider `google`, access levels `read` (`gmail.readonly`) and `full` (`gmail.modify`, the default), and an `account` handler that reads the mailbox address from `users.getProfile`. Since slice 6.1 it has the read tools `search`, `read_thread` and `list_labels` (see [its README](../../plugins/gmail/README.md)); `implied_scopes` lets a `gmail.modify` connection use tools that need `gmail.readonly`.

- **Module** `services/oauth_flow.py`, class `OAuth` (`app.state.oauth`, and one inside the run manager's `ToolAccessProvider`): `start(db, actor, connector, body) → authorize URL`, `finish(db, state=, code=, error=, iss=, session_user=) → Connection`, `refresh(sessionmaker, connection, connector)`, `revoke(connector, token)`. Its HTTP client takes an injectable transport (`create_app(outbound=…)`, `tool_access.transport`); otherwise it goes through the SSRF guard with no redirects.
- **Table** `oauth_flows` (`models/oauth_flow.py`): one row per sign-in in progress: the state's sha256 (never the state), the PKCE verifier encrypted with the vault's key, owner, access level, scopes asked for, 10-minute expiry. Start also deletes expired rows.
- **`POST /orgs/{id}/connections/oauth/start`** `{connectorId, ownerKind, botId?, access?}` → `{authorizeUrl}`. 404 unknown connector; 400 not an OAuth app, not set up ("Gmail isn't set up on this server yet."), unknown `access`, or a bot owner without `botId`; 403 by the same owner rules as API keys. The URL carries `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state` (`token_urlsafe(32)`), PKCE S256 (`token_urlsafe(48)` verifier) and the manifest's `extra_authorize_params` (Google: `access_type=offline`, `prompt=consent`, `include_granted_scopes=true`).
- **`GET /api/v1/oauth/callback`** (not org-scoped; reads the session cookie) always answers **303** to `{WEB_APP_URL}/apps/callback?result=connected&connector=<id>` or `?result=error&code=<code>`, with `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. Codes: `denied` (the provider sent `error`), `expired` (unknown, used, older than 10 minutes, or started by another user), `not-configured` (the client was removed meanwhile), `signed-out`, `forbidden` (left the organization or lost the role the owner needs), `failed` (anything else). It first deletes the flow (`DELETE … WHERE state_hash AND user_id RETURNING`), so a state works once and only for its member; it requires Google's `iss` (RFC 9207: Google's discovery document advertises `authorization_response_iss_parameter_supported`, so a callback without `iss`, or with another one, is `failed`; providers listed in `oauth_flow.ISSUERS`); then, with no transaction open, exchanges the code (form POST with the verifier and client secret) and calls the plugin's `account` handler through an `AuthorisedHttp` holding the new token and limited to the plugin's egress (no handler: label = the plugin's name, ref = `default`). Granted scopes come from the token response (falling back to those asked for), so a scope unticked on Google's consent screen isn't granted and the toolset drops the tools that need it. Saved by `connection_service.save_account`, the same upsert by `account_ref` as API keys: connecting the same account again is a **reconnect** of the same row (`connection.reconnected`), and a reconnect that brings no refresh token keeps the old one.
- **Refresh** (in `ToolAccessProvider.open`, before the `AuthorisedHttp` is built): a token with under 60 s left is refreshed. The caller that wins `UPDATE connections SET refresh_lease_until = now()+15s WHERE id = ? AND (lease IS NULL OR lease < now())` (committed at once) calls the token endpoint with no transaction open, the whole call bounded to 10 s (`TOKEN_CALL_BUDGET`) so the lease always outlives it, and saves the new token through the vault (keeping the refresh token when none comes back) with one guarded `UPDATE … WHERE id = ? AND status = 'active' AND encrypted_secret = <the one refreshed from>`: if the connection was disconnected (or reconnected) meanwhile, the new token is thrown away and the tool fails with "<label> was disconnected. Connect it again in Connect apps." The others re-read the row every 0.2 s for up to 15 s. `expires_in` may be a number or a numeric string (3599, 3599.0, "3599"); missing or unreadable means 3600 s. Two concurrent refreshes make one token request (`test_oauth_postgres.py`). `invalid_grant` (or no refresh token) sets `needs_reconnect` with a `status_reason`, clears the lease and writes `connection.needs_reconnect`; the tool fails with "<label> needs reconnecting (Connect apps)." A failure that may pass (network, timeout, 5xx, other OAuth errors, the SSRF guard refusing, an answer with no token) **backs off**: the lease is kept for 4 s (`BACKOFF`) so concurrent calls don't all retry, and every caller goes on with the old token (a lease with 4 s or less left is never waited for). Anything else raised during the refresh (a bug, the database, a cancellation) gives the lease back at once and is re-raised. A worker that dies holding the lease loses it after 15 s.
- **Disconnect** decrypts the token to revoke (the refresh token, else the access token), revokes in the vault and unbinds, commits, and only then POSTs the provider's `revoke_url` with `token=…`, best effort (a failure, including the SSRF guard refusing the address, is logged, and the disconnect still answers 204).
- **Secrets:** tokens, codes, verifiers and the client secret never reach a response, a log line, an audit line, a run event or a redirect URL; the provider's error text never reaches the browser (logs keep only an OAuth error code such as `invalid_grant`). `test_oauth.py` checks this over a whole flow. uvicorn's access log shows `/api/v1/oauth/callback?<redacted>` instead of the code and state (`core/access_log.py`, installed by `create_app`).
- **Tests without Google:** `tests/test_oauth.py` answers Google's token and revoke endpoints and Gmail's profile with `httpx.MockTransport` (`FakeGoogle`). `GOOGLE_OAUTH_BASE_URL` / `GMAIL_API_BASE_URL` point a test server at a fake Google (only with `ENVIRONMENT=test`); the Gmail one applies to the account lookup and to tool calls (`ToolAccessProvider(rebase=…)`); `tests/test_gmail_tools.py` runs `gmail.search` through the tool pipeline on a connected mailbox.

### Gmail tools and the new-email trigger

Slices 6.1-6.3 ([ADR 0011](../adr/0011-gmail-plugin.md), [plugin README](../../plugins/gmail/README.md), [owner's guide](../self-hosting/google-oauth.md)). All Gmail calls go through `ctx.http` (the connection's token added by BotDesk).

- **Tools.** Read (`gmail.readonly`): `search`, `read_thread`, `read_attachment`, `list_drafts` (all taint the run), `list_labels`. Write (`gmail.modify`): `add_labels`, `remove_labels`, `archive`, `create_draft` (`write-external`), `send`, `send_draft` (`external-send`), `trash` (`destructive`). So on "Ask before acting" every change asks; "Autonomous" asks only for `trash`; and once a run is tainted every change asks. `send` and `create_draft` take bare addresses (at most 20) and a one-line subject, refused by the args model before an approval card exists; the mail is built with `email` (plain text) and sent as base64url `raw`; a reply (`reply_to_thread_id`) is threaded with `threadId`, `In-Reply-To` and `References`. A send makes one request and never retries (the pipeline's `tool_executions` record stops a started, non-idempotent call from running again). `format: "markdown"` adds an HTML alternative we generate (the model's HTML is escaped). `send_draft` carries the draft's recipients, subject, whole text and attachments' names (as `list_drafts` showed them) for the card, and sends nothing unless the fetched draft still matches them. Details: [plugins/gmail/README.md](../../plugins/gmail/README.md).
- **Trigger subscriptions.** Table `trigger_subscriptions` (`models/trigger_subscription.py`, migration `e5a9c3f71d20`): one row per (binding, trigger) while it's on, with the **subscriber** (who switched it on), the account its `cursor` is for (`connection_id`), `seen` (newest 200 handled event ids), `problem` and `last_polled_at`. Removing the bot, the binding or the subscriber removes it.
- **`PUT /orgs/{id}/bots/{bot}/tools/{plugin}/triggers/{trigger}`** `{enabled}` → the bot's tools (`BotToolsOut`, whose plugins now carry `triggers: [{name, title, description, enabled, subscriberId, problem}]`). On: needs the plugin on for the bot with an active account (409 otherwise), and the right to choose that account (`binding_service.check_can_bind`: a member's own only them, 404 to others; the organization's, owners and admins; the bot's, also its creator). Off: anyone who can change the bot's Tools. Repeating either changes nothing.
- **Polling** (`trigger_service`, job `poll_triggers` every minute): per subscription, (1) `prepare`: still usable? (plugin loaded, binding on, account active, subscriber still a member and allowed that account; otherwise `problem` says why, e.g. "Paused: … needs reconnecting"); a binding moved to another account clears the cursor. (2) `poll_plugin`: the plugin's `TriggerSpec.poll(ctx, cursor)` through `ToolAccessProvider.open_plugin` (token refreshed as for tools), no transaction open. (3) `record`: under `SELECT … FOR UPDATE` and only if the cursor is still the one polled (so two polls racing post once), each new event becomes a system message in the subscriber's DM (a text line plus a `trigger-event` part) and a queued run (hop 0, requester the subscriber, `tainted` from the start); a poll `notice` is a system message with no run; then the cursor and `seen` are saved. A failing poll saves its `problem` and keeps its cursor; the others carry on.
- **Gmail's poll** (`plugins/gmail/src/botdesk_gmail/trigger.py`): no cursor → `users.getProfile` `historyId`, nothing else (no backfill). Then `users.history.list(startHistoryId, historyTypes=messageAdded, labelId=INBOX)`: new inbox mail except `SENT`, drafts, spam, Promotions and Social, and mail from the mailbox's own address; at most 10 per poll (a notice counts the rest). 404 (history expired) → back to the current `historyId` with one "missed some new mail" notice.
- **What the run reads.** A trigger message's `trigger-event` part becomes the run's request (`run_service.trigger_prompt`): the event as JSON inside `<untrusted-content>` (with `<` escaped), and "read it with your tools (gmail.read_thread), then do what your instructions say". People see only the text line.
- **Tests:** `plugins/gmail/tests/test_write_tools.py` and `test_trigger.py` (FakeHttp), `tests/test_gmail_tools.py` (policy per tool through the pipeline, an approved send), `tests/test_gmail_trigger.py` (routes, polling on SQLite), `tests/test_gmail_trigger_postgres.py` (two polls racing).

### Bindings (a bot's Tools)

Slice 5.2 ([contract](../architecture/connections-api-contract.md#bot-tools-bindings)). A **binding** lets a bot use one plugin, through one connection when the plugin needs an account. A bot has only the tools of its enabled bindings.

- **Table** `bot_tools` (`models/bot_tool.py`): `bot_id` (cascade), `plugin_id`, `connection_id` (`SET NULL`), `enabled`; one row per bot and plugin. New bots get a binding, on and with no account, for every loaded plugin that doesn't sign in with OAuth (`binding_service.add_defaults`, also used by the seed). The migration gave existing bots every plugin in `PLUGINS`, through the connection 5.1 chose automatically, so nothing changed for them.
- **Routes:** `GET /orgs/{id}/bots/{botId}/tools` → `{plugins: [{pluginId, name, description, authType, enabled, connectionId, tools}]}`, one per loaded plugin (no binding: off, no account). `PUT` the same path with `{plugins: [{pluginId, enabled, connectionId}]}` changes only the plugins sent. Any member may switch plugins (like editing a bot). Choosing a connection: a member's own only by that member, a bot's own (of this bot) by owners, admins and the bot's creator, the organization's by owners and admins (403 otherwise); leaving it unchanged is never refused. Unknown plugin or a connection you can't see: 404; another app's account, another bot's own, or a disconnected one: 400. Changes write `connection.bound` / `connection.unbound` audit lines.
- **Requester:** `runs.requester_id` is the member a run acts for: the author of the message that started the chain (copied to the runs a bot's @mentions start), or the member who set up a routine.
- **Toolset** (`runtime/toolset.py`): `resolve(registry, bindings, scope)` is a pure function; `load(db, registry, run_id)` reads the run, its chat and the bot's bindings with their connections (two queries). `call_model`, `prepare_call` and `execute_tool` each load it again, so a plugin switched off while a run waited is refused on resume ("This tool isn't available any more."). For each enabled binding: no connection keeps the plugin (tools needing an account fail with "connect it first"); a connection this run may not use drops the plugin; a tool whose `scopes` weren't all granted is dropped. A connection is usable when active and member-owned by the requester in the requester's own DM with this bot, bot-owned by this bot, or org-owned.
- **Pipeline:** `prepare(toolset, …, connections=toolset.connections)` adds ` · via=<plugin>:<label> (<ownerKind>)` to the decision trace and `record` saves `connection_id` on the call and its approval. `ExecuteDeps(tools=toolset, connection_ids=…)`; `ToolAccessProvider.open(run, tool, call_id, connection_id=…, timeout_seconds=…)` opens that connection. A call whose binding now points at another account than the one it was decided with fails instead of running.
- **Approvals:** a call through a member's own connection can be decided only by that member (403 for anyone else in the chat); bot- and org-owned ones keep the chat's rule.

### MCP servers

Slices 7.2-7.4 ([ADR 0012](../adr/0012-mcp-servers.md); what changed while building 7.3/7.4: [ADR 0016](../adr/0016-mcp-sign-in-and-review-as-built.md), proposed). An owner or admin adds a remote MCP server (Streamable HTTP over https); it becomes the organization's plugin `mcp-<8 hex>`, and its tools are offered to bots only after an admin reviews them and the server is on in a bot's Tools. Manual test: [docs/testing/mcp.md](../testing/mcp.md).

- **Table** `mcp_servers` (`models/mcp_server.py`, migrations `73107c948749` and `d4b8e1f0a372`): org, `short_id`, name, URL, `auth_kind` (`none` | `header` | `oauth`), `auth_header` (the name), `encrypted_auth` (the header and value, or an OAuth client secret, sealed with the credential vault's key; never returned), `oauth` (what discovery found, the client id and how it was got; no secret), `status` (`active` | `unreachable` | `needs_sign_in`) + reason, `tools` (the **tool snapshot**: per tool the server's name, the local name, title, description, schemas, annotations, a SHA-256 hash of name, title, description and schemas, and the review fields `state`, `enabled`, `risk`, `approvedHash`, `previous`), `tools_hash`, `last_checked_at`, `created_by`. Adding, refreshing, reviewing and removing write `mcp_server.*` audit lines; a risk change writes `mcp_tool.risk_changed`.
- **Module** `services/mcp_server_service.py`: `add`, `refresh`, `review`, `start_sign_in`, `finish_sign_in`, `remove`, `list_servers`, `tools_tab`, and `org_registry(db, registry, org_id, runtime)`, the loaded plugins plus this organization's servers built from their snapshots (only tools offered now). The Tools tab (`GET/PUT /bots/{id}/tools`), the approvals routes and the run's toolset use it. `McpRuntime` (vault, network, the shared `OAuth`, a sessionmaker) lives on the run manager (`runs.mcp`); `ALLOW_PRIVATE_MCP_URLS` sets its network. Pure parts: `mcp/snapshot.py` (snapshot, naming, the review diff) and `mcp/oauth.py` (discovery, registration, token and revocation requests).
- **Names:** tools are `mcp-<id>.<local>`: the server's name lowered to `[a-z0-9]` words joined by `_`, starting with a letter, at most 48 characters, with a 6-hex hash suffix when cut or taken, so `mcp-<id>__<local>` fits the providers' 64. A local name never changes across refreshes. Tools whose schemas are over 64 KB are left out.
- **Review (7.4).** A new server's tools (and a signed-in server's first listing) are `pending`: nothing is offered to a bot until an admin approves it on Review tools (`PUT …/tools`), choosing which are offered and each one's risk (never below `read`; lowering below `external-send` is audited with `lowered: true`). `toolsHash` must be the one the admin looked at (409 otherwise). Servers saved before 7.4 read as approved, offered, `external-send`.
- **Drift.** Every call first lists the server's tools again and compares the tool's hash with the approved one: a changed or vanished tool fails with "This tool changed on the server; an admin must review it in Connect apps before bots use it again.", and the new listing is recorded at once, so Connect apps shows the badge without a Refresh. Refresh records the same. `review_diff`: unchanged tools keep the admin's choices; a **changed** one is not offered and keeps `previous` (title, description, input and output schema as approved) for the diff; a **new** one is `pending`, off; a **removed** approved one shows as `removed` until the next review (and is approved again if it comes back unchanged). `toolsChanged` counts what waits for the review.
- **Bot Tools.** Each MCP server's entry has `mcp: {toolsWaiting, problem, orgAccount}`; a server with nothing offered now is still listed (no tools). Switching a server that uses the organization's key or sign-in (`orgAccount`) on or off takes an owner or admin (403 "Only owners and admins can switch … it uses the organization's sign-in."): that binds an org-owned account (ADR 0010 §3). Keyless servers, as before: any member.
- **OAuth sign-in (7.3).** `mcp/oauth.py` + the shared 5.3 flow, not the SDK's `OAuthClientProvider` (ADR 0016). Discovery: the 401's `resource_metadata` (else the well-known Protected Resource Metadata addresses, path first; none at all means the server's origin is its own authorization server), whose `resource` must be the server's origin and a prefix of its path, then the authorization server's RFC 8414 / OpenID metadata (its `issuer` must match; PKCE S256 required). Client, in the spec's order: a pasted client ID (and secret, sealed); a **Client ID Metadata Document** (`{API_PUBLIC_URL}/api/v1/oauth/client-metadata/<server id>.json`, when the authorization server advertises `client_id_metadata_document_supported` and `API_PUBLIC_URL` is public https); else dynamic registration (RFC 7591, public client, `token_endpoint_auth_method: none`). The authorize URL carries `state` and the PKCE challenge from `oauth_flows`, `resource` (RFC 8707) and the scopes (the challenge's, else the metadata's `scopes_supported`). The callback (`/api/v1/oauth/callback`, shared with Google) consumes the flow, re-checks that the user is still an owner or admin, checks `iss` (RFC 9207: required when the authorization server says it sends one), exchanges the code with the verifier and `resource`, lists the tools with the new token and saves the organization's connection (`connector_id` = the plugin id, `owner_kind` org, sealed by the vault); signing in again reconnects the same row.
- **Tokens in use.** Before each call the access token is refreshed when it has under a minute left, with the same lease, backoff and `needs_reconnect` as Google (`OAuth.refresh_with`), sending `resource` too. A refused refresh or a 401 with a token leaves the sign-in `needs_reconnect` (the server shows Reconnect). A **403 `insufficient_scope`** fails the call with "<name> needs more access than it was given (<scopes>)…", marks the sign-in `needs_reconnect` with that reason (shown as the server's `statusReason`) and adds the scopes to the server's, so Reconnect asks for them; nothing is retried inside the run. Removing the server or disconnecting the sign-in (Your connections) revokes the refresh token at the authorization server's `revocation_endpoint` (RFC 7009) after the commit, best effort.
- **Safety:** every MCP tool starts as `external-send`, egress `open`, untrusted output, not idempotent; annotations are kept to show and never set risk. So under *Ask before acting* every call asks unless an admin lowered it, and its result (including an `isError` one, which reaches the model as `{"text", "isError": true}`) taints the run. A call is limited to 60 s in all (re-check + call), results are cut at 256 KB of text, and the 7.1 client's rules apply: SSRF guard with the checked IP pinned, https only, one origin, 8 MB response cap, sampling/elicitation/roots refused. Every sign-in address (metadata, registration, token, revocation, and the authorize page) is checked the same way (https, no user info, public unless `ALLOW_PRIVATE_MCP_URLS`), connected to through the guard with no redirects, and read with a 256 KB cap; scopes from a server are kept only when they are RFC 6749 scope tokens (at most 30). Tokens, codes, verifiers and client secrets never reach a response, a log line or an audit line (`tests/test_mcp_oauth.py` checks with a marker). Arguments go through as sent (the server checks them against its schema; the model is shown that schema). Of the MCP errors a call can get, only a refusal before the tool ran (JSON-RPC method not found or invalid params, `McpRefused`) reaches the model, as tainting `isError` output; any other MCP error, an answer that isn't MCP, or a tool asking for input may come after the tool ran, so the call's outcome is unknown and the run stops for a person (see Tools and approvals). The URL is shown to every member: keys belong in the header, never in the query string.
- **Tests:** `tests/test_mcp_servers.py` and `tests/test_mcp_review.py` against a real MCP server (the SDK's server side under uvicorn, reached as `mcp.test` through the guard with the test network); `tests/test_mcp_oauth.py` adds one behind a bearer check (401 challenge, 403 step-up) and a fake authorization server (`httpx.MockTransport`: PRM, RFC 8414 metadata, registration, token, revocation).
- **Later:** member- and bot-owned MCP sign-ins (ADR 0012 §3 allows them; v1 has the organization's only); a drift check when nobody calls the tool or presses Refresh (a scheduled re-list); per-server call timeouts; `x-mcp-header` checks.

### Approval JSON

`GET …/approvals`, `GET …/approvals/{id}`, the `decide` response, and the `approval_requested` / `approval_decided` events all use this shape:

```jsonc
{
  "id": "uuid",
  "runId": "uuid", "threadId": "uuid", "botId": "uuid", "toolExecutionId": "uuid",
  "tool": "demo.send_email",               // plugin id + tool name
  "title": "Send an email",                // the tool's human name
  "summary": "Send an email to sara@acme.dev: Launch",
  "riskClass": "external-send",
  "reason": "level=Ask before acting · risk=external-send · tainted=no → ask",  // the policy's trace
  "tainted": false,                        // the run had read outside text: say so on the card
  "args": {"to": "sara@acme.dev", "subject": "Launch", "body": ""},          // what the bot asked for
  "finalArgs": null,                       // what was approved (edited args after an edit); null unless approved
  "argsSchema": {"type": "object", "properties": {}, "required": ["to", "subject"]},  // JSON Schema, for an edit form
  "preview": [{"label": "To", "value": "sara@acme.dev"}, {"label": "Subject", "value": "Launch"}, {"label": "Body", "value": ""}],
  "status": "pending",                     // pending | approved | edited | denied | expired
  "requestedAt": "2026-11-12T12:00:00Z",
  "expiresAt": "2026-11-15T12:00:00Z",
  "decidedAt": null,
  "decidedBy": null                        // {"id", "name"} once a person decided
}
```

`decide` body: `{"decision": "approve"}`, `{"decision": "deny"}`, or `{"decision": "approve", "editedArgs": {…all args…}}` (checked against `argsSchema`; 400 `"Those changes don't fit this action: …"`). An edit also rebuilds `summary` from the edited arguments (the tool's own summary function, as when it asked), so the card describes what runs; `preview` follows `finalArgs` too. In `title`, `summary` and `preview`, a character that doesn't show or reorders the text around it (a zero-width space, a right-to-left override, the invisible "tag" letters; the SDK's `show_hidden`) is written as `[U+202E]`, for every tool, so a card never reads differently from what runs; emoji and scripts keep the joiners they need, `args` stay as they are. Errors: 409 `"This approval was already decided."`, 409 `"This approval expired, so the bot didn't do it."`, 404 `"This approval doesn't exist."`.

The bot's final reply starts with its cards, in the order the calls were made, then the text part, so a reloaded chat shows what showed live. Per call: its `{"type": "approval", "approvalId"}` card if it asked, then `{"type": "tool-call", "toolExecutionId", "tool", "status", "error"?}` (the same fields as `tool_finished`; `status` is `succeeded`, `failed` or `denied`, `error` only when it didn't succeed). A call a person denied (or that expired) has only its card, which already says so. They are built from `tool_executions` (one query) when the reply is saved. There is no org-wide approvals stream yet: the inbox polls the list, chats get the events.

### Try it without an API key

The stand-in model (no key for the bot's provider, from the org or the environment) calls a tool when your message contains `/tool <name> key=value …` (quote values with spaces, or pass one JSON object). With a real key the model gets the same tools through `bind_tools` and decides for itself.

| Message to a bot at *Ask before acting* (the default) | What happens |
|---|---|
| `/tool demo.current_time` | `read`: runs at once |
| `/tool demo.create_note title="Q3 plan" body="Ship it"` | `write-internal`: runs at once |
| `/tool demo.draft_email to=sara@acme.dev subject=Hi` | `write-external`: approval card |
| `/tool demo.send_email to=sara@acme.dev subject=Launch body="See you Thursday"` | `external-send`: approval card; approve, edit or deny |
| `/tool demo.read_inbox` | a `read` that returns outside text (with a prompt injection in it): taints the run |

Set the bot to *Autonomous* and `send_email` runs without asking; to *Read only* and it is refused. Demo notes and "sent" emails live in memory only; their results are in `tool_executions`.

## Memory

Bots remember with mem0 on pgvector, in the same Postgres database ([agents-and-plugins.md §9](../architecture/agents-and-plugins.md#9-memory)). It's on when `MEMORY_ENABLED=true`, the database is Postgres and `OPENAI_API_KEY` is set (mem0 uses OpenAI to pick what's worth keeping and to embed it); otherwise `NoMemory` remembers nothing and says why.

- **Recall and remember:** before the model call the run recalls the top 5 memories for the message; after the reply it saves new ones in the background. Tainted runs save nothing, and neither does a bot whose `memoryEnabled` is off (Edit bot; on by default, read fresh at each step).
- **Scope:** every memory is saved under mem0's three entity keys: `user_id = org:<org id>`, `agent_id = <bot id>` and `run_id` = `shared` (learned in a group chat) or the member's id (learned in their DM). `runtime/memory.py` (`MemoryService`) is the only code that calls mem0, and it always sets all three itself, on every call: `add`, `search`, the list, and `delete_all` (org + bot only: every scope).
- **Why `run_id` and not metadata:** when mem0 extracts new memories it shows its model the scope's last 10 messages and its 10 closest existing memories, and it finds both by these entity keys only (`_build_session_scope` and the `search_filters` in `AsyncMemory._add_to_vector_store`). Metadata is ignored there, so with the member only in metadata, another member's DM messages and memories reached the extraction and could be restated into a shared memory. With `run_id`, a DM's extraction sees only that DM, and a group chat's only group chats (test: `test_a_dm_extraction_never_sees_another_members_dm`, real mem0 with a spy model).
- **Recall in a DM** sees shared memories and that member's: mem0 can't OR across `run_id`s, so it's two searches (`shared`, the member) merged by score, top 5. A search on the memory screen works the same way.
- **Older memories:** ones saved before `run_id` have the scope only in `metadata.member`. Migration `7d2c4e9a1b3f` copies `member` into `run_id` (a no-op when mem0's table doesn't exist yet). A row with neither was never scoped and stays out of every scope (forget everything still deletes it). Raw messages mem0 kept in its local history file under the old scopes are never read again, since every scope now includes `run_id`.
- **Who sees and changes what** (`services/memory_service.py`): you see the bot's shared memories (`scope: "bot"`) and your own DM ones (`scope: "you"`); nobody sees another member's DM memories, owners included. Owners and admins can correct or forget any memory of the bot; members only their own DM ones (a shared one is 403, someone else's is 404). Forget everything is owners and admins only and also clears every member's DM memories of that bot.
- **Isolation is ours, not the client's:** the bot must belong to the org in the URL (404 otherwise); mem0 is asked with the org, bot and allowed members; a memory fetched by id must carry this org and bot or it's 404; and the list is filtered again after mem0 answers.
- **Off or failing:** with `NoMemory` the list is `[]`, forget everything is a no-op and the status says why. A mem0 error is a 503 `"Memory isn't answering right now. Try again in a moment."`.
- **Correcting** uses mem0's `update(memory_id, text=…)`, which re-embeds the text and keeps the memory's scope. A memory deleted between the check and the change (mem0's `ValueError("… not found")`) is a 404, not a 503.
- **Newest first:** mem0's pgvector `get_all` has no `ORDER BY`, so past `limit` it returns an arbitrary subset. Without `q`, the list reads mem0's `bot_memories` table directly (`newest_in_table`): the same scope keys, `ORDER BY` `updated_at` (else `created_at`) as `timestamptz`, `LIMIT`. One query; it scans the bot's rows, like mem0's own list does (mem0 makes no payload index).

```jsonc
// GET /orgs/{id}/bots/{botId}/memories?q=fridays&limit=50   (no q: everything, newest first)
[{ "id": "9f1c…", "text": "The team ships on Fridays", "createdAt": "…", "updatedAt": "…", "scope": "bot" }]
// GET /orgs/{id}/memory/status
{ "enabled": false, "reason": "Memory is off on this server. Set MEMORY_ENABLED=true and add OPENAI_API_KEY to turn it on." }
```

**Not yet:** memory doesn't use the org's OpenAI key from Models & keys. mem0 builds one client (LLM, embedder and a pgvector connection pool) at startup, so a per-org key would mean one cached `AsyncMemory` per org key, with its own pool, rebuilt when the key changes; that's left for later. Also not yet: `memory_audit`, tainted memories, removing a bot's memories when the bot is removed, and paging past `limit` (the list shows the newest `limit`, at most 200).

## Usage and budgets

Settings → Usage & budgets, and each bot's "Budget this month" ([agents-and-plugins.md §4.2](../architecture/agents-and-plugins.md)).

**Recording.** After every model call, `call_model` adds one `usage_records` row in its own short transaction: org, bot, run, provider id (`anthropic`, `openrouter`, `custom-<id>`…), model id (`provider:model`), input and output tokens, and `cost_usd`. Tokens come from the LangChain answer's `usage_metadata`, which streaming fills in too: Anthropic always reports it, and the OpenAI-compatible adapters ask for it with `stream_usage` (`stream_options.include_usage`) for the built-in providers. Custom servers aren't asked (some refuse the field), so they record tokens only if they send them anyway. A finished call that reports no tokens records nothing, and the stand-in never records. The row is written in a `finally`, so a call that **fails or is stopped partway** records too: what the provider reported so far, with the output counted as at least the streamed characters ÷ 4; with nothing reported, an estimate (prompt characters ÷ 4 in, streamed characters ÷ 4 out) if anything streamed. Rows with guessed tokens have `estimated = true` (stored only; the report doesn't show it yet). The insert runs as its own task through `RunManager.unstoppable`: Stop or a timeout cancelling the run can't cancel it, and shutdown (`close`) waits for it. A failed insert is logged and the reply goes on. `bot_id` and `run_id` become null when those are deleted, so the organization's spend stays right. Indexes: `(org_id, created_at)` and `(bot_id, created_at)`.

**Cost** = `input_tokens × input price + output_tokens × output price`, prices in US dollars per million tokens (`services/pricing.py`):

| Provider | Price from |
|---|---|
| OpenRouter | its model list (`ModelCatalog`, the same cache Models & keys uses). If the API hasn't listed it yet, `ModelResolver` fetches it once per org (an `asyncio.Lock`, so runs starting together share one fetch); after a failure the price is unknown for 60 s without trying again. Saving a bot with an OpenRouter model fetches the list after the response (`RunManager.warm_price`), so its first run doesn't wait |
| Anthropic, OpenAI, Gemini, Groq | `PRICE_TABLE` in `services/pricing.py`, dated by `PRICES_CHECKED`. Standard rates, no caching or batch discounts. Exact model ids only, after dropping a date suffix (`-20250929`, `-2024-08-06`, `-latest`), so `gpt-4o` never prices `gpt-4o-mini`. **Effective-dated:** an entry is a price, or `(effective_from, price)` steps; the call uses the step in effect at its time (UTC dates), and a `None` step means the model stops being priced. So an announced change goes in ahead of time (2026-12-01: Gemini 4 Carbon and Argon double, gemini-2.5-pro and 2.5-flash lose their price as Google routes them to other models; 2027-01-01: gemini-3.8-flash doubles) and nobody edits anything on the day. Edit the table when prices change |
| Custom servers | no price |

A model with no price records its tokens and `cost_usd = null`. The web shows those tokens as "without a known price" instead of guessing, and budgets can't stop them.

**Budgets.** Before each model call, `call_model` checks the bot's `monthlyBudgetUsd` and the organization's `monthlyBudgetUsd`. A month is the calendar month in UTC. The run stops when this month's spend is already at the budget, or when spend plus a small estimate of this call (prompt characters ÷ 4 as input tokens, plus 500 output tokens, at the model's price) would pass it. A bot budget of 0 and an org budget of null mean no limit; with neither set, nothing is summed. The spend is one SUM over the `(org_id, created_at)` index for both the bot and the org. A stopped run fails with a message such as `"Inbox Manager reached its $40 monthly budget. Raise it in the bot's settings."` (or `"<Org> reached its $200 monthly budget for all its bots. An owner or admin can raise it in Settings → Usage & budgets."`), and its `run_failed` event carries `code: "budget"`.

**Each call is capped.** When the bot or org has a budget and the model has a price, `call_model` passes `max_tokens` = what's left of the tighter budget, minus the prompt's estimated cost, ÷ the output price per token (`chat_model.output_cap`). It is at least 256, and not passed at all when it would be 16,000 or more (the model's own limit applies then), nor when the model is already held lower (ChatAnthropic's own `max_tokens`). Both LangChain classes take `max_tokens`: ChatAnthropic sends it as is, ChatOpenAI as `max_completion_tokens`.

**Budgets are a soft limit.** The check reads what was spent before the call, and calls already under way aren't counted until they finish. So a budget can be passed by roughly **(calls running at once for that bot or org) × (one call's cost)**, each call's output bounded by the cap above. Once passed, the next call stops.

**Routes** (any member):

`GET /orgs/{id}/usage?days=14` (1–90):

```json
{
  "days": [{"date": "2026-11-13", "modelsUsd": 1.25, "computersUsd": 0, "inputTokens": 12000, "outputTokens": 3000, "unpricedTokens": 0}],
  "monthStart": "2026-11-01",
  "monthToDateUsd": 33.5,
  "orgBudgetUsd": 200,
  "unpricedTokens": 4200,
  "bots": [{"botId": "…", "name": "Scout", "spentUsd": 33.5, "budgetUsd": 40, "inputTokens": 900000, "outputTokens": 120000, "unpricedTokens": 0}],
  "pricesChecked": "2026-11-13"
}
```

`days` are UTC days, oldest first, today included, quiet days as zeros. `computersUsd` stays 0 until bots have computers. `budgetUsd` / `orgBudgetUsd` null = no limit. `monthToDateUsd` includes bots removed this month. `GET /orgs/{id}/bots/{botId}/usage?days=14` is one bot's entry plus its `days` and `monthStart`. The organization's budget is set with `PATCH /orgs/{id}` `{monthlyBudgetUsd}` (owners and admins; null or 0 removes it, leaving it out keeps it).

## Email

Emails go through [Brevo](https://www.brevo.com)'s transactional API (`POST https://api.brevo.com/v3/smtp/email`), from `services/email_service.py`:

- **One interface:** `EmailSender.send(EmailMessage)`. `BrevoEmailSender` when `BREVO_API_KEY` and `EMAIL_FROM_ADDRESS` are set; otherwise `ConsoleEmailSender`, which logs the subject, the recipient and (outside production) the link, so you can click it in dev. Tests swap in a fake that records what was sent (`outbox` fixture).
- **In the background:** controllers hand the email to FastAPI's `BackgroundTasks`, so a request never waits on Brevo. A failure is logged (`Couldn't send email …`), never shown to the user. One shared `httpx.AsyncClient` (10 s timeout) lives in the app lifespan.
- **Templates** live in `src/emails/`: one function per email returning `(subject, html, text)`. Plain HTML with inline CSS, the `botdesk` wordmark as text, one button, the link as text, and "If you didn't ask for this, ignore this email". Names are escaped.
- **Sent today:** password reset links and invitations. A successful send logs Brevo's `messageId`.

Set it up: Brevo → **SMTP & API → API Keys** → generate a key; **Senders & Domains** → verify the sender address. Put both in `apps/api/.env`. Mail from a Gmail address can land in spam: verify your own domain (DKIM and DMARC) in Brevo and send from it.

### Password reset

Follows the OWASP Forgot Password cheat sheet:

1. `forgot-password` always answers 202 with the same text. If the account exists it stores a new token in `password_reset_tokens` (only its SHA-256 hash, like sessions), deletes the user's older unused tokens, and emails `{WEB_APP_URL}/reset-password?token=…`. Known and unknown emails run the same queries, and the email is sent after the response, so timing doesn't reveal accounts.
2. `reset-password` claims the token with one guarded `UPDATE` (unused and not expired), so it works once even under races. It checks the same password rules as sign-up, sets a new Argon2 hash and deletes **all** the user's sessions. A bad, used or expired token gets `400 "This reset link has expired or was already used. Ask for a new one."`
3. The web app's `/reset-password` page reads the token, posts the new password, and sends you to sign in.

### Sign-up modes

`SIGNUP_MODE` is checked in `auth_service.sign_up`, before the email is looked at, so a refusal never says whether an account exists:

| Mode | Without an invite | With `inviteToken` |
|---|---|---|
| `open` (default) | New account + its own organization | New account that joins the inviting organization (no organization of its own). A bad, used or expired invite is refused (403), not quietly ignored |
| `invite-only` | 403 "Sign-up is by invitation. Ask your admin for an invite link." | Same as open, if the invite is unused, unexpired and for this email; otherwise 403 ("This invite link isn't valid any more…" / "This invite is for …") |
| `closed` | 403 "New accounts are turned off on this server. Ask your admin if you need one." | The same 403. Existing people still sign in and accept invites (`POST /invitations/accept`) |

The invite flow is the one that already existed: the link is `/invite/<token>`; signed out, it sends you to `/sign-up?next=/invite/<token>`, and the web sends the token with the sign-up. The invite is used up in the same transaction that creates the account (`invitation_service.join`, shared with accepting an invite), and the web then opens the app instead of the used link. For an internet-facing install: sign up the first owner while `open`, then set `invite-only` and restart the API.

### Rate limits

`core/rate_limit.py` is a small sliding-window limiter in the API process's memory; `services/auth_limits.py` holds the limits and raises `TooManyRequests`, which `main.py` turns into **429** with `Retry-After` (seconds) and `{"detail": "Too many attempts. Try again in 1 minute."}`. The web shows that message as is.

| Route | Per client address | Per email (lowercased) |
|---|---|---|
| sign-in | 10 a minute | 5 a minute |
| sign-up | 20 an hour | |
| forgot-password | 20 an hour | 5 an hour |
| reset-password | 20 an hour | |

- **Nothing leaks:** unknown emails are counted exactly like known ones, and the limit is checked before the database, so a 429 says nothing about accounts. A refused attempt isn't counted, so waiting out `Retry-After` always works; the right password also waits (the point is to stop guessing). The trade-off: someone who knows an email can keep that person from signing in, one minute at a time, while they keep trying; the per-email limits are short for that reason.
- **Bounded memory:** a key keeps at most its limit's timestamps; keys whose window has passed are swept out every 1,000 attempts, and past 50,000 keys the least recently used go first.
- **One process:** counts live in each API process and reset when it restarts. Several API copies would each count on their own: they need a shared store (Postgres or Redis), which comes with the job queue ([ADR 0005](../adr/0005-job-queue-and-scaling.md)).
- **The client address** is the connection's, unless the connection comes from a proxy in `FORWARDED_ALLOW_IPS`; then uvicorn's `ProxyHeadersMiddleware` (added in `main.py`) takes the rightmost address in `X-Forwarded-For` that isn't a trusted proxy. Anyone else's `X-Forwarded-For` is ignored, so a made-up header can't buy a fresh allowance. Behind a reverse proxy that isn't listed, every request looks like it comes from the proxy and shares one allowance: set it (the self-hosting guide shows how for Docker).

## Security choices

- **Passwords:** Argon2id; old hashes are upgraded on sign-in. Unknown emails take as long as wrong passwords.
- **Who can sign up:** `SIGNUP_MODE` (`open`, `invite-only`, `closed`); see [Sign-up modes](#sign-up-modes).
- **Rate limits:** sign-in, sign-up, forgot-password and reset-password, per client address and (sign-in, forgot-password) per email; 429 with `Retry-After`. See [Rate limits](#rate-limits).
- **Reset links:** single use, expire after `PASSWORD_RESET_MINUTES`, only the SHA-256 hash is stored; using one signs out every device.
- **Sessions:** 32 random bytes; only the SHA-256 hash is stored. Cookie is `httpOnly`, `SameSite=Lax`, `Secure` in production. Bearer works for apps.
- **Tenancy:** every `/orgs/{id}/…` route goes through `OrgAccess`. Non-members get 404, so they can't learn an org exists.
- **CORS:** only `WEB_ORIGINS`, with credentials.
- **Secrets:** only in `.env` (git-ignored). `.env.example` lists every setting.
- **Model keys:** encrypted at rest with `SECRET_KEY` (32+ characters, rotatable with `SECRET_KEY_OLD`), never returned or logged; custom model servers pass an SSRF guard in every environment (public addresses only, pinned at connect time, no redirects). See [Models and keys](#models-and-keys).

## Not yet (in order)

1. Approval follow-ups: *retry / skip* for `needs_attention` runs, saved rules ("always allow"), org ceiling, per-call risk raising, `run_steps` audit rows, a tool-calls-per-run limit, an org-wide approvals stream. Then the rest of step 3: `plugins/_template`, a generated and CI-checked `manifest.json`, import rules in CI, release-please for the SDK. Full order: [agents-and-plugins.md §14](../architecture/agents-and-plugins.md#14-build-order-each-step-small-tested-and-usable).
2. Memory: the org's OpenAI key for memory, `memory_audit`, tainted memories; trimming old `run_events` and checkpoints.
3. Email verification; rate limits shared between several API copies.

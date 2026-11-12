# Backend guide (apps/api)

The BotDesk API: one backend for the web, desktop and mobile apps. Python, FastAPI, SQLAlchemy, Alembic. Why this stack: [ADR 0003](../adr/0003-python-backend.md).

## Run it

You need [uv](https://docs.astral.sh/uv/) and Python 3.13 (uv can install it: `uv python install 3.13`).

```bash
cd apps/api
uv sync                  # install dependencies into apps/api/.venv
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
| `pnpm db:seed` | Add the demo team (ali@acme.dev / botdesk123, Sara, Omar in Acme Labs) and three bots. Not in production |
| `pnpm check` | typecheck (mypy) + lint (ruff) + tests, for web and API together |

Inside `apps/api`: `pnpm db:revision "add bots"` writes a new migration from model changes; `pnpm format` formats and fixes lint.

### Settings

Every setting is in [`apps/api/.env.example`](../../apps/api/.env.example). The ones for bots:

| Setting | Default | What it does |
|---|---|---|
| `DATABASE_URL` | local SQLite | The app database. On Neon the **pooled** address is fine |
| `DATABASE_URL_DIRECT` | = `DATABASE_URL` | The **direct** address (Neon: no `-pooler` in the host). Run checkpoints and mem0 keep their own connections here |
| `TEST_DATABASE_URL` | empty | A **separate** database for the Postgres tests. They wipe it. Empty = those tests are skipped |
| `DEFAULT_MODEL_ID` | `anthropic:claude-sonnet-4-5` | The model for bots that don't name one (`provider:model`) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | empty | Provider keys. A bot whose provider has no key answers with a **stand-in reply**, so everything works offline |
| `RUN_MAX_STEPS`, `RUN_MAX_SECONDS` | 25, 900 | Limits on every run; a run that hits one fails with a clear message |
| `BOT_MAX_RUNNING_RUNS` | 2 | Runs one bot may have going at once (across chats) |
| `PLUGINS` | `demo` | Allowlist of built-in plugins to load (comma-separated). `demo` = fake tools for trying approvals |
| `TOOL_TIMEOUT_SECONDS` | 30 | A tool call that takes longer fails |
| `APPROVAL_EXPIRY_HOURS` | 72 | An approval nobody answers in time counts as "no" (checked when someone decides) |
| `MEMORY_ENABLED` | false | mem0 memory on pgvector, in the same database. Also needs Postgres and `OPENAI_API_KEY` |
| `BREVO_API_KEY` | empty | Sends real email through Brevo. Empty = emails are only written to the log (see [Email](#email)) |
| `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME` | empty, BotDesk | The sender. The address must be verified in Brevo |
| `PASSWORD_RESET_MINUTES` | 60 | How long a password reset link works |

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
      errors.py              AppError → NotFound, Conflict, Unauthorized, Forbidden
      handles.py             names → handles and slugs
    models/                  SQLAlchemy tables (one file per area)
    schemas/                 Pydantic request/response shapes (JSON is camelCase)
    services/                business rules + database queries. No HTTP here.
      email_service.py       EmailSender: Brevo, or the log when there's no key
    emails/                  email templates: (subject, html, text)
    controllers/             one request at a time: call services, commit, set cookies
    runtime/                 how a bot run happens (ADR 0007: inside the API process for now)
      runner.py              RunManager: starts and resumes runs as tasks, one at a time per chat, Stop, restart recovery
      graph.py               the LangGraph graph: model ↔ tool pipeline loop, approval_gate (interrupt), save_reply
      tool_pipeline.py       one door for every tool call: validate → risk → policy → record → execute at most once
      policy.py              security level × risk class → auto / ask / deny, plus taint (pure)
      chat_model.py          a bot's model_id → a LangChain chat model, or the stand-in (which obeys `/tool …`)
      prompt.py              instructions + memories + the chat → what the model sees
      token_batcher.py       streamed tokens → a few database writes, not one per token
      limits.py              steps and time per run
      memory.py              MemoryService: NoMemory, or mem0 when switched on
      event_bus.py           wakes a chat's live streams when new events are saved
      reporter.py            saves a run's events
    plugins/                 what bots can do
      sdk.py                 the plugin seam: ToolSpec, PluginManifest, ToolContext, RiskClass (becomes packages/plugin-sdk)
      registry.py            ToolRegistry: allowlisted plugins' tools by full name (`demo.send_email`)
      demo/                  DEMO plugin: fake tools (clock, knowledge base, notes, fake outbox, injected inbox)
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
POST /threads/{id}/messages       one transaction: the message, a queued run per bot that should reply,
                                  and a message_saved event. Returns at once with the run ids.
  → RunManager.start              an asyncio task per run
    → waits for its turn          one run per chat: a lock in this process + a guarded UPDATE in Postgres
    → graph                       load_context → recall → call_model (streams message_delta events)
                                  → tool calls? one at a time through the tool pipeline (see Tools and approvals)
                                  → save_reply (the message + message_saved) → remember (in the background)
    → run_finished / run_failed, or paused: approval_requested (waiting_approval) / run_needs_attention
GET /threads/{id}/events          SSE: replays run_events after Last-Event-ID, then follows new ones
```

The web app reads one stream per open chat. Tokens arrive in batches (about every 50 ms) as `message_delta`; when the reply is saved, `message_saved` carries the whole message, which replaces the streamed text.

A service raises `NotFound("…")`, `Conflict("…")` and so on. `main.py` turns those into `{"detail": "…"}` with the right status, so services never touch HTTP. Controllers own the transaction (`db.commit()`).

## API v1 so far

| Method & path | What it does |
|---|---|
| `GET /api/v1/health` | Up, and the database answers |
| `POST /api/v1/auth/sign-up` | Create account + first organization (you're owner); signs you in |
| `POST /api/v1/auth/sign-in` | Email + password → session cookie |
| `POST /api/v1/auth/sign-out` | Ends this session everywhere it was used |
| `GET /api/v1/auth/me` | You, and your organizations with your role |
| `PATCH /api/v1/auth/me` | Change your name or @handle (unique) |
| `POST /api/v1/auth/change-password` | Needs the current password (wrong one: 400, so the app keeps you signed in); signs out your other devices |
| `POST /api/v1/auth/forgot-password` | Emails a reset link if the account exists. Always the same 202 answer (doesn't reveal accounts) |
| `POST /api/v1/auth/reset-password` | `{token, password}`: sets a new password from the link (once, before it expires) and signs out every device |
| `GET /api/v1/orgs` | Your organizations |
| `GET /api/v1/orgs/{id}` | One organization |
| `PATCH /api/v1/orgs/{id}` | Rename / change address (owner or admin) |
| `GET /api/v1/orgs/{id}/members` | People and their roles |
| `PATCH /api/v1/orgs/{id}/members/{userId}` | Change a role (owners and admins; only owners touch owners) |
| `DELETE /api/v1/orgs/{id}/members/{userId}` | Remove someone, or leave (your own id). There's always one owner |
| `POST /api/v1/orgs/{id}/invitations` | Invite an email as admin or member (owners and admins only; members get 403); emails them the link, and returns it once |
| `GET /api/v1/orgs/{id}/invitations` | Pending invites (owners and admins) |
| `DELETE /api/v1/orgs/{id}/invitations/{invId}` | Revoke an invite |
| `POST /api/v1/invitations/accept` | Join from an invite link (signed in with the invited email) |
| `GET /api/v1/orgs/{id}/bots` | The organization's bots |
| `POST /api/v1/orgs/{id}/bots` | Hire a bot (any member); @handle comes from the name |
| `GET /api/v1/orgs/{id}/bots/{botId}` | One bot |
| `PATCH /api/v1/orgs/{id}/bots/{botId}` | Edit a bot (only the fields you send) |
| `DELETE /api/v1/orgs/{id}/bots/{botId}` | Remove a bot (owners and admins); its chats go too |
| `GET /api/v1/orgs/{id}/threads` | Your chats, most recent first, with a preview of the last message |
| `POST /api/v1/orgs/{id}/threads/dm` | Your chat with a bot (`{botId}`): the existing one or a new one. Private to you |
| `POST /api/v1/orgs/{id}/threads/groups` | Group chat with you plus the people and bots you pick |
| `GET /api/v1/orgs/{id}/threads/{threadId}` | One chat (404 unless you're in it) |
| `GET /api/v1/orgs/{id}/threads/{threadId}/messages` | Messages oldest first; `limit` (1–200) and `before` to page back |
| `POST /api/v1/orgs/{id}/threads/{threadId}/messages` | Send a message (`{text}`). In a DM the bot replies; in a group, the @mentioned bots in it do. Returns the message plus `runIds` |
| `GET /api/v1/orgs/{id}/threads/{threadId}/events` | Live updates (SSE). Resumes after the `Last-Event-ID` header, or `?after=`; otherwise from now. `?follow=false` sends what's saved and closes |
| `GET /api/v1/orgs/{id}/runs/{runId}` | One run: status, steps used, limits, error |
| `POST /api/v1/orgs/{id}/runs/{runId}/cancel` | Stop a run (queued or paused: at once, and its pending approval expires; running: within moments) |
| `GET /api/v1/orgs/{id}/approvals` | Approvals in chats you're in, newest first, max 100. `status` = `pending` (default) / `approved` / `denied` / `edited` / `expired` / `all`; filter with `botId`, `threadId` |
| `GET /api/v1/orgs/{id}/approvals/{approvalId}` | One approval (404 unless you're in its chat) |
| `POST /api/v1/orgs/{id}/approvals/{approvalId}/decide` | `{decision: "approve" or "deny", editedArgs?}`. Decides once and resumes the run. 409 if already decided or expired, 400 if `editedArgs` don't fit the tool |

#### Live events

Each SSE message has `id:` (a growing number), `event:` (the kind) and `data:` JSON in one shape: `{id, kind, runId, threadId, createdAt, data}`. The kinds and their `data`:

| Kind | `data` |
|---|---|
| `message_saved` | `{message}`: the full message, as in the messages list (yours, someone else's, or a bot's reply). `runId` is null for people's messages |
| `run_started` | `{botId}` |
| `message_delta` | `{messageId, botId, text}`: the next piece of a reply. `messageId` is the id the saved reply will have |
| `run_finished` | `{status}`: `succeeded` or `cancelled` |
| `run_failed` | `{status: "failed", error}`: `error` is ready to show |
| `tool_started` | `{toolExecutionId, tool, risk, args}`: a tool call is about to run (`tool` like `demo.send_email`) |
| `tool_finished` | `{toolExecutionId, tool, status, result, error}`: `status` is `succeeded` (with `result`), `failed` (with `error`) or `denied` (refused by the policy; it never ran, `error` says why). Bad arguments or an unknown tool also come as `failed` without a `tool_started` |
| `approval_requested` | `{approval}`: the run paused on a risky call and is now `waiting_approval`. `approval` is the [Approval JSON](#approval-json) |
| `approval_decided` | `{approval}`: someone decided (`approved` / `edited` / `denied`), or it `expired` (run stopped, or decided too late) |
| `run_resumed` | `{botId}`: a paused run carries on after a decision |
| `run_needs_attention` | `{status: "needs_attention", error}`: a tool may have half run (e.g. the API restarted mid-call); a person must check. Stop is the only action so far |

Run `status` values: `queued`, `running`, `waiting_approval`, `needs_attention`, `succeeded`, `failed`, `cancelled`.

Error messages match the web app's wording, e.g. `401 "That email and password don't match."`.

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

- **Policy** (`runtime/policy.py`, pure): the ADR 0004 table, 3 levels × 7 risk classes (`read`, `write-internal`, `write-external`, `external-send`, `spend`, `destructive`, `credential`). The bot's `securityLevel` is the level (no org ceiling or routine level yet).
- **Taint** (strict, run-level): a tool that returns outside text (`untrusted_output`) sets `runs.tainted`. After that, anything above `write-internal` asks, even for Autonomous bots, and the run saves no memories. Outside text reaches the model wrapped in `<untrusted-content>`. An `open`-egress read in a tainted run counts as `external-send`.
- **`tool_executions`** records every call; run id + the model's tool call id is the idempotency key. Status: `ready` → `started` → `succeeded` / `failed`; `waiting_approval` → `ready` (approved) / `denied`; refused calls are saved as `denied` / `failed`. It also stores `risk`, `decision`, `decision_trace`, `args` and `args_hash`. Running a call that already `succeeded` reuses its result; one left `started` stops the run as `needs_attention` unless the tool is idempotent. A tool also gets `ctx.idempotency_key` (`"{runId}:{toolCallId}"`) to pass to services that accept one.
- **Pausing:** `approval_gate` only calls `interrupt({"approvalId"})`. The run task ends, the run becomes `waiting_approval`, and the checkpoint waits in Postgres (it survives restarts; SQLite's in-memory checkpoints don't, and resuming then fails the run with a clear message).
- **Deciding** is one conditional `UPDATE … WHERE status = 'pending'`, together with the tool call's update in one transaction, so a double click or two people can only decide once; the other gets 409. After the commit the API resumes the same checkpoint (thread id = run id) with `Command(resume={"approved", "message"})`. The tool runs with the arguments saved on the `tool_executions` row (the edited ones after an edit), never with arguments from the resume value.
- **Who:** members of the organization who are in the approval's chat (the same people who can see the run; a DM stays private). Any role can decide.
- **Expiry:** approvals expire after `APPROVAL_EXPIRY_HOURS`. With no job queue there is no sweeper yet: an expired approval is noticed when someone decides it (409, and the run is told "no"), or when the run is stopped.
- **Short transactions:** none is open during a model call, a tool call, or the wait for a person.

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

`decide` body: `{"decision": "approve"}`, `{"decision": "deny"}`, or `{"decision": "approve", "editedArgs": {…all args…}}` (checked against `argsSchema`; 400 `"Those changes don't fit this action: …"`). Errors: 409 `"This approval was already decided."`, 409 `"This approval expired, so the bot didn't do it."`, 404 `"This approval doesn't exist."`.

The bot's final reply starts with one `{"type": "approval", "approvalId"}` part per approval asked for in that run, then the text part, so a reloaded chat can show the cards. There is no org-wide approvals stream yet: the inbox polls the list, chats get the events.

### Try it without an API key

The stand-in model (no `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) calls a tool when your message contains `/tool <name> key=value …` (quote values with spaces, or pass one JSON object). With a real key the model gets the same tools through `bind_tools` and decides for itself.

| Message to a bot at *Ask before acting* (the default) | What happens |
|---|---|
| `/tool demo.current_time` | `read`: runs at once |
| `/tool demo.create_note title="Q3 plan" body="Ship it"` | `write-internal`: runs at once |
| `/tool demo.draft_email to=sara@acme.dev subject=Hi` | `write-external`: approval card |
| `/tool demo.send_email to=sara@acme.dev subject=Launch body="See you Thursday"` | `external-send`: approval card; approve, edit or deny |
| `/tool demo.read_inbox` | a `read` that returns outside text (with a prompt injection in it): taints the run |

Set the bot to *Autonomous* and `send_email` runs without asking; to *Read only* and it is refused. Demo notes and "sent" emails live in memory only; their results are in `tool_executions`.

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

## Security choices

- **Passwords:** Argon2id; old hashes are upgraded on sign-in. Unknown emails take as long as wrong passwords.
- **Reset links:** single use, expire after `PASSWORD_RESET_MINUTES`, only the SHA-256 hash is stored; using one signs out every device.
- **Sessions:** 32 random bytes; only the SHA-256 hash is stored. Cookie is `httpOnly`, `SameSite=Lax`, `Secure` in production. Bearer works for apps.
- **Tenancy:** every `/orgs/{id}/…` route goes through `OrgAccess`. Non-members get 404, so they can't learn an org exists.
- **CORS:** only `WEB_ORIGINS`, with credentials.
- **Secrets:** only in `.env` (git-ignored). `.env.example` lists every setting.

## Not yet (in order)

1. Wire the web app's sign-in to this API (replace the mock in `apps/web/src/data/store.ts`).
2. Approval follow-ups: an expiry sweeper (needs the job queue), *retry / skip* for `needs_attention` runs, saved rules ("always allow"), org ceiling and routine levels, per-call risk raising, `run_steps` audit rows, a tool-calls-per-run limit, an org-wide approvals stream. Then the plugin SDK (step 3). Full order: [agents-and-plugins.md §14](../architecture/agents-and-plugins.md#14-build-order-each-step-small-tested-and-usable).
3. The job queue (procrastinate) and a separate worker, deferred by [ADR 0007](../adr/0007-runs-in-the-api-process-for-now.md); then the Postgres `LISTEN/NOTIFY` bus for several API copies.
4. Memory screens (see, edit, delete) and `memory_audit`; trimming old `run_events` and checkpoints.
5. Email verification, rate limiting on sign-in and forgot-password.

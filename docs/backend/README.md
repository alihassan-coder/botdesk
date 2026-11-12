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
| `pnpm start:api` | Migrate, then run without reload (production style) |
| `pnpm test:api` | pytest: unit and HTTP tests on in-memory SQLite (~5 s, no network) |
| `pnpm db:migrate` | Apply migrations to `DATABASE_URL` |
| `pnpm db:seed` | Add the demo team (ali@acme.dev / botdesk123, Sara, Omar in Acme Labs). Not in production |
| `pnpm check` | typecheck (mypy) + lint (ruff) + tests, for web and API together |

Inside `apps/api`: `pnpm db:revision "add bots"` writes a new migration from model changes; `pnpm format` formats and fixes lint.

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
      security.py            password hashing, session tokens
      errors.py              AppError → NotFound, Conflict, Unauthorized, Forbidden
      handles.py             names → handles and slugs
    models/                  SQLAlchemy tables (one file per area)
    schemas/                 Pydantic request/response shapes (JSON is camelCase)
    services/                business rules + database queries. No HTTP here.
    controllers/             one request at a time: call services, commit, set cookies
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

A service raises `NotFound("…")`, `Conflict("…")` and so on. `main.py` turns those into `{"detail": "…"}` with the right status, so services never touch HTTP. Controllers own the transaction (`db.commit()`).

## API v1 so far

| Method & path | What it does |
|---|---|
| `GET /api/v1/health` | Up, and the database answers |
| `POST /api/v1/auth/sign-up` | Create account + first organization (you're owner); signs you in |
| `POST /api/v1/auth/sign-in` | Email + password → session cookie |
| `POST /api/v1/auth/sign-out` | Ends this session everywhere it was used |
| `GET /api/v1/auth/me` | You, and your organizations with your role |
| `POST /api/v1/auth/forgot-password` | Always the same answer (doesn't reveal accounts) |
| `GET /api/v1/orgs` | Your organizations |
| `GET /api/v1/orgs/{id}` | One organization |
| `PATCH /api/v1/orgs/{id}` | Rename / change address (owner or admin) |
| `GET /api/v1/orgs/{id}/members` | People and their roles |
| `PATCH /api/v1/orgs/{id}/members/{userId}` | Change a role (owners and admins; only owners touch owners) |
| `DELETE /api/v1/orgs/{id}/members/{userId}` | Remove someone, or leave (your own id). There's always one owner |
| `POST /api/v1/orgs/{id}/invitations` | Invite an email as admin or member; returns the invite link once |
| `GET /api/v1/orgs/{id}/invitations` | Pending invites (owners and admins) |
| `DELETE /api/v1/orgs/{id}/invitations/{invId}` | Revoke an invite |
| `POST /api/v1/invitations/accept` | Join from an invite link (signed in with the invited email) |

Error messages match the web app's wording, e.g. `401 "That email and password don't match."`.

## Security choices

- **Passwords:** Argon2id; old hashes are upgraded on sign-in. Unknown emails take as long as wrong passwords.
- **Sessions:** 32 random bytes; only the SHA-256 hash is stored. Cookie is `httpOnly`, `SameSite=Lax`, `Secure` in production. Bearer works for apps.
- **Tenancy:** every `/orgs/{id}/…` route goes through `OrgAccess`. Non-members get 404, so they can't learn an org exists.
- **CORS:** only `WEB_ORIGINS`, with credentials.
- **Secrets:** only in `.env` (git-ignored). `.env.example` lists every setting.

## Not yet (in order)

1. Wire the web app's sign-in to this API (replace the mock in `apps/web/src/data/store.ts`).
2. Invite emails (the link is copied by hand until an email provider is added).
3. Bots, then threads and messages with streamed replies (SSE).
4. Agent runtime: LangGraph + LangChain models, Postgres checkpointer, approvals via `interrupt()`.
5. Memory with mem0 (pgvector).
6. Password reset emails, email verification, rate limiting on sign-in.

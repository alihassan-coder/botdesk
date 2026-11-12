# 0003 — Python backend: FastAPI, SQLAlchemy, Alembic, LangGraph, mem0

- Status: accepted
- Date: 2026-11-12
- Replaces: the backend stack in [architecture §0 D7 and §4](../architecture/high-level.md) (Node.js, Hono, oRPC, Drizzle, Better Auth, DBOS)

## Context

The architecture proposal planned a TypeScript backend. The owner chose Python instead, for its AI ecosystem (LangChain, LangGraph, mem0) and because they want to work in it. The web app keeps running on mock data until each API slice is ready, so the change costs nothing in the UI.

## Decisions

1. **Language and tooling:** Python 3.13, managed with **uv** (`pyproject.toml` + `uv.lock`). Lint and format with **ruff**, types with **mypy (strict)**, tests with **pytest**.
2. **HTTP:** **FastAPI** on **uvicorn**. Every route lives under **`/api/v1`**. Streaming uses FastAPI's built-in Server-Sent Events (`fastapi.sse`).
3. **Code layout: layered.** routes → controllers → services → models (details in [docs/backend](../backend/README.md)).
4. **Database:** **PostgreSQL** (hosted **Neon** for development; pgvector available), through **SQLAlchemy 2 (async)** with the **psycopg 3** driver. Schema changes only through **Alembic** migrations. Tests use in-memory SQLite, so they need no network.
5. **Auth: our own, small.** Email + password with **Argon2id** hashes. Sign-in creates an opaque random session token; the database stores only its SHA-256 hash. The web app gets it as an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production). Desktop and mobile send the same token as `Authorization: Bearer`. Organizations, memberships and roles (owner, admin, member) are our own tables. Better Auth is dropped (TypeScript only).
6. **Agents (later slice):** bots run as **LangGraph** graphs over **LangChain** chat models (`init_chat_model`, any provider). Durable runs and approvals use LangGraph's **Postgres checkpointer** with `interrupt()` / `Command(resume=…)`. Long-term memory uses **mem0** on pgvector, scoped per organization and bot, with its telemetry turned off.
7. **One step at a time:** login and organizations first, then bots, then chat with streaming, then the agent runtime, approvals and memory.

## Consequences

- `apps/api` is a Python project inside the pnpm workspace. A small `package.json` maps `dev`, `test`, `lint` and `typecheck` to `uv run …`, so `pnpm dev:api`, `pnpm check` and Turborepo work as before.
- The typed web client comes from FastAPI's OpenAPI schema (`/api/openapi.json`) instead of oRPC; the generator is chosen in the slice that wires the web app to the API.
- **License note:** psycopg 3 is **LGPL-3.0**. We use it unmodified as a separately installed library, which LGPL allows in an MIT project. This ADR records that exception to the "MIT-compatible only" rule.
- On Windows, psycopg's async mode needs the selector event loop. The dev and start scripts pass `--loop asyncio:SelectorEventLoop` to uvicorn, and Alembic sets the same loop.
- The architecture doc's sections on DBOS, Hono, oRPC, Drizzle and Better Auth are history; the rest (plugins, security levels, approvals, data model) still applies.

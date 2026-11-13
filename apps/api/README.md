# @botdesk/api

The BotDesk backend: one API for web, desktop and mobile. Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL (Neon).

```bash
uv sync --all-packages && cp .env.example .env   # once (uv uses the workspace at the repo root)
pnpm dev:api                      # from the repo root → http://localhost:8000/api/docs
```

Everything else (folders, how a request flows, routes, security, what's next): [docs/backend/README.md](../../docs/backend/README.md). Why Python: [ADR 0003](../../docs/adr/0003-python-backend.md).

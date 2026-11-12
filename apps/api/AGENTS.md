# apps/api: rules for agents

Python 3.13 + FastAPI. Read [docs/backend/README.md](../../docs/backend/README.md) first.

- **Layers, one direction:** `api/v1/routes` → `controllers` → `services` → `models`. Routes only declare HTTP. Controllers commit and set cookies. Services hold rules and queries and raise `core.errors` (never `HTTPException`).
- **Every route under `/api/v1`.** A new area = `models/x.py`, `schemas/x.py`, `services/x_service.py`, `controllers/x_controller.py`, `api/v1/routes/x.py`, then include it in `api/v1/router.py`.
- **Tenant data:** routes under `/orgs/{org_id}/…` must take `OrgAccess` and filter by `access.org.id`.
- **Schema changes:** edit the model, then `pnpm db:revision "what changed"` in `apps/api`, review the file, run `pnpm test`. Never edit the database by hand.
- **JSON is camelCase:** response/request models extend `schemas.common.ApiModel`. Error text matches the web app's wording.
- **Tests first for logic** (`mattpocock-skills:tdd`). HTTP tests use the `client` fixture in `tests/conftest.py` (in-memory SQLite).
- **Before committing:** `pnpm lint && pnpm typecheck && pnpm test` in `apps/api` (ruff, mypy strict, pytest).
- **Dependencies:** `uv add <pkg>` (dev: `uv add --dev`). MIT/Apache/BSD only; anything else needs an ADR (psycopg's LGPL is recorded in ADR 0003).
- **Windows:** keep `--loop asyncio:SelectorEventLoop` in the uvicorn scripts; psycopg async needs it.
- **Build slowly:** the owner wants one slice at a time. Don't add agent, LangGraph or mem0 code until that slice starts (see "Not yet" in the backend guide).

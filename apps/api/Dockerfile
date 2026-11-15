# syntax=docker/dockerfile:1
#
# The BotDesk API image. One image, started different ways (docs/architecture/repo-structure.md):
#   api      uvicorn (the default command below)
#   migrate  alembic upgrade head
#   worker   python -m src.worker   (later, when the job queue lands: ADR 0005 / 0007)
#
# Build from the REPO ROOT (the API needs the uv workspace: packages/plugin-sdk and plugins/*):
#   docker build -f apps/api/Dockerfile -t botdesk-api .
# Normally deploy/docker-compose.yml builds it for you.

ARG PYTHON_VERSION=3.13

# ---- build: install the API's dependencies into /app/.venv with uv ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

# Byte-compile for faster starts; copy (not hard-link) out of the cache mount; use this image's
# Python, never a downloaded one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# The workspace (root pyproject.toml + uv.lock) and its members. The SDK and plugins are small,
# so they are copied whole: uv builds them as wheels in the next step.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/README.md apps/api/
COPY packages/plugin-sdk packages/plugin-sdk
COPY plugins plugins

# Only what the API needs at run time (no dev tools). --no-editable installs the SDK and the
# built-in plugins as real packages, so the final image doesn't need their source folders.
# psycopg[binary] bundles libpq, so no system packages are needed.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package botdesk-api

# The API itself (it runs from src/; it is not an installed package).
COPY apps/api/alembic.ini apps/api/
COPY apps/api/migrations apps/api/migrations
COPY apps/api/src apps/api/src

# ---- runtime: Python, the venv and the code; runs as a non-root user ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# mem0 writes a small config folder (MEM0_DIR); its telemetry stays off.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    MEM0_DIR=/home/botdesk/.mem0 \
    MEM0_TELEMETRY=False

RUN groupadd --system --gid 10001 botdesk \
 && useradd --system --uid 10001 --gid botdesk --create-home --home-dir /home/botdesk botdesk

COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/apps/api /app/apps/api

# alembic.ini and the `from src...` imports both expect to run from apps/api.
WORKDIR /app/apps/api
USER botdesk

EXPOSE 8000

# /api/v1/health answers 200 only when the API can reach the database.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

# The same server command as `pnpm start:api` (apps/api/package.json), minus the migration:
# in compose the `migrate` service runs that once before the API starts.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio:SelectorEventLoop"]

# Getting started

This guide takes you from a fresh clone to the web app and API running on your machine. It takes about 15 minutes, most of it waiting for downloads.

You can stop after **Step 2** if you only want to try the web app on demo data.

## Step 1: install the tools

| Tool | Version | Why | Get it |
|---|---|---|---|
| Git | any recent | Get the code | [git-scm.com](https://git-scm.com) |
| Node.js | 22 or newer | Runs the web app | [nodejs.org](https://nodejs.org) (or `nvm use`, which reads `.nvmrc`) |
| pnpm | the version in `package.json` | Installs JavaScript packages | `corepack enable` (sets up the right version), or [pnpm.io](https://pnpm.io/installation) |
| Python | 3.13 | Runs the API | [python.org](https://www.python.org), or let uv install it: `uv python install 3.13` |
| uv | any recent | Installs Python packages | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |

Check them:

```bash
node --version    # v22 or newer
pnpm --version
uv --version
```

## Step 2: run the web app on demo data

```bash
git clone https://github.com/alihassan-coder/botdesk.git
cd botdesk
pnpm install
pnpm dev:web
```

Open <http://localhost:3000>. Click **Explore the demo**, or sign in with `ali@acme.dev` / `botdesk123`.

In this mode everything is pretend data that lives in your browser. Nothing is saved, and there's no server to set up. It's the fastest way to see what BotDesk does.

## Step 3: get a database

The API stores everything in **PostgreSQL**. Pick one option:

- **Easiest: Neon (free, nothing to install).** Create a project at [neon.tech](https://neon.tech). On the dashboard, click **Connect** and copy the connection string. It looks like `postgresql://user:password@ep-something.neon.tech/neondb?sslmode=require`.
- **Your own Postgres 15+.** Any local or hosted Postgres works. Your connection string looks like `postgresql://user:password@localhost:5432/botdesk`.
- **Just trying the API?** Skip this step. Without a database URL, the API uses a local SQLite file (`apps/api/botdesk.db`). That's fine for exploring, but some later features (memory, durable bot runs) need Postgres.

## Step 4: configure and start the API

```bash
uv sync --all-packages  # from the repo root: installs every Python package into .venv
cd apps/api
cp .env.example .env    # your local settings (never committed)
```

Open `apps/api/.env` and set your database URL:

```ini
DATABASE_URL=postgresql://user:password@your-host/neondb?sslmode=require
```

Every setting is explained in `.env.example`. Then go back to the repo root:

```bash
cd ../..
pnpm db:migrate         # creates the tables
pnpm db:seed            # optional: adds the demo team (ali@acme.dev / botdesk123)
pnpm dev:api            # API at http://localhost:8000
```

Or run both together with `pnpm dev`. Both reload when you save a file: the API watches `apps/api/src`, the web app hot-reloads in the browser.

Open <http://localhost:8000/api/docs>. You'll see every API route and can try them in the browser.

## Step 5: connect the web app to the API

Tell the web app where the API is:

```bash
cp apps/web/.env.example apps/web/.env.local
```

Make sure it contains:

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Restart `pnpm dev:web`. Sign-in, organizations, members, invites and bots now use the real API and your database. Parts that aren't built on the API yet still use demo data.

## Step 6: run the checks

Before you open a pull request:

```bash
pnpm check        # type checks, linting and unit tests for web and API
pnpm test:e2e     # browser tests; they use your installed Google Chrome
```

## Common problems

| Problem | Fix |
|---|---|
| `pnpm: command not found` | Run `corepack enable` (comes with Node.js), then try again. |
| `Port 3000 (or 8000) is already in use` | An old dev server is still running. The message shows the exact `taskkill` command to stop it; run it, then start again. |
| API won't start: `password authentication failed` or `could not translate host name` | Check `DATABASE_URL` in `apps/api/.env`. For Neon, keep `?sslmode=require` at the end. |
| Web app shows demo data even though the API is running | Check `apps/web/.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000`, then restart `pnpm dev:web`. |
| Sign-in works on the API docs page but not in the web app | The API only accepts calls from `WEB_ORIGINS` in `apps/api/.env`. Default: `http://localhost:3000`. |
| Windows: odd event-loop errors from the database driver | Start the API with `pnpm dev:api` (it sets the right event loop), not plain `uvicorn`. |

Still stuck? [Open an issue](https://github.com/alihassan-coder/botdesk/issues/new/choose) with what you ran and the error you saw.

## Where to go next

- **[docs/README.md](README.md):** a map of all the documentation
- **[Frontend guide](frontend/README.md):** how the web app is organised
- **[Backend guide](backend/README.md):** how the API is organised, and every route
- **[How bots think and how plugins plug in](architecture/agents-and-plugins.md):** the core design
- **[CONTRIBUTING.md](../CONTRIBUTING.md):** how to send your first pull request

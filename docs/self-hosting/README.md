# Self-hosting BotDesk

Run BotDesk on your own server with Docker: Postgres, the API and the web app, started with one command. BotDesk is free and MIT licensed; there is no hosted version ([ADR 0008](../adr/0008-free-and-open-source.md)), so this is how you run it for real.

> **Early software.** BotDesk is in early development. Back up your database before every update.

## What runs

`deploy/docker-compose.yml` starts four containers:

| Service | What it does |
|---|---|
| `postgres` | PostgreSQL 17 with pgvector (for bot memory). Data lives in the `postgres-data` volume. Not reachable from outside Docker. |
| `migrate` | Brings the database tables up to date (`alembic upgrade head`), then exits. Runs on every start, so updates migrate themselves. |
| `api` | The BotDesk API on port 8000. Bot runs happen inside this process for now ([ADR 0007](../adr/0007-runs-in-the-api-process-for-now.md)), so run **one** copy and don't scale it. |
| `web` | The web app on port 3000. |

There is no separate worker yet. It arrives with the job queue ([ADR 0005](../adr/0005-job-queue-and-scaling.md)) as the same API image started another way; the compose file has a commented stub for it.

## Requirements

- **Docker Engine 24+ with Compose v2.20+** (`docker compose version`). Docker Desktop works too.
- **2 GB RAM, 2 CPUs, 10 GB disk** is comfortable for a small team. Building the images the first time needs more memory (about 3 GB for the web build) and takes several minutes.
- **The BotDesk repository** (`git clone https://github.com/alihassan-coder/botdesk.git`). The images are built from it on your machine; there are no published images yet.
- **A domain and HTTPS** for anything beyond trying it on your own machine (see [HTTPS with a reverse proxy](#https-with-a-reverse-proxy)).
- Optional: a model provider key (Anthropic, OpenAI, …). People can also add their own in **Settings → Models & keys**. Without any key, bots answer with a stand-in reply.

## Quick start (on your own machine)

Run these from the repo root.

**1. Copy the settings file.**

```bash
cp deploy/.env.example deploy/.env
```

**2. Generate the two secrets** and put them in `deploy/.env`:

```bash
openssl rand -base64 48   # → SECRET_KEY=   (encrypts saved model keys; keep it, don't change it)
openssl rand -hex 24      # → POSTGRES_PASSWORD=
```

No `openssl`? `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` works for both. Keep `POSTGRES_PASSWORD` to letters and digits: it goes inside a database URL.

Compose refuses to start while either is empty, and the API refuses to start in production with a `SECRET_KEY` shorter than 32 characters.

**3. Start it.**

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

The first run builds both images (several minutes). Watch progress with `docker compose -f deploy/docker-compose.yml ps` until `api` and `web` show `healthy` / `running` and `migrate` shows `exited (0)`.

**4. Open <http://localhost:3000>.**

**5. Sign up.** There is no admin account to configure: every person who signs up gets their own new organization and is its **owner**. Invite your team from **Settings → Members**; people who accept an invite join *your* organization instead of only their own.

> **Sign-up is open.** Anyone who can reach your web app can create an account (with their own, separate organization; they can't see yours). There is no switch to close sign-up yet, so keep BotDesk on a private network or behind your reverse proxy's access control if that matters to you.

Without `BREVO_API_KEY`, no email is sent. Invites still work: the invite dialog shows a one-time link to copy and share yourself. Password-reset emails are only noted in the API log (`docker compose -f deploy/docker-compose.yml logs api`), without the link, since in production links carry sign-in tokens. Set up Brevo (below) before people need to reset passwords.

## Settings

Everything lives in `deploy/.env`; [`deploy/.env.example`](../../deploy/.env.example) explains each line. The ones that matter most:

| Setting | What it is |
|---|---|
| `SECRET_KEY` | **Required.** Encrypts saved model keys. Lose it and those keys must be added again. To rotate: see `SECRET_KEY_OLD` in [`apps/api/.env.example`](../../apps/api/.env.example). |
| `POSTGRES_PASSWORD` | **Required** for the bundled Postgres. |
| `NEXT_PUBLIC_API_URL` | The API's address **as browsers reach it**. Built into the web app: after changing it, run `up -d --build`. Left empty, the web app runs on demo data only. |
| `WEB_ORIGINS`, `WEB_APP_URL` | The web app's address as browsers reach it, exactly (scheme, host, port, no trailing slash). The API only accepts signed-in calls from `WEB_ORIGINS`; invite links point to `WEB_APP_URL`. |
| `ENVIRONMENT` | `production` (default): Secure cookies, no `/api/docs`. See [Testing over plain http](#testing-over-plain-http-on-your-lan). |
| `BIND_ADDRESS` | `127.0.0.1` (default): ports are only reachable from this machine. `0.0.0.0`: from your network too. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, … | Instance-wide model keys, used when an organization hasn't added its own. |
| `MEMORY_ENABLED` | `true` lets bots remember facts (needs `OPENAI_API_KEY`). |
| `BREVO_API_KEY`, `EMAIL_FROM_ADDRESS` | Send invite and password-reset emails through Brevo (verify the sender in Brevo first). |

Any other API setting from `apps/api/.env.example` (run limits, `PLUGINS`, session length, …) can be added to `deploy/.env` too. Restart to apply: `docker compose -f deploy/docker-compose.yml up -d`.

## HTTPS with a reverse proxy

For anything other than `localhost`, put BotDesk behind a reverse proxy that serves HTTPS. In production the sign-in cookie is marked **Secure** (the API sets it whenever `ENVIRONMENT=production`), so browsers only keep it over HTTPS.

The simplest setup is **one domain**: the proxy sends `/api/*` to the API and everything else to the web app. The web app has no `/api` routes of its own, and the browser then talks to a single origin.

[Caddy](https://caddyserver.com) gets and renews the certificate for you. On the same server, with BotDesk on its default `127.0.0.1` ports, a `Caddyfile`:

```caddy
botdesk.example.com {
	handle /api/* {
		reverse_proxy 127.0.0.1:8000
	}
	handle {
		reverse_proxy 127.0.0.1:3000
	}
}
```

Then in `deploy/.env`:

```ini
NEXT_PUBLIC_API_URL=https://botdesk.example.com
WEB_ORIGINS=https://botdesk.example.com
WEB_APP_URL=https://botdesk.example.com
ENVIRONMENT=production
BIND_ADDRESS=127.0.0.1
```

and rebuild, since `NEXT_PUBLIC_API_URL` changed: `docker compose -f deploy/docker-compose.yml up -d --build`.

Notes:

- Bot replies stream over Server-Sent Events (`/api/v1/.../events`). Caddy passes them through as they arrive. With nginx, turn buffering off for `/api/` (`proxy_buffering off;`, `proxy_read_timeout 1h;`).
- Two subdomains also work (`app.example.com` for the web app, `api.example.com` for the API): set `NEXT_PUBLIC_API_URL=https://api.example.com` and `WEB_ORIGINS` / `WEB_APP_URL` to `https://app.example.com`. Keep both under the same parent domain so the cookie counts as same-site.
- Keep `BIND_ADDRESS=127.0.0.1` so ports 3000 and 8000 are not open to the internet next to the proxy.

## Testing over plain http on your LAN

`http://localhost` works out of the box: browsers keep Secure cookies on localhost. Over plain http to another address (`http://192.168.1.20:3000`), they don't, so you can sign up but every page sends you back to sign-in.

For a quick test on a trusted network only:

```ini
ENVIRONMENT=development      # cookies without Secure; /api/docs becomes public
BIND_ADDRESS=0.0.0.0
NEXT_PUBLIC_API_URL=http://192.168.1.20:8000
WEB_ORIGINS=http://192.168.1.20:3000
WEB_APP_URL=http://192.168.1.20:3000
```

then `up -d --build`. `SECRET_KEY` stays required (compose checks it). Switch back to `production` with HTTPS before other people use it.

## Updating

```bash
git pull
docker compose -f deploy/docker-compose.yml up -d --build
```

`migrate` runs first and updates the tables; the API starts only if that succeeds. Back up first (below), and read the release notes' "Upgrading" section when there is one. Migrations only go forward.

## Backups

The data that matters is in Postgres, plus your `deploy/.env` (without `SECRET_KEY`, saved model keys can't be read).

Back up (a compressed dump, safe while BotDesk runs):

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U botdesk -d botdesk -Fc > botdesk-$(date +%F).dump
```

Restore into a fresh install (this replaces what's in the database):

```bash
docker compose -f deploy/docker-compose.yml up -d postgres
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_restore -U botdesk -d botdesk --clean --if-exists --no-owner < botdesk-2026-11-15.dump
docker compose -f deploy/docker-compose.yml up -d
```

Run the backup from cron (daily is a good start) and copy the files somewhere off the server.

## Using Neon (or your own Postgres) instead

Any Postgres 15+ works if the `vector` extension (pgvector) is available; [Neon](https://neon.tech) has it.

1. In `deploy/.env`, set both addresses (Neon: **Connect** in the dashboard; keep `?sslmode=require`):

   ```ini
   DATABASE_URL=postgresql://USER:PASSWORD@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require
   DATABASE_URL_DIRECT=postgresql://USER:PASSWORD@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```

   The pooled address is fine for the app; the direct one (no `-pooler`) is for run checkpoints and memory, which keep their own connections.
2. In `deploy/docker-compose.yml`, delete the `postgres` service and the `depends_on: postgres` block under `migrate`. `POSTGRES_PASSWORD` is then no longer needed.
3. `docker compose -f deploy/docker-compose.yml up -d --build`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `required variable SECRET_KEY is missing a value` (or `POSTGRES_PASSWORD`) | Fill it in `deploy/.env` (step 2). The file must be in `deploy/`, next to the compose file. |
| `api` restarts with `SECRET_KEY is too short` | Use at least 32 characters: `openssl rand -base64 48`. |
| `migrate` exits with an error, `api` never starts | `docker compose -f deploy/docker-compose.yml logs migrate`. Usually the database address or password. If you changed `POSTGRES_PASSWORD` after the first start, the volume still has the old one: put the old one back (or, on a test install only, `down -v` to delete the data and start over). |
| The web app shows demo data, or "Explore the demo" only | `NEXT_PUBLIC_API_URL` was empty when the web image was built. Set it, then `up -d --build`. |
| "Can't reach botdesk right now" in the web app | The browser can't reach `NEXT_PUBLIC_API_URL`. Open `<that URL>/api/v1/health` in the same browser: it should say `{"status":"ok"}`. |
| Sign-in seems to work, then you're back at sign-in | The cookie was dropped: plain http on a non-localhost address with `ENVIRONMENT=production`. Use HTTPS, or see [Testing over plain http](#testing-over-plain-http-on-your-lan). |
| Sign-in fails with a network or CORS error in the browser console | `WEB_ORIGINS` doesn't match the web app's address exactly (scheme, host, port). Fix it and `up -d`. |
| Bots answer with a stand-in reply | No model key: add one in **Settings → Models & keys**, or set `ANTHROPIC_API_KEY` (etc.) in `deploy/.env`. |
| Invite or reset emails never arrive | Without `BREVO_API_KEY` and a verified `EMAIL_FROM_ADDRESS` nothing is sent (`docker compose -f deploy/docker-compose.yml logs api` shows "Email not sent"). Copy the invite link from the invite dialog instead, or set up Brevo. |
| A reply stopped half way after a restart | Expected for now: a restart fails unfinished runs ([ADR 0007](../adr/0007-runs-in-the-api-process-for-now.md)). Send the message again. |
| Web image build is killed | Not enough memory for `next build`. Give Docker 3 GB or more, or add swap. |

Health checks you can run yourself: `curl http://localhost:8000/api/v1/health` (API and database) and `docker compose -f deploy/docker-compose.yml ps`.

## Local development database

Contributors without Neon can run just Postgres with pgvector:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d
```

then set `DATABASE_URL=postgresql://botdesk:botdesk@localhost:5432/botdesk` in `apps/api/.env` (and, for the Postgres tests, `TEST_DATABASE_URL=postgresql://botdesk:botdesk@localhost:5432/botdesk_test`). See [getting-started.md](../getting-started.md).

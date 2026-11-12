# BotDesk

Open-source (MIT) Grok Bot: your team of always-on AI bots. Any model, self-hostable, approvals built in.

> Early stage: the web UI is done on mock data; the Python backend is starting. What we are building: [docs/product/spec.md](docs/product/spec.md). Progress so far: [docs/PROGRESS.md](docs/PROGRESS.md). For agents: [AGENTS.md](AGENTS.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Next.js web app (first client), on mock data for now |
| `apps/api` | Python API (in progress) |
| `apps/desktop`, `apps/mobile` | Electron and Expo clients (coming soon) |
| `packages/*` | Shared code: UI, database, core logic, API client (planned) |

## Develop

```bash
pnpm install        # once, and after pulling new dependencies
pnpm dev:web        # web app on http://localhost:3000
```

Sign in with the demo account `ali@acme.dev` / `botdesk123`. Sign-in is a mock until the backend lands.

Each app gets its own `dev:<app>` command. `pnpm dev` runs every app at once.

| Command | What it does |
|---|---|
| `pnpm dev:web` | Web app in development mode |
| `pnpm build:web` / `pnpm start:web` | Production build of the web app / serve that build |
| `pnpm test:web` | Logic and UI component tests (Vitest + Testing Library, ~10s) |
| `pnpm test:e2e` | The real app in Chrome at desktop and phone size (Playwright), on a production build at :3200, signed in as the demo user |
| `pnpm test` | Every package's tests (Turborepo) |
| `pnpm typecheck` / `pnpm lint` | TypeScript and ESLint across the repo |
| `pnpm check` | typecheck + lint + test: run before pushing |

Inside `apps/web` you can also run `pnpm test:watch` to re-run tests as you edit. More on the frontend and its tests: [docs/frontend/README.md](docs/frontend/README.md).

### Backend

<!-- BACKEND COMMANDS: to be filled in with apps/api (pnpm dev:api, setup, migrations, tests). -->

_Coming soon: commands for `apps/api` (Python)._

## License

MIT

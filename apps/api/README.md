# @botdesk/api — coming soon

The BotDesk backend: one API for web, desktop and mobile.

**Planned stack** (see [architecture](../../docs/architecture/high-level.md)):
- Node.js + [Hono](https://hono.dev), typed client via oRPC contract (`packages/contract`, `packages/sdk`)
- PostgreSQL + pgvector, Drizzle ORM + Drizzle Kit migrations
- Better Auth (orgs, teams, roles), envelope-encrypted model keys
- Durable bot runs, approvals and routines (DBOS, in `apps/worker`)
- Plugin-based integrations (Gmail first), mem0 memory, WebSocket realtime

Until this lands, `apps/web` runs on mock data in `apps/web/src/data/mock/`.

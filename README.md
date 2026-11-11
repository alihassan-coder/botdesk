# BotDesk

Open-source (MIT) Grok Bot: your team of always-on AI bots. Any model, self-hostable, approvals built in.

> Early stage: building the web UI on mock data. What we are building: [docs/product/spec.md](docs/product/spec.md). For agents: [AGENTS.md](AGENTS.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Next.js web app (first client) |
| `apps/api` | Node.js API (coming soon) |
| `apps/desktop`, `apps/mobile` | Electron and Expo clients (coming soon) |
| `packages/*` | Shared code: UI, database, core logic, API client (planned) |

## Develop

```bash
pnpm install
pnpm dev
```

## License

MIT

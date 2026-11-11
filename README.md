# BotDesk

Open-source AI assistant for teams, inspired by Grok. Any model, shared memory, and agents you can @mention.

> Early stage: planning and scaffolding. See [docs/](docs/README.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Next.js web app (first client) |
| `apps/api` | Node.js API (planned) |
| `apps/desktop`, `apps/mobile` | Electron and Expo clients (later) |
| `packages/*` | Shared code: UI, database, core logic, API client (planned) |

## Develop

```bash
pnpm install
pnpm dev
```

## License

MIT

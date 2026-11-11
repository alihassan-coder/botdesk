# @botdesk/web

The BotDesk web app: Next.js 16 (App Router), React 19, Tailwind CSS 4, shadcn/ui (Radix, Nova preset, all components).

Currently runs on **mock data** so every screen is clickable before the API exists.

| Path | What |
|---|---|
| `src/data/types.ts` | Domain types (will move to `packages/contract`) |
| `src/data/store.ts` | The only data entry point for screens: `useStore(selector)` + `actions` |
| `src/data/mock/` | Mock fixtures. Delete when `apps/api` is live |
| `src/components/ui/` | shadcn/ui components |

```bash
pnpm dev   # from the repo root, or here
```

Scope and screens: [docs/product/spec.md](../../docs/product/spec.md).

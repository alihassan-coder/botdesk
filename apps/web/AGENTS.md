<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## BotDesk rules for this app

Full guide: [docs/frontend/README.md](../../docs/frontend/README.md). In short:

- **Where code goes.** `src/app/` routes are thin and render one screen from `src/features/<feature>/`. shadcn components live in `src/components/ui/` (add, don't edit). Pure helpers in `src/lib/` with a `*.test.ts` next to them.
- **Data.** Read with the named hooks in `src/data/store.ts` (`useThread`, `useBot`, …) and change with `actions.*`. Never import `src/data/mock/`.
- **Size and names.** One component per file, under ~150 lines. Names from GLOSSARY.md. Comments explain why.
- **Client vs server.** Server components by default. Put `"use client"` only on the entry component of an interactive tree (screens, shell), not on every child.
- **Next 16 + Cache Components.** Dynamic params: `params.then(...)` inside `<Suspense>`. URL hooks (`usePathname`, `useSearchParams`) and anything time-based must sit inside `<Suspense>` or render client-only (`useNow`, `<TimeAgo>`, `<ClockTime>`). Never read `Date.now()` during render.
- **Check before done.** `pnpm typecheck`, `pnpm test`, `pnpm lint`, `pnpm build`, then look at the screen at 390, 1024 and 1440px wide, light and dark.

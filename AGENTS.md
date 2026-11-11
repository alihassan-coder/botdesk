# BotDesk

Open-source (MIT) Grok Bot: a team of always-on AI bots that work in your apps, talk in threads, and ask for approval before risky actions. pnpm + Turborepo monorepo; web first, desktop and mobile later on one API.

## Read before working

- **Product scope, screens, build order, current status** → [docs/product/spec.md](docs/product/spec.md)
- **Domain terms** (Bot, Run, Approval, Routine, Plugin, Security level…) → [GLOSSARY.md](GLOSSARY.md). Use these words exactly in code and UI.
- **Architecture** (API, agent runtime, computers, plugins, data model, security) → [docs/architecture/high-level.md](docs/architecture/high-level.md)
- **Decisions already made** → [docs/adr/](docs/adr/). Treat accepted ADRs as fixed; propose changes as a new ADR.
- **UI reference** (Grok Bot layout and components) → [docs/research/grok-bot-teardown.md](docs/research/grok-bot-teardown.md)

## Rules

- **Mock boundary.** Screens read data only through `apps/web/src/data/store.ts` (hooks + actions) and types in `apps/web/src/data/types.ts`. Only `store.ts` imports `data/mock/`, so the API can replace the mock in one file.
- **Prebuilt first.** Use shadcn/ui components (`apps/web/src/components/ui`, Radix base, Nova preset) and add more with `pnpm dlx shadcn@latest add <name>` before writing custom UI.
- **Licenses.** Dependencies must be MIT-compatible (MIT, Apache-2.0, BSD, ISC). SSPL, Elastic and AGPL need an ADR.
- **No Grok/xAI assets.** Match Grok Bot's flows and layout; use BotDesk's own name, colours and icons.
- **Network is slow** on the owner's machine: batch installs, avoid cloning large repos (read them on GitHub instead).
- `apps/web/AGENTS.md` has Next.js 16 rules: read it before writing Next code.

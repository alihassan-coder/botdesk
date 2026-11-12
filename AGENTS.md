# BotDesk

Open-source (MIT) Grok Bot: a team of always-on AI bots that work in your apps, talk in threads, and ask for approval before risky actions. pnpm + Turborepo monorepo; web first, desktop and mobile later on one API.

## Read before working

- **Product scope, screens, build order, current status** → [docs/product/spec.md](docs/product/spec.md)
- **Domain terms** (Bot, Run, Approval, Routine, Plugin, Security level…) → [GLOSSARY.md](GLOSSARY.md). Use these words exactly in code and UI.
- **Architecture** (API, agent runtime, tools and approvals, plugins, scaling) → [docs/architecture/README.md](docs/architecture/README.md) (reading guide); what the API does today → [docs/backend/README.md](docs/backend/README.md)
- **Decisions already made** → [docs/adr/](docs/adr/). Treat accepted ADRs as fixed; propose changes as a new ADR.
- **UI reference** (Grok Bot layout and components) → [docs/research/grok-bot-teardown.md](docs/research/grok-bot-teardown.md)
- **Brand and visual design** (logo, tokens, avatars; approved before building) → [docs/design/](docs/design/README.md)

## Rules

- **Mock boundary.** Screens read data only through `apps/web/src/data/store.ts` (hooks + actions) and types in `apps/web/src/data/types.ts`. Only `store.ts` imports `data/mock/`, so the API can replace the mock in one file.
- **Prebuilt first.** Use shadcn/ui components (`apps/web/src/components/ui`, Radix base, Nova preset) and add more with `pnpm dlx shadcn@latest add <name>` before writing custom UI.
- **Licenses.** Dependencies must be MIT-compatible (MIT, Apache-2.0, BSD, ISC). SSPL, Elastic and AGPL need an ADR.
- **No Grok/xAI assets.** Match Grok Bot's flows and layout; use BotDesk's own name, colours and icons.
- **Network is slow** on the owner's machine: batch installs, avoid cloning large repos (read them on GitHub instead).
- `apps/web/AGENTS.md` has Next.js 16 rules: read it before writing Next code.
- `apps/api/AGENTS.md` has the Python backend rules (layers, `/api/v1`, migrations): read it before touching `apps/api`. Backend stack: [ADR 0003](docs/adr/0003-python-backend.md).

## Skills

Load the matching skill before starting the task:

- **Screens and components:** `frontend-design`, then `modern-web-guidance` for HTML/CSS/browser APIs, `vercel-react-best-practices` for React code; `emil-design-eng` for motion and polish. Check the result in a real browser with the Playwright tools (screenshot, then critique), and review with `web-design-guidelines`.
- **Library APIs** (Next 16, Tailwind 4, shadcn, FastAPI, SQLAlchemy, LangGraph, LangChain, mem0): look them up with Context7 before writing code; training data is older than these versions.
- **New feature end to end:** `/feature-dev`; for design exploration, `playground`.
- **System design:** `mattpocock-skills:to-spec`, then `to-tickets`; architecture health with `mattpocock-skills:improve-codebase-architecture`. Record decisions as ADRs in `docs/adr/`.
- **GLOSSARY.md, ADRs, naming:** `mattpocock-skills:domain-modeling`.
- **Module boundaries** (store/mock seam, `packages/*`): `mattpocock-skills:codebase-design`.
- **Auth, orgs, roles** (`apps/api`): own email/password auth per ADR 0003 (Better Auth is no longer used).
- **Bugs:** `mattpocock-skills:diagnosing-bugs`. **Logic with tests:** `mattpocock-skills:tdd`. **Reviews:** `mattpocock-skills:code-review`.

Adding skills: Claude Code plugins go in `enabledPlugins` in [.claude/settings.json](.claude/settings.json); standalone skills go in with `npx skills add <owner/repo>`, which writes `.claude/skills/` and `skills-lock.json`.

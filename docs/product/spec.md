# BotDesk v1 — What we're building

> The product definition. Terms are defined in [GLOSSARY.md](../../GLOSSARY.md); the why is in [vision.md](vision.md); the how is in [architecture/](../architecture/README.md) (start with the reading guide).

## One line

An open-source (MIT), self-hostable **Grok Bot**: your team of always-on AI bots that work in your apps, talk in threads with you and each other, and ask for approval before risky actions.

## v1 scope

v1 = **Grok Bot feature parity on the web**, with one integration.

| Area | v1 must do |
|---|---|
| Bots | Create from scratch or a template; edit name, handle, role, instructions, model, security level, budget, computer mode |
| Threads | DM with a bot; group threads with members + bots; `@mentions`; handoffs between bots; reasoning shown; message cards (see below) |
| Runs | Background, durable, cancellable; live status per bot (`working`, `waiting-approval`, `sleeping`, `error`) |
| Approvals | Inline approval card in the thread **and** an approvals inbox; approve / deny / edit-then-approve |
| Computer | Live view of a bot's computer; take over to log in |
| Routines | Follow-along recording, create from chat, schedule, enable/disable, run history |
| Integrations | **Gmail only**, built as a plugin; custom remote MCP server; catalog shows future connectors as "coming soon" |
| Memory | Per member and per bot; list, edit, delete |
| Models | All major providers + custom OpenAI-compatible; member keys and org keys |
| Teams | Orgs, members, roles, invitations |
| Usage | Cost per bot and per day; budgets that pause a bot |
| Marketplace | Browse and hire bot templates |
| Customization | Theme (light/dark/system), accent, radius, font, density, chat style, sidebar width (saved per member) |

**Later:** desktop (Electron), mobile (Expo), more integrations, advanced approval policies (rules, spend limits, multiple approvers), local "bring your own computer".

## Message cards

A bot message is a list of parts. Each part renders as a card in the thread:
`text` · `reasoning` · `work-log` (checklist) · `computer-task` (status, take over) · `approval` · `question` (options) · `routine-created` · `file` · `handoff`.

Source of truth for shapes: `apps/web/src/data/types.ts`.

## Screens

Layout: bot sidebar (left) · thread (centre) · bot details pane (right, collapsible). Reference: [Grok Bot teardown](../research/grok-bot-teardown.md).

1. Onboarding (create org, hire first bot, connect Gmail)
2. Thread view (DM and group) with composer, `@mention` picker, cards
3. Bot details pane: profile, routines, memory, computer preview
4. Computer full view with take over and "teach a task" recording
5. Approvals inbox
6. Routines list and editor
7. Connect apps (catalog + connections)
8. Marketplace
9. Settings: profile, appearance (customization), models & keys, security levels, members & roles, usage & budgets, memory
10. Command palette (`⌘K`)

## Build order

1. **UI first, on mock data** (current phase). Every screen clickable against `apps/web/src/data/mock/`.
2. **API** (`apps/api`, with the worker inside it, [ADR 0005](../adr/0005-job-queue-and-scaling.md)): auth, orgs, bots, threads, runs, approvals; swap the mock source for the API.
3. **Gmail plugin**, memory, computers, routines.
4. Desktop, then mobile.

## Status (2026-11-12)

History: [PROGRESS.md](../PROGRESS.md).

**Done**

- Docs: this spec, vision, ADRs 0001–0006, architecture, research, glossary.
- API (`apps/api`): sign-in, organizations, invitations, bots, threads and messages. Bots don't reply yet.
- Logo: the botdesk wordmark with an online light on the o, with all files in [docs/design/logo](../design/logo/README.md).
- Web frontend on mock data (`apps/web`, Next.js 16, React 19, Tailwind 4, shadcn/ui). Plan and rules: [docs/frontend](../frontend/README.md).
  - App shell: sidebar that collapses to an icon rail, workspace header with org switcher, light/dark, phone/tablet/desktop layouts.
  - DM and group threads with all 9 message cards, composer with streaming mock replies, inline approval card (Approve / Deny / Edit), details pane.
  - Pages: create bot, marketplace, approvals inbox, routines, create routine, connect apps, ⌘K command palette.
  - Settings (opens on Profile): profile, organization, appearance (theme, accent presets or a custom colour), models & keys, security matrix, members, usage & budgets, memory.
  - Mock accounts: sign in, sign up, forgot password, sign out. An auth gate sends signed-out people to sign in.
  - Tests: Vitest logic and UI component tests; Playwright end-to-end tests at desktop and phone size.

**In progress**

- Backend changes to Python (ADR 0003, `docs/adr/0003-python-backend.md`): FastAPI, SQLAlchemy + Alembic, LangGraph for durable runs and approvals, mem0 for memory, own email/password auth, Neon Postgres for dev.
- Wiring the web app to the API in `store.ts` (bots are done).
- Next backend step: bots reply (job queue, worker, streaming). Build order: [agents-and-plugins.md §14](../architecture/agents-and-plugins.md#14-build-order-each-step-small-tested-and-usable).

**Next**

- Web: group chats with an @mention picker, the computer view (live screen, take over) and routine recording.
- Design: brand tokens (colour, type, radius, motion), then the bot avatar system.

**Open:** the remaining owner questions in [high-level.md §16](../architecture/high-level.md#16-questions-for-the-owner) (computers, approvers, pricing, retention, marketplace).

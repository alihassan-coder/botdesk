# Roadmap

One checklist for the whole project: what's done, what's being built, and what's next.

- **Ticked boxes** are finished, tested and on `main`.
- **Unticked boxes** are still to do, top to bottom, roughly in that order.
- Dated details of the finished work are in [PROGRESS.md](PROGRESS.md).
- The reasons behind each decision are in the [ADRs](adr/).

When you finish something, tick it here in the same pull request.

## Done

### 1. Product and design
- [x] Product spec, vision and research ([product/spec.md](product/spec.md), [research/](research/))
- [x] Glossary of terms used in code and UI ([GLOSSARY.md](../GLOSSARY.md))
- [x] Logo: the botdesk wordmark with an online light ([design/logo](design/logo/README.md))
- [x] Architecture design, diagrams and ADRs 0001–0007 ([architecture/](architecture/README.md))
- [x] Open-source files: MIT license, contributing guide, security policy, code of conduct, issue and pull request templates, CI

### 2. Web app on demo data (`apps/web`)
- [x] App shell: sidebar that collapses to an icon rail (the logo expands it), org switcher, light and dark, phone/tablet/desktop
- [x] Chats: direct and group, all 9 message cards, streaming replies, inline approval card, details pane
- [x] Pages: create bot, marketplace, approvals inbox, routines, create routine, connect apps, settings (profile, organization, appearance, models and keys, security, members, usage and budgets, memory)
- [x] ⌘K command palette and keyboard shortcuts
- [x] Guest mode: "Explore the demo" without an account
- [x] Unit tests (vitest) and browser tests (Playwright, desktop and phone)
- [x] README screenshots

### 3. API foundations (`apps/api`)
- [x] Python + FastAPI + SQLAlchemy + Alembic, layered routes → controllers → services → models ([ADR 0003](adr/0003-python-backend.md))
- [x] Postgres on Neon, a separate test database, and Postgres in CI
- [x] Accounts: sign up, sign in, sign out, profile, change password (Argon2, httpOnly session cookie)
- [x] Email through Brevo: password reset link (single use, 1 hour) and invitation emails
- [x] Organizations, members, roles (only one owner can't leave), invitations
- [x] Bots: create, edit, remove
- [x] Chats: direct and group, message history with paging, sending
- [x] Speed: no N+1 queries, one query per auth and org check, indexes

### 4. Bots that reply (build step 1)
- [x] Runs: one reply = one run, in the API process for now ([ADR 0007](adr/0007-runs-in-the-api-process-for-now.md))
- [x] LangGraph run graph with a Postgres checkpointer; a stand-in model when there's no AI key
- [x] Live updates over SSE, resuming after a dropped connection
- [x] Limits: one run per chat, per-bot cap, step and time limits, Stop
- [x] Memory with mem0 (off until `MEMORY_ENABLED` and an OpenAI key)
- [x] Web: chat on the API with live streamed replies and Stop

### 5. Tools and approvals (build step 2)
- [x] Risk policy: 3 security levels × 7 risk classes, strict taint ([ADR 0004](adr/0004-agent-runtime-and-safety.md))
- [x] Tool pipeline: validate → classify → decide → (ask) → run → record; never runs twice
- [x] Approvals that pause a run and resume it on Approve / Edit / Deny; only one decision wins
- [x] Built-in demo plugin (time, search, notes, draft and "send" email, a pretend inbox)
- [x] Web: approval cards in the chat and on the Approvals page, live from the event stream
- [x] Web: Approve, Edit (with the tool's fields) and Deny against the API
- [x] Web: policy table with all 7 risk classes (`write-external`) and the `edited` status
- [x] Web: waiting and "needs attention" states for a run

### Developer experience
- [x] `pnpm dev` (web + API), `pnpm dev:web`, `pnpm dev:api`, reload on save, busy-port check
- [x] `pnpm check` runs type checks, lint and every test

## Next

### Real AI
- [ ] Set `SECRET_KEY` in `apps/api/.env`, then add a real key in Settings → Models & keys (owner, no code)
- [x] Models and keys in settings, saved per organization: Anthropic, OpenAI, Gemini, OpenRouter, Groq and custom OpenAI-compatible servers; keys checked live and encrypted; live model lists; a searchable model picker for bots

### Plugins (step 3)
- [ ] Plugin SDK as its own package, and a uv workspace ([ADR 0006](adr/0006-repo-structure-plugins-and-project.md))
- [ ] Move the demo plugin onto the SDK

### Gmail (step 5)
- [ ] Connect with your own Google client; read, label, draft, and send only after approval

### Memory, routines, handoffs (steps 6–7)
- [ ] Memory screen: see and delete what a bot remembers
- [ ] Routines: bots work on a schedule
- [ ] Handoffs: one bot passes work to another

### MCP (step 8)
- [ ] Connect a remote MCP server; its tools become bot tools

### Hosting
- [ ] Job queue and a separate worker process ([ADR 0005](adr/0005-job-queue-and-scaling.md)); approvals expire on a timer
- [ ] `deploy/docker-compose.yml` for one-command self-hosting
- [ ] Row-level security in Postgres before a hosted launch
- [ ] Rate limits (forgot password, sign-in) and your own email domain in Brevo

### Later
- [ ] Usage and budgets on the API
- [ ] Unread counts in the chat list
- [ ] Bot computers (live screen, take over) and routine recording
- [ ] Desktop app, then mobile

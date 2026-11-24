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
- [x] Architecture design, diagrams and ADRs 0001–0008 ([architecture/](architecture/README.md))
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
- [x] The org's default security level for new bots (Settings → Security)
- [x] The org's security ceiling ("Highest level for every bot", Settings → Security): no bot set or run above it, routines, the Gmail trigger and handoff children included; lowering it reaches runs already going at their next tool call
- [x] Create another organization from the org switcher (you're its owner)
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
- [x] Tool lines saved with the reply, so a reload shows "Used Send email · done"
- [x] A chat opened later shows its runs' live state (`GET /threads/{id}/runs?active=true`, then the stream after `lastEventId`)
- [x] An edited approval's summary follows the edited arguments
- [x] Approval cards: focus moves with Edit, Cancel and a decision; decisions announced; edits kept on a 409 that isn't a decision

### Developer experience
- [x] `pnpm dev` (web + API), `pnpm dev:web`, `pnpm dev:api`, reload on save, busy-port check
- [x] `pnpm check` runs type checks, lint and every test

## Next

### Real AI
- [ ] Set `SECRET_KEY` in `apps/api/.env`, then add a real key in Settings → Models & keys (owner, no code)
- [x] Models and keys in settings, saved per organization: Anthropic, OpenAI, Gemini, OpenRouter, Groq and custom OpenAI-compatible servers; keys checked live and encrypted; live model lists; a searchable model picker for bots
- [x] Member keys ("My keys"): a member's own key per built-in provider, used before the org's for the runs they're the requester of, seen by nobody else, never used for anyone else's run

### Plugins (step 3)
- [x] Plugin SDK as its own package, and a uv workspace ([ADR 0006](adr/0006-repo-structure-plugins-and-project.md))
- [x] Move the demo plugin onto the SDK
- [x] Plugins found through `botdesk.plugins` entry points, loaded only from the `PLUGINS` allowlist, checked at load (a broken one is skipped)
- [x] `GET /orgs/{id}/plugins` for the "Connect apps" page
- [x] Web: Connect apps shows the server's plugins as built in; the app catalogue is "coming soon" until connections exist
- [x] `plugins/_template`, a generated `manifest.json` checked in CI, import rules in CI ([author guide](plugins/README.md))
- [ ] Release the SDK to PyPI with release-please (separate `sdk-v*` version): config and `release.yml` are ready; waiting on the owner's one-time PyPI and GitHub setup ([steps](../packages/plugin-sdk/README.md#releases))

### Connections (before Gmail and MCP; [build plan](architecture/connections-gmail-mcp.md), [ADR 0010](adr/0010-connections-and-credentials.md))
- [x] 5.1 Connection platform (backend): `connections` table, credential vault, API-key connections (`/orgs/{id}/connections`), `ctx.http` (declared hosts only, no redirects, no private addresses, size and time caps, credential added by BotDesk), SDK manifest v2, demo `call_api` tool
- [x] 5.2 Bindings: each bot's Tools tab, the run's requester, member connections only in their member's DMs; changing a shared account needs the right to it
- [x] 5.3 OAuth connections and Connect apps on the API (token refresh with a lease, reconnect, revoke); `plugins/gmail` connects a Google account (no tools yet)

### Gmail (step 5)
- [x] Connect with your own Google client; read, label, draft, and send only after approval
  - [x] 6.1 Read: `gmail.search`, `gmail.read_thread`, `gmail.list_labels` (plain text, capped, header filter, `<email>` blocks; mail results taint the run, the label list doesn't)
  - [x] 6.2 Write: `gmail.add_labels`, `remove_labels`, `archive`, `create_draft` (write-external), `send` (external-send), `trash` (destructive); plain-text mail, replies threaded, header injection refused, approval cards show recipients, subject and body
  - [x] 6.3 "React to new email" (bot Tools tab): history polling every minute on the job queue; each new email posts in the subscriber's DM and starts a tainted run; expired history → one notice
  - [x] 6.4 Owner's guide ([Google setup and what bots can do](self-hosting/google-oauth.md), [manual test](testing/gmail.md))
  - [x] 6.5 Extras: easier-to-read HTML mail (numbered lists, table rows, quotes; quoted earlier mail at the end of a reply left out), `gmail.read_attachment` (text, CSV, JSON; not PDFs), Markdown mail (plain + HTML we generate), `gmail.list_drafts` and `gmail.send_draft` (card shows the draft's recipients and subject, checked before sending)

### Multi-bot (from the 2026-11-14 test)
- [x] Speaker names in group history, so a bot knows who said what
- [x] Bot-to-bot @mentions start runs, with a hop limit (ADR 0009); guests in DMs
- [x] Handoffs and Chief delegation: a handoff tool and tasks; the parent waits and gets the results back ([ADR 0014](adr/0014-handoffs-and-tasks.md), [contract and build slices](architecture/handoffs-contract.md))
- [x] A default responder when no bot is mentioned in a group: the group's lead

### Memory and routines (steps 6–7)
- [x] Memory screen: see, search, correct and forget what a bot remembers; a memory switch per bot
- [x] Routines: bots work on a schedule (cron + time zone, Run now, recent runs; each run in the creator's DM, at the strictest of bot and routine level)

### MCP (step 8)
- [x] Connect a remote MCP server; its tools become bot tools (slice 7.2: header-key auth, tool snapshot pinned by hash, every tool asks and taints)
- [x] MCP OAuth sign-in (7.3); review tools and their risk, drift diff and badge (7.4) ([ADR 0016](adr/0016-mcp-sign-in-and-review-as-built.md), proposed; [manual test](testing/mcp.md); not yet tried against a real OAuth MCP server)
- [ ] Member- and bot-owned MCP sign-ins (each member's own account, only in their DMs); v1 has the organization's sign-in only
- [ ] MCP drift noticed without a call or a Refresh (a scheduled re-list)

### Self-hosting
- [x] Job queue and a separate worker process ([ADR 0005](adr/0005-job-queue-and-scaling.md), [ADR 0013](adr/0013-the-job-queue-lands.md)); approvals expire on a timer
- [x] `deploy/docker-compose.yml` for one-command self-hosting ([docs/self-hosting](self-hosting/README.md), checked by the CI smoke test)
- [x] Sign-ups: open, invite-only or closed (`SIGNUP_MODE`); signing up from an invite link joins that organization
- [ ] Row-level security in Postgres, before one install serves teams that don't trust each other
- [x] Rate limits on sign-in, sign-up, forgot password and reset password (in-process; per address, and per email for sign-in and forgot password)
- [ ] Your own email domain in Brevo

### Onboarding
- [x] First-time setup at `/welcome` for the owner of a new organization (no bots yet): name it, add an AI key, hire Chief (or another bot), connect Gmail; every step skippable, Finish opens the first bot's DM with its welcome; never shown to invited members, the demo, or again after finishing or skipping

### Later
- [x] Usage and budgets on the API
- [x] Model prices (`apps/api/src/services/pricing.py`) are effective-dated, so they switch by themselves: on **2026-12-01** Gemini 4 Carbon and Argon double, and gemini-2.5-pro / 2.5-flash switch models (no price from then); on **2027-01-01** gemini-3.8-flash doubles
- [x] Unread counts in the chat list (per person, marked read when you look at the chat)
- [x] Manage a group: rename it, add and remove people and bots (its creator, owners and admins)
- [x] Marketplace templates from the API: one catalogue (`apps/api/src/templates/catalogue.json`, Chief included), hired by the API with the template's instructions, plugins and the stricter of its level and the org's default
- [x] Bots' files: Local or your own S3-compatible bucket, `botdesk/<bot>/` folders, Settings → Computers, the Files tools ([ADR 0017](adr/0017-bot-browsers-and-file-storage.md) step 1)
- [x] Bots' Local browser: open, read, follow, search; click, type and choose with approval; screenshots into Files (ADR 0017 step 2)
- [x] Take over a bot's browser to sign in (API; ADR 0017 step 3)
- [x] Take over in the web app (live view in the Computer tab)
- [x] Cloud browser providers: Steel, Browserbase, Kernel (API; ADR 0017 step 4)
- [x] Cloudinary storage (API; ADR 0017 step 5)
- [x] Browser provider card and Cloudinary in Settings → Computers
- [ ] A browser in the Docker image (or Docker users pick a cloud browser); files attached in chat
- [ ] The full bot computer (a whole desktop) and routine recording
- [ ] Desktop app, then mobile

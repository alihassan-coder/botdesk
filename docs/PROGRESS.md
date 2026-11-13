# Progress

A short history of BotDesk, newest first. For one checklist of what is done and what is next, see [ROADMAP.md](ROADMAP.md).

## 2026-11-13: Models & keys, saved per organization

Settings → Models & keys is real. An owner or admin adds an API key for a model provider; BotDesk checks it with a live call, saves it encrypted, and lists that provider's models live; everyone picks a model per bot from that list; and the bot's runs use the org's key. Details: [backend guide](backend/README.md#models-and-keys).

- **Providers:** Anthropic (native), OpenAI, Google Gemini (through Google's OpenAI-compatible endpoint), OpenRouter (with names, context sizes and prices), Groq, and custom OpenAI-compatible servers such as Ollama, LM Studio or vLLM (name, base URL, optional key). One small adapter each, behind one interface.
- **API:** `GET/PUT/DELETE /orgs/{id}/providers…`, `POST …/providers/{id}/test`, `GET /orgs/{id}/models` (merged across providers, cached 10 minutes, `?refresh=true`, a provider that's down is reported without failing the rest). New table `provider_credentials` (migration applied to the dev database); `bots.model_id` grew to 200 characters for ids like `custom-<id>:llama3.2:latest`.
- **Keys:** Fernet-encrypted with a new `SECRET_KEY` (production won't start without it), never returned or logged (only the last 4 characters), provider error messages scrubbed. Owners and admins change keys; members only look.
- **Runs:** the org's key, else the server's env key (`ANTHROPIC_API_KEY` … `GROQ_API_KEY`, kept for self-hosting), else the stand-in model. Errors from the provider become actionable messages ("This model can't use tools…", "refused the API key…").
- **Safety:** custom server addresses go through an SSRF guard: http/https only, and in production no private, loopback or link-local addresses unless `ALLOW_PRIVATE_MODEL_URLS=true`.
- **Web:** provider cards, an add-key dialog that says "Checking…" and then the API's verdict, a searchable live model list, and a searchable, grouped model picker in create bot and edit bot. Model ids are `provider:model` everywhere now, so the mock's translation table is gone.

## 2026-11-13: approvals on the web (finishes build step 2)

In API mode a bot's risky action now shows up in the chat as an approval card, live from the chat's event stream, and on the Approvals page.

- **The card** shows the title and summary, the risk in plain words, why the bot asked (from the policy's trace), a warning when the run read outside content first, the exact action and when it expires. **Approve**, **Deny**, or **Edit**: a form built from the tool's argument schema (text, long text, numbers, yes/no, choices), filled in with what the bot asked for, checked before sending and showing the API's own field errors. After a decision the card says "Approved by you", "Edited and approved by Sara", "Denied by…" or "Expired", live. If someone decided first, the card refreshes to what happened and a toast says so.
- **Run states in the chat:** tools the bot used show as a compact line ("Used Send email · done"); while it waits the bot's status says "Waiting for approval"; after a decision it's thinking again; a run that needs attention gets a notice with the error and a Stop button. A chat that opens while a run waits still shows the card. How events change the chat stays in the pure, tested `api/run-events.ts`.
- **Approvals page** reads the API's list, with Waiting and Decided tabs and a filter by bot. The sidebar's count is checked every 20 seconds while the tab is visible (no org-wide stream yet), and at once when a chat hears of a request or decision.
- **The web policy table** now has ADR 0004's 7 risk classes (with `write-external`, reversible changes in other apps like drafts and labels), and the security levels describe it: *Read only* reads and keeps internal notes but never drafts outside; *Ask before acting* asks before drafting, sending, spending, deleting or using a login; *Autonomous* drafts and sends on its own. Settings → Security explains taint.
- **Demo:** the mock approvals carry arguments and a schema, so Edit works the same way without an API; one shows the outside-content warning.

Clicked through against a local API with the stand-in model: approve, edit (with a bad address caught in the form), deny, a waiting card surviving a reload, the Approvals page, and a decision made elsewhere (409).

## 2026-11-12: chats on the API, and the web checked end to end

In API mode the web app now talks to bots for real. The chat list, each bot's DM, message history (50 at a time, with "Show earlier messages"), sending, and replies streamed live from the chat's event stream: typing dots, words as they arrive, the saved reply, an inline error when a reply fails, and a Stop button while a bot replies. The "chat coming soon" placeholder is gone. Settings → Profile saves your name and @handle on the API and gained a Password section.

**Group chats (web).** "New group" in the sidebar's New menu opens a dialog: name the group, tick bots and teammates, Create. On the API it calls `POST /threads/groups`, in the demo it's created in the mock; either way the new chat opens, and the bots you @mention reply. **Dev console fixed:** every page under the app shell logged Next's "Could not validate that a segment in your UI has instant navigation" because the auth gate left the page out until the browser knew your session, so Next's prerender never rendered the route's segments. The gate now renders the page hidden and inert until you're signed in.

Every wired flow was clicked through in a browser against a local API: sign up, sign in, sign out, session restore, forgot password, org switcher and rename, members (role change, removal), invites (create, revoke, accept), bots (create, edit, remove). Fixed on the way: profile edits were only saved in the browser; handles allowed `_`, which the API rejects; times from a SQLite API showed 5 hours off; a renamed bot's DM kept its old name after a reload; a reload straight into a chat flashed "This chat doesn't exist".

## 2026-11-12: tools, the policy and approvals (build step 2, API)

Bots can now use tools, and risky ones wait for a person ([ADR 0004](adr/0004-agent-runtime-and-safety.md); details in the [backend guide](backend/README.md#tools-and-approvals)).

- **One pipeline for every tool call:** validate the arguments, work out the risk class, ask the policy (3 levels × 7 risk classes, a pure module with a table test), then run, ask or refuse. One call at a time.
- **Approvals pause the run** with LangGraph `interrupt()`; the checkpoint waits in Postgres. Approve, edit-and-approve or deny resumes it with `Command(resume=...)`. Deciding is one guarded `UPDATE`, so a double click can't approve twice. New table `approvals`, routes under `/orgs/{id}/approvals`, live events `approval_requested`, `approval_decided`, `run_resumed`, `tool_started`, `tool_finished`, `run_needs_attention`.
- **Nothing runs twice:** every call is a `tool_executions` row keyed by run and tool call. A call left half done after a restart puts the run in `needs_attention` instead of retrying.
- **Strict taint:** once a tool returns outside text, every action above `write-internal` asks, even for Autonomous bots, and the run saves no memories.
- **A demo plugin** (`src/plugins/demo`) with fake tools (clock, knowledge base, notes, a fake outbox and an inbox with a prompt injection), registered through a small manifest + registry shaped like the coming plugin SDK. Without an API key, `/tool demo.send_email to=… subject=…` makes the stand-in model call a tool, so an approval can be tried end to end.

## 2026-11-12: real email through Brevo

The API now sends email through Brevo's transactional API, in the background so requests never wait on it ([backend guide → Email](backend/README.md#email)). Without a key, emails are written to the log instead.

- **Password reset, the standard way:** `forgot-password` emails a single-use link (hashed token, 60 minutes) and always gives the same answer; the new `reset-password` sets the password and signs out every device. New table `password_reset_tokens`.
- **Invitations are emailed** to the invitee, with who invited them and the organization's name. The API still returns the link too.
- **Web:** a `/reset-password` page for the emailed link; it sends you to sign in with a toast.

A first real reset email to the owner's address was accepted by Brevo.

## 2026-11-12: new logo, the name with an online light

After eleven rounds the owner chose a **wordmark**: `botdesk` in Outfit ExtraBold, where the o carries an online light, the dot that shows a teammate is available. It replaces the v7 bd monogram everywhere: the web app (sidebar, sign-in, loader, favicon and touch icon), the README and the docs. All files are generated by one script, and the old rounds were deleted. Files and rules: [design/logo](design/logo/README.md).
The collapsed sidebar was also fixed: every icon now sits on one centre line.

## 2026-11-12

**Architecture review.** A critical review of the bots-and-plugins design ([architecture/review-2026-11-12.md](architecture/review-2026-11-12.md)): 16 ranked findings and 13 decisions for the owner, all accepted the same day as ADRs 0004–0006, with a [reading guide](architecture/README.md). The design doc gained a Scaling section (job queue, event bus, connection pools, tenancy, observability) and safer run, approval and plugin rules; a new [repo-structure.md](architecture/repo-structure.md) lays out the monorepo for open source. Docs only, no code changed.

**Backend moves to Python.** The owner changed the backend plan from Node (Hono, Drizzle, Better Auth) to Python:

- uv for packages, FastAPI on uvicorn for the API.
- SQLAlchemy 2 (async) and Alembic for the database.
- LangChain and LangGraph for bots. LangGraph's Postgres checkpointer makes runs durable; approvals pause a run and resume it.
- mem0 for memory.
- Our own small email/password auth: argon2 password hashes, opaque session tokens in httpOnly cookies or a Bearer header.
- Hosted Neon Postgres for development.

The decision is recorded in ADR 0003 ([adr/0003-python-backend.md](adr/0003-python-backend.md)). The first backend slice is auth, orgs, bots, threads and messages, and streaming bot replies.

**Accounts and polish (web).** Mock sign in, sign up, forgot password and sign out. An auth gate sends signed-out people to `/sign-in` and back again afterwards. Also: create a routine (`/routines/new`), manage the organization (`/settings/organization`), Settings opens on Profile with a section nav that stays in view, a sidebar that collapses to an icon rail, an org switcher in the sidebar header, and a custom accent colour. End-to-end tests now start signed in as the demo user.

**Every app page (web).** Create bot with a live preview, marketplace, approvals inbox, routines, connect apps, all settings sections, the ⌘K command palette and a new workspace header with the logo tile.

**Tests.** Vitest and Testing Library for logic and UI components; Playwright for the whole app in Chrome at desktop and phone size, on a production build. Writing the tests found three bugs (an approval field losing focus while typing, the approvals count missing from a link's name, and old mock replies leaking into fresh data). Root commands `pnpm dev:web`, `test:web`, `test:e2e` and `check` were added.

**Slice 1 (web).** The app shell (sidebar, phone/tablet/desktop layouts, light and dark), DM and group threads, all 9 message cards, a composer with streaming mock replies, the inline approval card (Approve / Deny / Edit) and the bot details pane. Everything runs on mock data behind one store, so the API can replace it in one file.

**Logo v7 approved.** After six rounds, the owner chose v7, "the always-on bd": the b and d of botdesk share one loop shaped like an infinity sign, drawn as one even monoline. Earlier rounds taught us what to avoid: plain flat shapes and glossy icons felt cheap, a woven gap read as a cut, pointed bowls read as sly eyes, and calligraphy did not fit. Files and rules: [design/logo](design/logo/README.md).

**Tooling.** Project skills and Claude Code plugins enabled for design, React, testing and docs work.

## 2026-11-11

**Web app scaffold.** `apps/web` on Next.js 16, React 19 and Tailwind 4, with all shadcn/ui components and a mock data layer.

**Planning docs.** The monorepo root, the product vision, the v1 spec, AGENTS.md, the glossary, the architecture proposal, a screen-by-screen teardown of Grok Bot, competitor research, and ADRs 0001 (product scope and deployment) and 0002 (Grok Bot parity, plugin integrations, security levels, approvals).

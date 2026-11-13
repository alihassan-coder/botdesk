# Progress

A short history of BotDesk, newest first. For one checklist of what is done and what is next, see [ROADMAP.md](ROADMAP.md).

## 2026-11-13: formatted bot replies

- **Markdown:** bot replies show bold, lists, headings, tables, task lists, links (new tab) and code blocks with syntax colours and a copy button, with react-markdown and remark-gfm (MIT). Raw HTML is never rendered and images show as links. People's messages stay as typed.
- **Copy message:** under each finished message, with its time, on hover or keyboard focus (always on touch screens).
- **@mentions:** an @ inside a word, like `sara@acme.dev`, is no longer a mention, in highlighting or in who a message pulls in.
- **Chat list:** previews show the words without markdown marks.

## 2026-11-13: free and open source, no plans

BotDesk is MIT and free forever: people bring their own AI keys and pay their provider directly ([ADR 0008](adr/0008-free-and-open-source.md)). Organizations no longer have a `plan` (migration `9f2d6c1b7a40` drops the column, `OrgOut` drops the field), and the sidebar and organization settings no longer show "Free plan" or "Team plan".

## 2026-11-13: usage and budgets, fixes from a review

- **Stopped and failed calls are billed:** usage is recorded in a `finally`, as its own task that Stop and shutdown can't cancel. Without the provider's numbers, tokens are estimated from characters and the row is marked `estimated` (new column).
- **Budgets overshoot less:** each model call gets a `max_tokens` cap from what's left of the budget. Budgets are documented as a soft limit (about calls at once × one call's cost).
- **OpenRouter prices:** one fetch per org at a time, a failure isn't retried for 60 s, and saving a bot with an OpenRouter model fetches the list ahead of its first run.
- **Bot budgets are for owners and admins:** members get 403 changing one (they may hire a bot with up to $50); the Edit dialog shows it read-only for them.

## 2026-11-13: memory privacy and run-event fixes from a review

An independent review of the memory screen and the run-event lock found seven problems; all are fixed, with tests. Details: [backend guide](backend/README.md#memory).

- **Privacy (important):** the member's scope was only in mem0 metadata, which mem0 ignores when it builds its extraction context, so other members' DM messages and memories could reach the model and come back as a shared memory. The scope is now mem0's `run_id` (`shared` or the member's id) on every call; a DM's recall searches shared and the member's and merges. Migration `7d2c4e9a1b3f` moves old rows' `member` tag into `run_id`. Tested against real mem0 with a spy model.
- **Newest first, really (important):** mem0's pgvector list has no order, so with more memories than the limit the screen showed an arbitrary subset. It now reads the newest straight from mem0's table with `ORDER BY`.
- **A memory forgotten by someone else mid-request** is 404, not 503.
- **Web:** forgetting, correcting or forgetting everything outdates searches still in flight, so a late answer can't bring a forgotten memory back; a list still loading is loaded again.
- **Run-event lock:** the flush hook returns before touching the connection when there are no new events, and a transaction that would take chat locks out of order now fails loudly instead of risking a deadlock.
- **`replayFrom` counts only queued and running runs.** A paused run no longer pins every page load's replay to its start; it's rebuilt from the active-runs list and its approval card.

## 2026-11-13: usage and budgets, for real

Every model call is now counted and priced, and budgets stop a bot before it overspends. Details: [backend guide](backend/README.md#usage-and-budgets).

- **Usage records:** one `usage_records` row per model call (tokens from LangChain's `usage_metadata`, streaming included; the built-in OpenAI-compatible providers now send `stream_options.include_usage`), with the provider, model and cost in US dollars. Prices: OpenRouter's from its model list, a small dated price table in `services/pricing.py` for Anthropic, OpenAI, Gemini and Groq, and none for custom servers. A model without a price records tokens and "price unknown", never a guess.
- **Budgets:** checked before each model call against this calendar month (UTC), with one indexed SUM: the bot's `monthlyBudgetUsd` (0 = no limit) and a new optional organization budget (owners and admins, `PATCH /orgs/{id}`). Over budget, the run fails with a clear message and `run_failed` carries `code: "budget"`.
- **Routes:** `GET /orgs/{id}/usage?days=14` (daily totals, month to date, org budget, every bot's spend) and `GET /orgs/{id}/bots/{botId}/usage`, for any member.
- **Web:** Settings → Usage & budgets, the bot details' budget bar and the org budget are on the API (demo and guest mode keep the mock); bots near their limit show amber, past it red; a reply stopped by a budget shows a notice with Edit and a link to Usage & budgets.
- **Plugin hardening (from a review):** a plugin that returns a non-object or something JSON can't hold (a `datetime`, a `UUID`) now fails that tool call cleanly (`failed`, with a message) instead of leaving the row `started` and crashing the run.

## 2026-11-13: the memory screen

See, search, correct and forget what a bot remembers, on the API and the web. Details: [backend guide](backend/README.md#memory).

- **API:** `GET /orgs/{id}/memory/status`, and under `/orgs/{id}/bots/{botId}/memories`: list or search (`?q=`), `PATCH` to correct, `DELETE` one, `DELETE` all. Built on mem0's `get_all`, `search`, `get`, `update`, `delete` and `delete_all`, always with the org and bot filters set by the API.
- **Privacy:** you see a bot's shared memories and your own DM ones, never another member's, owners included. Members change only their own; owners and admins change any and can make a bot forget everything. A memory id from another org or bot is 404. With memory off, the routes answer empty lists and a status with the reason.
- **Per-bot switch:** bots have `memory_enabled` (on by default; migration `3e0c1566143b`). Off, the bot neither recalls nor saves memories. It's in Edit bot.
- **Web:** Settings → Memory (pick a bot) and the bot's Memory tab share one list with search, inline correct, forget, and "Forget everything" behind a confirm.
- **Follow-up:** memory still needs `OPENAI_API_KEY` on the server; using the org's own OpenAI key from Models & keys needs one mem0 client per key and is left for later.

## 2026-11-13: live run state on open, race fixes from a review

An independent review of "a chat opened later sees what's going on" found six problems; all are fixed, with tests.

- **A run that starts while a chat loads keeps going** (Stop shows, the bot is busy). Each run remembers the newest event id the chat applied; the active-runs list ends only runs it doesn't list that weren't heard on the stream after its `lastEventId`. A run the stream already knows is left to the stream.
- **Stand-in replies survive the page load.** A reply still being written (with its cards and tool lines) is kept beside the loaded page whatever its time; other messages are kept if they're newer than the page's oldest one.
- **A reply opened midway shows all its words.** The active-runs list now also returns `replayFrom` (just before the unfinished runs' first events, in the same statement), and the web follows the stream from there. Replayed events are idempotent; words already applied, or for a saved reply, are skipped. Chosen over a `partialText` field because the replay also brings back the reply's tool lines and cards, and needs no second way of building a reply.
- **Event ids become visible in order on Postgres.** A transaction adding events to a chat first takes that chat's advisory lock (until it commits), so a stream at id N can't miss a smaller id committed later.
- **Approval card:** when someone else decides while your edit is open, the form closes and focus moves to the decision line once, not again on later renders.
- **Edit form:** clearing an optional field the bot sent sends `null` if the schema allows it, else leaves it out, never `""`.

## 2026-11-13: approvals follow-ups: live state for chats opened later, saved tool lines

Gaps found while building approvals, fixed on the API and the web.

- **A chat opened later sees what's going on.** New `GET /orgs/{id}/threads/{threadId}/runs?active=true` lists the chat's runs that are queued, running, waiting for approval or needing attention, with `lastEventId`, read in the same statement. The web asks for it first, then follows the event stream after that id and loads the messages, so nothing in between is missed: a running bot shows "Thinking…", a paused one "Waiting for approval", a stuck one the needs-attention notice with Stop.
- **Tool lines survive a reload.** The saved reply keeps one `tool-call` part per call, in the order the calls were made, after the call's approval card: the same "Used Send email · done" lines the chat showed live.
- **An edited approval's summary is rebuilt** from the edited arguments, with the tool's own summary function.
- **No hydration warning in API mode.** The store's server snapshot is fixed and has no demo data in API mode, so the server and the browser's first render agree (the chat list shows its skeleton until the API answers). Checked in a browser: 4 warnings before, 0 after.
- **Approvals, from a review:** decisions are final in the store (a slow poll or a replayed event can't bring the buttons back, and a finished run is never paused again); a 409 counts as "someone decided" only when the approval really is decided, so an edit survives "this tool isn't available any more", and an open form says who decided instead of vanishing; focus moves to the first field on Edit, back to Edit on Cancel, and to the decision line after deciding, inside a live region that announces it; edited arguments leave out optional fields the bot didn't send and keep numeric choices as numbers; the Approvals page shows a load error with Try again and reloads on an org switch.

## 2026-11-13: Models & keys hardened after a security review

An independent review of Models & keys found eight problems; all are fixed, with tests. Details: [backend guide](backend/README.md#custom-servers-and-ssrf).

- **No redirects on chat calls (high):** the OpenAI and Anthropic SDKs follow redirects, so a custom server could bounce a run's request (conversation and key) to `169.254.169.254`. Chat models now get BotDesk's own HTTP clients with `follow_redirects=False`.
- **DNS rebinding closed:** calls to custom servers (model lists and chats) go through `GuardedTransport`, which resolves once, checks every address and connects to the checked IP, keeping the Host header and TLS name.
- **Fails closed:** the SSRF guard is on in every environment (`ALLOW_PRIVATE_MODEL_URLS=true` opts out, e.g. for Ollama on localhost). The public development `SECRET_KEY` is used only with an explicit `ENVIRONMENT=development` or `test`; otherwise `SECRET_KEY` is required and must be 32+ characters. New `SECRET_KEY_OLD` rotates keys (`MultiFernet`).
- **Editing a custom server** with the key left blank keeps its key; changing the base URL needs the key again or "This server needs no key" (the web form says so).
- **Two first saves at once** end as one key instead of a 500.
- **Chat timeouts** (10 s connect, 60 s between chunks); run errors remove the exact key the request carried, whatever its format; environment provider keys are `SecretStr`.

## 2026-11-13: the plugin SDK as its own package (build step 3)

Plugins now build on a small, separate package instead of a file inside the API, as [ADR 0006](adr/0006-repo-structure-plugins-and-project.md) decided. Details: [backend guide](backend/README.md#plugins), [SDK README](../packages/plugin-sdk/README.md).

- **One Python workspace** at the repo root (`pyproject.toml`, `uv.lock`, `.venv`) with `apps/api`, `packages/plugin-sdk` and `plugins/*`. `apps/api/uv.lock` moved to the root; set up with `uv sync --all-packages`. CI runs `uv sync --frozen --all-packages`, and `pnpm check` now also checks the SDK and the demo plugin (each has a small `package.json` so Turborepo runs its ruff, mypy and pytest).
- **`packages/plugin-sdk`** (`botdesk-plugin-sdk` 0.1.0, MIT, typed): `PluginManifest`, `ToolSpec`, the 7 risk classes, egress, `ToolContext` (ids, idempotency key, logger; no database, no settings), `ToolResult`, `NoArgs`, `validate_manifest`, and `testing.call_tool` to run a tool without the app. Depends only on Pydantic. A README with a five-minute "first plugin" guide and the release steps; not on PyPI yet.
- **Entry points + allowlist:** plugins register under `botdesk.plugins`; the API imports only the ids in `PLUGINS`. A plugin that fails to import, raises, or breaks a rule (unique tool names, known risk class, Pydantic args model, async handler, id matching its entry point) is skipped with one log line; the API keeps running. An allowlisted id nobody provides stops startup, since it's a typo.
- **The demo plugin** moved to `plugins/demo` (`botdesk-plugin-demo`), uses only the SDK, and loads through its entry point. Runs, policy and approvals behave exactly as before; their tests changed only in imports.
- **API:** `GET /api/v1/orgs/{id}/plugins` lists the loaded plugins and their tools (name, title, description, risk) for the "Connect apps" page.

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

# Progress

A short history of BotDesk, newest first. For one checklist of what is done and what is next, see [ROADMAP.md](ROADMAP.md).

## 2026-11-19: Answering a run that needs attention

Details: [backend guide](backend/README.md#tools-and-approvals), [frontend guide](frontend/README.md#talking-to-the-api).

- **It was done / It wasn't done.** A run stopped because a send may have gone out (its call left `started`, ADR 0004 §2) can now be answered, not only stopped: `POST /runs/{id}/resolve` with `{outcome: "done" | "not_done"}`. "Done" finishes the call `succeeded` with "A person checked: it was done.", "not done" finishes it `failed` with "A person checked: it wasn't done." The run carries on from its checkpoint (`tool_finished` with the real status, then `run_resumed` with `after: "attention"`); the model reads the answer and the call is never run again. After "not done" the model may try again as a new call, which the policy decides again (Ask before acting asks again). Who may answer: whoever can see the run, but only the account's member for a call through a member's own account (the approvals rule). One conditional UPDATE, so of two answers at once one wins and the other gets 409.
- **Web:** the needs-attention notice has It was done and It wasn't done next to Stop, all off while one is sending; errors are toasts.

## 2026-11-18: Organization security ceiling, member keys, creating organizations

Details: [backend guide](backend/README.md#the-security-ceiling) ([member keys](backend/README.md#member-keys)), [frontend guide](frontend/README.md#talking-to-the-api). Finishes work started on 2026-11-17 (branch `wave4/gaps-org`), re-applied on the current code, completed and tested.

- **Security ceiling** (ADR 0004 §4, the "effective level"): `organizations.max_security_level` (migration `d5e1a7c3f920`, after `d4b8e1f0a372`; existing orgs get `autonomous`, no ceiling). Owners and admins set it with `PATCH /orgs/{id}` (`maxSecurityLevel`). No bot is hired or raised above it (400, for every role); lowering a bot, or resending its level, is fine. The default for new bots stays at or under it (lowering the ceiling lowers it). A run's level is the strictest of ceiling, bot and run, read when it loads its context, and the ceiling is read again before every tool call, so lowering it reaches runs already going. Routines, the Gmail new-email trigger and handoff children are capped the same way (tested end to end on SQLite).
- **Member keys** ("My keys"): `provider_credentials.user_id` (migration `e8b3c6d2a417`, after the ceiling; partial unique indexes: one org key per built-in provider, one member key per member and provider). `GET/PUT/DELETE /orgs/{id}/me/providers[/{provider}]`, any member, built-in providers only, checked live, encrypted like org keys. A run's key is its requester's own, then the org's, then the server's, then the stand-in; never another member's, never in another org. Only the member sees it (last 4 characters); leaving or being removed deletes it. Model lists follow the same order and cache a member's list apart from the org's; OpenRouter prices fall back to the requester's key so budgets keep a price.
- **Create organization:** `POST /orgs` (`{name, slug?}`), the creator is owner; a slug is made from the name (cut to fit the 64-character column) or must be free (409). Web: "New organization" in the org switcher opens a dialog, then switches to the new org, where first-time setup starts.
- **Web:** Settings → Security has "Highest level for every bot"; the security-level picker shows levels above the ceiling as unavailable (Create bot, Edit bot, the default), "Your bots" and the bot details say "Capped at … by the organization". Settings → Models & keys has My keys. The stand-in reply mentions My keys.
- **Review fixes (same day):** an approved call meets the policy again before it runs, so one approved after the ceiling dropped to a level that denies it is refused, never run (the card stays Approved, the tool line and the bot say why); refusals say whether the bot's level or the organization's ceiling caused them. OpenRouter prices come from the org's key first, and a member's broken key only pauses that member's price lookups. A key saved just as its member was removed isn't kept, and removing a member drops their cached model lists. Creating organizations is limited to 5 an hour per person.
- **Later:** a Test button for your own key; your own key for memory.


## 2026-11-18: Email can't be sent twice, and send cards show everything that's sent

Details: [backend guide](backend/README.md#tools-and-approvals), [plugin README](../plugins/gmail/README.md); [ADR 0015](adr/0015-gmail-attachments-formatting-and-drafts.md) has an update section.

- **A send that may have gone out stops the run.** A tool that isn't idempotent and changes something outside BotDesk (`gmail.send`, `send_draft`, an MCP tool, the demo's send) and timed out, broke or answered nonsense after it may have reached the other app was marked failed, so the model tried again, and an Autonomous bot sent a second email with nobody asked. Now the call stays `started`, its line in the chat says "Tried … · may have been done" (`tool_finished` with `status: "unknown"`), and the run stops as needs attention; it is never run again. It still fails (and the model may retry) when it certainly didn't happen: the tool never ran, or every request that could change something got a 4xx refusal or never connected (`ctx.http` keeps count; a 5xx, a dropped connection or a read timeout counts as "may have"). Plugins whose requests BotDesk can't see (no egress, MCP) say "nothing was done" with the SDK's new `NotDone`.
- **`gmail.send_draft` shows the draft's text.** `gmail.list_drafts` returns each draft's whole text and attachments' names; `send_draft` carries them, the card shows them, and nothing is sent if the draft's text or attachments changed since (as for its recipients and subject).
- **No hidden characters on a card.** Gmail refuses zero-width characters, right-to-left overrides, invisible "tag" letters and line separators in subjects, bodies and attachment names; every card writes any that reach it as `[U+202E]` (SDK: `hidden_characters`, `show_hidden`). Emoji and scripts keep the joiners they need. Also checked: summaries already list cc and bcc, Markdown HTML already escapes the model's markup, header injection was already refused; tests added for each.
- **Review fixes (same day):** an MCP answer that can't be used (an internal error, not MCP, a request for input) now counts as "may have been done" (only method-not-found / invalid-params reach the model); `ctx.http` counts each request on its own, so sends at once can't clear each other; a send cut off by Stop or the time limit is noted, and a run that ran out of time with one needs attention; a draft whose HTML says something else, hides text, has another kind of part or holds invisible characters is never sent by a bot; a pile of combining marks counts as hidden. MCP: adding and refreshing keep no transaction open while the server is called, each sign-in request has 15 s in all, a server's own error text is never its status on Connect apps, and snapshot changes lock the server's row.
- **Later:** after Stop, the next run isn't told that a send may have gone out (the chat's line says so). (Answering a needs-attention run: done 2026-11-19.)

## 2026-11-18: MCP sign-in with OAuth, and reviewing MCP tools (slices 7.3, 7.4)

[ADR 0012](adr/0012-mcp-servers.md); what changed while building: [ADR 0016](adr/0016-mcp-sign-in-and-review-as-built.md) (proposed). Details: [backend guide](backend/README.md#mcp-servers), [frontend guide](frontend/README.md); manual test: [testing/mcp.md](testing/mcp.md).

- **Review before anything is offered:** a new MCP server's tools are pending until an owner or admin approves them on **Review tools** (`/apps/mcp/[serverId]`): which tools bots get, and each one's risk (lowering below "sends outside your org" is audited). The add dialog's second step leads there.
- **Drift:** every call re-lists the server's tools and compares hashes; a changed tool fails the call and stops being offered until re-approved, a new one waits, a removed one shows until the next review. The review shows the diff: description word by word, schemas line by line. Connect apps has a "1 tool changed" / "2 new tools" badge, and a bot's Tools says "N tools to review".
- **OAuth sign-in:** discovery (Protected Resource Metadata, authorization-server metadata, PKCE S256, `resource`, `iss`), client by the spec's order (pasted, Client ID Metadata Document served at `/api/v1/oauth/client-metadata/<id>.json` when the API is public https, dynamic registration), tokens in the vault and refreshed with the shared lease, Reconnect, revocation at the authorization server on remove or disconnect, and "needs more access" (403 `insufficient_scope`) asking for the extra scopes on Reconnect. Every sign-in address goes through the SSRF guard, answers are capped at 256 KB, and no token reaches a log line or a response.
- **Who may:** switching a server that uses the organization's key or sign-in on or off for a bot now takes an owner or admin (it binds an org-owned account, ADR 0010 §3); keyless servers stay open to every member.
- **Later:** member- and bot-owned MCP sign-ins; noticing drift without a call or a Refresh; trying it against a real OAuth MCP server (tests use the SDK's server and a fake authorization server).

## 2026-11-18: Chat gaps finished (unread, groups, prices) and marketplace templates from the API

The 2026-11-17 entry below was written while that work was still partial; this finishes it. Details: [backend guide](backend/README.md#bots-working-together) (managing a group), [templates](backend/README.md#marketplace-templates), [frontend guide](frontend/README.md#talking-to-the-api).

- **Groups, fixed:** changes to one group now happen one at a time (its row is locked, and the asker must still be in it), so two adds of the same bot no longer fail with a duplicate key and two removals at once can't leave a group with nobody in it (Postgres test, `test_unread_postgres.py`). Removing a bot stops its unfinished runs in that group, so it no longer posts into a group it left. A deleted bot leaves its groups, and someone removed from the organization leaves its groups; an open stream also ends when you're no longer a member of the organization (before, a removed member's open tab kept hearing the chat). A change is read once, not twice, for its answer and its live event.
- **Unread and groups on the web, fixed:** a removal replayed after you were added back no longer drops the group (the chat list decides); a chat list that was on its way no longer brings back the count of a chat you just read, drops a chat you just started (a new hire's DM or group could vanish for 20 s), or rolls back a newer preview; a chat opened in a background tab isn't marked read until you look; the badge caps at "99+" and reads "N unread messages"; Remove isn't offered on yourself (leaving is later) and the rename and Remove buttons have 44 px tap areas on phones.
- **Dated prices, checked:** `ModelResolver` takes a `now` clock, and a test shows a run is priced at the moment of each call (December's price from the first call after midnight UTC); another checks every step list starts at `date.min` and runs oldest first.
- **Marketplace templates from the API:** one catalogue, `apps/api/src/templates/catalogue.json` (Chief, with its chief-of-staff instructions, Inbox Zero, Outbound SDR, Recruiter, Expense Clerk, QA Tester, Researcher), served by `GET /templates` (plugins this server loaded only) and hired by `POST /orgs/{id}/templates/{templateId}/hire`: the API makes the bot with the template's instructions, its plugins switched on (Gmail on with no account yet), $20 a month, the default model, and the stricter of the template's security level and the org's default. The demo shows the same catalogue (a test keeps the copy word for word). Ids changed from `tpl_*` to slugs (`chief`, `inbox-zero`, …). Taken from the 2026-11-17 `wave4/gaps-chat` work; its separate unread table was dropped in favour of `last_read_at`.
- **Review fixes:** deleting a bot locks its groups first (it could deadlock with a group change on Postgres); a run queued for a bot at the moment it was removed is cancelled when it would start; someone leaving the organization is announced to each group's people (`thread_updated`), and a group left with nobody in it is deleted; on the web, a chat that left your list (you left it, its bot was removed, a live removal) no longer comes back from a chat list that was on its way.
- **Later (unchanged):** an org-wide event stream; "leave group"; a confirm before removing a person; a live `thread_updated` when a bot is deleted (its groups update on the next 20 s refresh).

## 2026-11-17: Unread counts, managing groups, dated model prices

Details: [backend guide](backend/README.md#unread-counts), [frontend guide](frontend/README.md#talking-to-the-api).

- **Unread counts:** `thread_participants.last_read_at` (migration `4c1e9b7d2a80`, existing rows start read). The chat list returns `unread` per chat for you (messages after your mark by someone else; bots and system notices count, yours don't) in one grouped query. `POST /threads/{id}/read` marks a chat read; the web calls it when a chat is on screen in a visible tab (open, back to the tab, each new message), adds one live for messages heard elsewhere, and refreshes the list every 20 s while visible.
- **Managing a group:** `PATCH /threads/{id}` (rename), `POST /threads/{id}/participants`, `DELETE /threads/{id}/participants/{type}/{id}`, for the group's creator, owners and admins (the lead's rule). Removing the lead bot clears it; a removed person can't open the group and their open stream ends; the last person stays; a DM can't be changed. Changes (and lead changes) go out live as `thread_updated`. Web: a rename pencil, "Add people or bots" and Remove buttons in the group's details pane.
- **Dated prices:** `PRICE_TABLE` entries can be `(effective_from, price)` steps; the price in effect at the call's time is used. The Gemini changes on 2026-12-01 and 2027-01-01 are in, so nothing needs editing on the day.
- **Later:** an org-wide event stream (unread counts for chats not open come from the 20 s refresh); "leave group" for members; a confirm before removing a person.

## 2026-11-17: Onboarding (first-time setup)

Details: [frontend guide](frontend/README.md#routes).

- **Who sees it:** after sign-up, the owner of an organization with no bots goes from `/` to `/welcome` (`lib/onboarding.ts`, `onboarding/use-onboarding-redirect.ts`; `/welcome` itself sends members and the demo home). Invited members, admins, teams with bots and the demo never do. Finishing or skipping is remembered per organization in this browser (`botdesk.onboarding.done.<orgId>`), so it never nags; no new API field.
- **Steps** (`features/onboarding/`, outside the app shell, progress bars and Skip on each): name the organization (prefilled, `PATCH /orgs/{id}` only if changed); add an AI key (the Models & keys dialog; "Skip — bots will use a stand-in reply"); hire Chief (a new marketplace template) or Inbox Zero, or leave to create one from scratch; connect Gmail (the Connect apps dialog; a server without a Google client says so and links the guide). Finish opens the first hired bot's DM.
- **Welcome message:** an empty DM now opens with the bot introducing itself (`threads/dm-welcome.tsx`, `lib/bot-welcome.ts`), so a new bot's chat never starts blank on the API either.
- **Later:** after Google sign-in the browser lands on `/apps/callback`, not back in the bot's DM; the store has no "bots failed to load" state, so an owner whose bot list fails to load is offered setup (Skip setup gets out). (Chief's chief-of-staff instructions were in fact added that day; see 2026-11-18.)

## 2026-11-17: Gmail extras: easier HTML mail, attachments, Markdown mail, drafts

Details: [plugin README](../plugins/gmail/README.md); manual test: [testing/gmail.md](testing/gmail.md#5-extras-attachments-markdown-mail-and-drafts). Owner-approved additions to [ADR 0011](adr/0011-gmail-plugin.md) §3 ("not in v1": attachments, HTML compose); its email rules (§4) are unchanged.

- **Reading HTML mail:** numbered lists (`1.`), table cells as `a | b` one row per line, quotes as `> ` lines, no zero-width preview filler, no bare links from images. Quoted earlier mail at the end of a reply ("On … wrote:" and the `> ` lines) is left out, with a `quoted` note outside the email block; forwards and quote-only messages stay whole. Fixtures: a newsletter and a reply chain.
- **`gmail.read_attachment`** (read, taints the run): by message id and the attachment's `part`, which `gmail.read_thread` now lists (Gmail's attachment ids change between reads, so the tool looks the part up again). Text, CSV, JSON, XML and HTML only, up to 100 000 characters in an `<email>` block; PDFs, images and Office files aren't downloaded and the result says why; at most 10 MB.
- **Markdown mail:** `gmail.send` and `create_draft` take `format: "markdown"` and send `multipart/alternative`: the body as written plus HTML we generate (`markdown.py`: headings, lists, bold, italic, code, http(s)/mailto links). The model's own HTML is escaped. Plain text stays the default.
- **Drafts:** `gmail.list_drafts` (read, taints: reply drafts quote outside mail) and `gmail.send_draft` (external-send). The call carries the draft's recipients and subject, so the card reads "Send draft r-5512 to sara@acme.dev (cc …; bcc …): “Subject”"; right before sending the tool fetches the draft and sends nothing if they differ.
- **Later:** PDF text, the draft's body on the send-draft card, signatures trimmed, quotes in other languages ("a écrit", "schrieb"), images' alt text, attachments on outgoing mail.

## 2026-11-17: Gmail finished: write tools and "React to new email" (slices 6.2-6.4)

[ADR 0011](adr/0011-gmail-plugin.md). Details: [backend guide](backend/README.md#gmail-tools-and-the-new-email-trigger), [owner's guide](self-hosting/google-oauth.md); manual test: [testing/gmail.md](testing/gmail.md).

- **Write tools (6.2):** `gmail.add_labels`, `remove_labels`, `archive`, `create_draft` (write-external), `send` (external-send), `trash` (destructive), all on `gmail.modify`. Plain-text mail built with the standard `email` package; replies threaded (`threadId`, `In-Reply-To`, `References`); bare addresses only, at most 20 recipients, one-line subject, so header injection is refused before an approval card exists. Cards read "Send an email to sara@acme.dev (cc …; bcc …): “Subject”: start of the body". A send is one request, never retried.
- **New-email trigger (6.3):** "React to new email" in a bot's Tools tab (`PUT /bots/{id}/tools/{plugin}/triggers/{trigger}`, table `trigger_subscriptions`, migration `e5a9c3f71d20`). The `poll_triggers` job (every minute) asks Gmail's history API for new inbox mail; each email posts "New email from …: …" in the subscriber's DM and starts a tainted run that reads it with `gmail.read_thread`. No backfill, own mail/promotions/social skipped, at most 10 a minute, an expired history id gives one "missed some new mail" note, a connection needing reconnect pauses it, one failing subscription never blocks the rest. SDK: `TriggerPollResult.notice`.
- **Docs (6.4):** what bots can do with Gmail and how to switch on the trigger, and a step-by-step manual test.
- **Later:** sending an existing draft by id (with its content on the card), HTML mail and attachments, label filters and a Gmail query per trigger, Pub/Sub push, a quarantined reader for email, the trigger's own security level.

## 2026-11-17: MCP servers as bot tools (slice 7.2)

[ADR 0012](adr/0012-mcp-servers.md), the lean version. Details: [backend guide](backend/README.md#mcp-servers); manual test: [testing/mcp.md](testing/mcp.md).

- **API:** `mcp_servers` (migration `73107c948749`) and `/orgs/{id}/mcp-servers` (list for every member; add, refresh, remove for owners and admins). Adding connects through the SSRF guard (https, public addresses unless `ALLOW_PRIVATE_MCP_URLS=true`), lists the tools and saves a hash-pinned tool snapshot; an optional API key is sent in a named header and kept sealed. Each server is the plugin `mcp-<id>` with sanitised tool names, bindable per bot in the Tools tab.
- **Safety:** every MCP tool is `external-send` with untrusted output (asks under Ask before acting; its result taints the run), annotations are ignored, calls are re-checked against the snapshot hash first ("This tool changed on the server; an admin must refresh it."), limited to 60 s and 256 KB of text; sampling and elicitation are refused.
- **Web:** an MCP servers section on Connect apps with the Add server dialog, tool counts, Refresh and Remove; members read only; the demo says it needs the API.
- **Later:** MCP OAuth (7.3), the review/drift screen with per-tool risk (7.4), the drift check at run start.

## 2026-11-16: bots hand off work, each bot's Tools, Gmail read, and reviews

Built in parallel waves; every piece was independently reviewed and its findings fixed with tests before merging.

- **Handoffs** ([ADR 0014](adr/0014-handoffs-and-tasks.md), [contract](architecture/handoffs-contract.md)): `team.handoff` gives a task to any bot in the organization. The parent pauses as `waiting_handoff` (freeing the chat), each child works in the same chat with a live handoff card, and the parent resumes exactly once with every result in `<task-results>`. Taint goes down and back up; a child is never looser than its parent; Stop cascades; tasks time out after 60 minutes; removing a bot mid-wait fails or cancels its tasks. Web: handoff cards, a "waiting for @sales and @inbox" notice, and a Chief demo in guest mode.
- **Bindings, slice 5.2:** each bot's Tools (`GET/PUT /bots/{id}/tools`), the toolset resolver, `runs.requester_id`; a member's own account serves only their DMs with that bot, and only they approve calls through it. Replacing or clearing an account someone else chose needs the right to that account.
- **Routines review fixes:** only the creator edits or runs a routine; a run keeps the security level it started at; a failing routine no longer blocks the rest; a budget stop skips a slot instead of switching the routine off; schedules that never come, use random fields or run under 5 minutes apart are refused; old routine runs are pruned.
- **OAuth review fixes:** revoke and refresh survive guard errors, the token call is bounded inside its lease, a failed refresh backs off, a late refresh can't revive a disconnected row, Google callbacks require `iss`, and the callback's query is kept out of access logs.
- **Gmail read, slice 6.1:** `gmail.search`, `gmail.read_thread`, `gmail.list_labels`; mail is plain text in `<email>` blocks, capped, and taints the run. SDK `OAuth2Auth.implied_scopes` (full access includes read).
- **MCP client, slice 7.1:** `mcp` 2.3 over the SSRF guard (one origin, https, no private addresses, size and time caps).
- **Smaller:** real app logos on Connect apps (simple-icons, bundled); hiring from the marketplace on the API uses the instance's default model.

## 2026-11-16: OAuth connections, slice 5.3 (backend)

[ADR 0010](adr/0010-connections-and-credentials.md) §5-§6, [contract](architecture/connections-api-contract.md). Details: [backend guide](backend/README.md#oauth-connections).

- **Connect with Google:** `POST /orgs/{id}/connections/oauth/start` → Google's sign-in page (PKCE S256, offline access); `GET /api/v1/oauth/callback` saves the connection and always sends the browser to `/apps/callback` with `connected` or an error code (`denied`, `expired`, `not-configured`, `signed-out`, `forbidden`, `failed`). Each sign-in is an `oauth_flows` row (migration `571864651dea`) used once, by its own member, within 10 minutes. Connecting the same account again updates the same connection.
- **`GET /orgs/{id}/connectors`** for Connect apps: how each app connects, its access levels, and whether the server has the client it needs (`GOOGLE_OAUTH_CLIENT_ID` / `_SECRET`).
- **Tokens stay fresh:** a token with under a minute left is refreshed before a tool uses it, one refresh per connection at a time (a lease on the row); a refused refresh marks the connection *needs reconnect*. Disconnecting also revokes the token at Google.
- **`plugins/gmail`:** provider `google`, Read or Full access, the account is the mailbox address. No tools yet (slice 6.1).

## 2026-11-15: routines that really run

- API: `routines` and `routine_runs` (migration `e1c4d7a92b30`), CRUD + Run now + recent runs under `/orgs/{org}/routines`. A `fire_routines` job every minute starts due routines as runs in the creator's DM (a "Routine: {name}" notice the run answers), hop 0, acting for the creator, at the strictest of the bot's and the routine's level. Missed slots run once, never as a backlog; a removed bot, a creator who left or a spent budget switches the routine off with a reason; a slot whose last run is still going is skipped.
- Web: the routines page, create/edit form (Every day, Weekdays, Every week, Every hour, or a cron line, in your time zone), Run now, delete, the bot's Routines tab and the "Created a routine" card on the API. The demo keeps its mock routines.

## 2026-11-15: the job queue

[ADR 0013](adr/0013-the-job-queue-lands.md) (supersedes ADR 0007). Details: [backend guide](backend/README.md#background-jobs).

- **Runs are jobs** on procrastinate (Postgres; its tables come from migration `b7f3a9c1d2e4`). A message, a bot's @mention reply and an approval decision save their `run_bot` job in the same transaction. Runs in one chat share a job lock, so they still go one at a time in order; the database guard and the per-bot cap stay.
- **Restarts don't lose replies:** a run interrupted by a restart carries on from its last saved step; a crashed worker's jobs are put back within a minute or two. Only SQLite still fails interrupted runs.
- **Approvals expire on a timer:** a job every minute expires approvals past `APPROVAL_EXPIRY_HOURS` and resumes their runs told "no".
- **Timers for the next slices:** periodic and delayed jobs are declared on one registry (`JOBS.task(name, cron=…)`); routines and Gmail polling will use it.
- **`WORKER_MODE`:** `embedded` (default, the worker inside the API) or `separate` (`python -m src.worker`, an optional `worker` service in docker compose). Live events reach other processes through Postgres `LISTEN/NOTIFY`.

## 2026-11-15: connections, slice 5.1 (backend)

[ADR 0010](adr/0010-connections-and-credentials.md), step 5.1 of the [build plan](architecture/connections-gmail-mcp.md). Details: [backend guide](backend/README.md#connections).

- **Connections:** a `connections` table (one authorised account on one connector, owned by a member, a bot or the organization) and an append-only `audit_log` (migration `6e4056385217`). `GET/POST/DELETE /orgs/{id}/connections` for API-key connections, with ADR 0010 §3's rules for who may create, see and disconnect. Disconnecting nulls the credential and keeps the row.
- **Credential vault** (`services/credential_vault.py`): the only code that decrypts a credential, with its own key purpose (`botdesk:connections:v1`) and the same `SECRET_KEY` / `SECRET_KEY_OLD` rotation as model keys.
- **`ctx.http`:** a tool calls other apps through an HTTP client that adds the credential itself (the tool never sees it), reaches only its plugin's declared hosts over https, never follows redirects, refuses private addresses (the SSRF guard), and caps response size (10 MB) and time.
- **Plugin SDK manifest v2** (additive; v1 plugins load unchanged): `auth` (`ApiKeyAuth`, `OAuth2Auth`), `egress` hosts, per-tool `scopes`, settings models, `triggers`, `ctx.connection`, and `FakeHttp` for tests.
- **Demo:** `demo.call_api` calls a web service with the connected Demo key. Until bindings (5.2), a run uses the bot's own connection, else the organization's; member connections wait for 5.2.
- The model-key dataclass `Connection` is now `ProviderAccess`, so "connection" has one meaning.

## 2026-11-15: bots working together

[ADR 0009](adr/0009-bots-working-together.md), slice 1. Details: [backend guide](backend/README.md#bots-working-together).

- **Mention routing** is one pure module (`services/mention_routing.py`, mirrored for the demo in `apps/web/src/lib/mention-routing.ts`), tested case by case.
- **Bots @mention bots:** a reply that mentions a bot in the chat starts its run one hop on, after the reply's run ends. Runs record `parent_run_id` and `hop` (migration `dca6e06f506b`). Past `BOT_HOP_LIMIT` (3) nothing starts and the chat shows "Stopped a chain of bot replies after 3 hops.". Taint travels along the chain; runs another bot started don't save memories.
- **Groups have a lead** (`lead_bot_id`): the first bot picked, or the one chosen in New group; it answers messages that mention no bot. Its creator, owners and admins change it in the details pane (`PUT /threads/{id}/lead`).
- **Guests in DMs:** @mention another bot of the org in a DM and it replies once as a guest (the DM's bot replies only if mentioned too). The @ list in a DM offers every bot, the others marked "Joins as a guest"; a guest's reply shows its name.
- **Demo:** the mock follows the same rules; say "relay" in a group to watch bots hand over until the hop limit stops them.

## 2026-11-15: who can sign up, and rate limits on auth

- **`SIGNUP_MODE`** (`open` by default, `invite-only`, `closed`): `POST /auth/sign-up` takes an optional `inviteToken`; with one, the new account joins the inviting organization instead of getting its own. Invite-only needs a valid invite for that email; closed takes no new accounts (sign-in and accepting invites still work); refusals are 403. `GET /auth/options` tells the web, whose sign-up, sign-in and invite pages adapt. Self-hosting now recommends invite-only once the first owner has signed up.
- **Rate limits:** sign-in (10/min per address, 5/min per email), sign-up (20/hour per address), forgot-password (20/hour per address, 5/hour per email) and reset-password (20/hour per address) answer 429 with `Retry-After`. A small in-process limiter with bounded memory (one API process, ADR 0007). The client address comes from `X-Forwarded-For` only from proxies in `FORWARDED_ALLOW_IPS`.

## 2026-11-15: no screen pretends to work

- **Default security level for new bots is real:** organizations have `default_security_level` (migration `381735fe703b`, default `ask-before-acting`), set with `PATCH /orgs/{id}` by owners and admins (members 403). A bot hired without a level gets it; create bot and marketplace hires start at it. Settings → Security loads and saves it, and says "saved" only once the API has.
- **Honest in API mode** (the demo is unchanged): Routines, New routine and the bot's Routines tab say bots can't run on a schedule yet, instead of saving routines nothing runs. Connect apps shows the server's plugins (`GET /orgs/{id}/plugins`) as built in, with each tool's risk, and the app catalogue as coming soon with Connect off. Answering a question card sends your choice to the chat, so the bot gets it. The marketplace drops made-up hire counts and Gmail tags.

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

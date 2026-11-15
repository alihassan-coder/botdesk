# 0011: The Gmail plugin

- Status: proposed
- Date: 2026-11-15
- Based on: [ADR 0002](0002-grok-bot-parity-and-plugin-platform.md) §2, [ADR 0004](0004-agent-runtime-and-safety.md), [ADR 0006](0006-repo-structure-plugins-and-project.md) §5, [ADR 0007](0007-runs-in-the-api-process-for-now.md), [ADR 0008](0008-free-and-open-source.md), [ADR 0010](0010-connections-and-credentials.md); sources at the end
- Build plan: [connections-gmail-mcp.md](../architecture/connections-gmail-mcp.md)

## Context

Gmail is the first real integration and the main source of prompt injection: every email is text written by a stranger. Google classes the useful Gmail scopes as **restricted**. A public app using them needs verification and a yearly CASA assessment, but BotDesk has no hosted service (ADR 0008): **every install uses its own Google OAuth client**. That puts Google's rules for unverified and "Testing" apps on every self-hoster, so the setup must be written down and the failure modes handled in the product.

There is no job queue yet (ADR 0007), and ADR 0007 asks to revisit before triggers. The new-email trigger is the first thing that runs on a timer.

## Decisions

### 1. A built-in plugin calling the REST API

`plugins/gmail` (`botdesk-plugin-gmail`, id `gmail`), runtime `builtin`, imports only the SDK. It calls `https://gmail.googleapis.com/gmail/v1/...` through `ctx.http` (ADR 0010 §8); manifest `egress = ("gmail.googleapis.com",)`, token and revoke endpoints are used by the API's OAuth module, not by the plugin. No `google-api-python-client` or `google-auth` (they want a raw credential, and they are large).

### 2. Scopes: two access levels, one scope each

| Access level (chosen at Connect) | Scope | Gives |
|---|---|---|
| **Read only** | `https://www.googleapis.com/auth/gmail.readonly` | search, read, labels list |
| **Read, organise, draft and send** (default) | `https://www.googleapis.com/auth/gmail.modify` | everything above, plus labels, archive, read/unread, drafts, send, trash |

- `gmail.modify` already covers read, compose and send ("all read/write operations except immediate, permanent deletion"), so asking for `readonly` + `compose` + `modify` together adds nothing. One scope per level keeps the consent screen short.
- Never `https://mail.google.com/` (permanent delete) and never `gmail.settings.*` (forwarding, filters, delegates: the `credential` actions an attacker would want). No `openid`/`email`: the account address comes from `users.getProfile`, which every Gmail scope can read.
- `access_type=offline`, `prompt=consent` (so Google always returns a refresh token), `include_granted_scopes=true`, PKCE. The connection stores the scopes Google actually granted; a person can untick a scope on Google's screen, and tools needing it are then hidden (ADR 0010 §4).
- The bot's **security level still applies on top**: a *Read only* bot on a full-access connection still can't label or send.

### 3. Tools and their risk

| Tool | Gmail API | Scope | Risk | Untrusted output | Idempotent |
|---|---|---|---|---|---|
| `gmail.search` (query, max 25) → id, thread id, from, subject, date, snippet, labels | `messages.list` + `messages.get(format=metadata)` | readonly | `read` | **yes** | yes |
| `gmail.read_thread` → messages as plain text | `threads.get(format=full)` | readonly | `read` | **yes** | yes |
| `gmail.list_labels` | `labels.list` | readonly | `read` | no | yes |
| `gmail.change_labels` (add/remove, incl. read/unread, star) | `messages.modify` / `threads.modify` | modify | `write-external` | no | yes |
| `gmail.archive` (remove `INBOX`) | `threads.modify` | modify | `write-external` | no | yes |
| `gmail.create_draft` (new or reply) | `drafts.create` | modify | `write-external` | no | no |
| `gmail.send` (new or reply, or an existing draft by id) | `messages.send` / `drafts.send` | modify | `external-send` | no | no |
| `gmail.trash` | `threads.trash` | modify | `destructive` | no | yes |

- Reading taints the run (ADR 0004 §5), so after a bot reads mail **every** label, draft, send and trash asks a person, at every security level. That is deliberate.
- `trash` is reversible in Gmail for 30 days, but it hides mail from the person, so it is `destructive` (never automatic in v1).
- Not in v1: attachments (metadata only: name, type, size), forwarding, filters, settings, permanent delete, HTML compose. Send is plain text, threaded with `threadId`, `In-Reply-To` and `References`; at most 20 recipients; `Bcc` shown on the approval card.
- Approval cards for `send` and `create_draft` show from (the connection's account), to/cc/bcc, subject and the full body; recipients and links that first appeared in outside text are highlighted (agents-and-plugins.md §5).

### 4. Prompt-injection defences specific to email

- Message bodies are converted to plain text (HTML stripped, no remote images, links shown as text with their domain), capped (20 000 characters per message, 60 000 per result, with a "truncated" note), and wrapped as untrusted data by the pipeline.
- Only selected headers reach the model (From, To, Cc, Date, Subject, Message-ID); never `Authentication-Results` noise or raw MIME.
- The bot has no tool that changes access (§2), so "set up forwarding to me" has nothing to call; a connection is never created by a tool (ADR 0010 §9).
- Runs started by the new-email trigger start **tainted**.
- Later, not v1: a quarantined, tool-less reader that turns an email into fields before the acting bot sees it.

### 5. The `new_email` trigger: history polling every 60 s by default

- **Polling is the default and the only mode in v1.** Each subscription keeps a `historyId` cursor and calls `users.history.list(startHistoryId, historyTypes=messageAdded, labelId=<filter>)` every 60 s. It works on a laptop with no public address, needs no Google Cloud Pub/Sub, and costs about 2 quota units a minute per mailbox.
- **Push (Pub/Sub) later**, as an opt-in: it needs a Pub/Sub topic with `gmail-api-push@system.gserviceaccount.com` allowed to publish, either a public HTTPS endpoint or a pull subscription with a service-account key, and a `users.watch` renewed at least every 7 days. Too much setup for the default.
- **Expired cursor** (404 from `history.list`; Google keeps history "at least a week", sometimes less): reset the cursor to the profile's current `historyId`, start no runs for the gap, and post one notice in the chat ("BotDesk missed new mail between … and …"). Never a flood of runs for old mail.
- **Filters** (bot settings): label (default `INBOX`), an optional Gmail query, skip mail sent from the connection's own address and skip `CATEGORY_PROMOTIONS` / `CATEGORY_SOCIAL` by default. At most 10 runs per subscription per poll; the rest are summarised in one run.
- **Where the run goes:** the subscribing member's DM with the bot. The trigger saves a short **event message** in that chat ("New email from Sara Lee: Invoice 4471", tainted) and starts a run with it as its trigger message and the subscriber as **requester**. Dedupe on (subscription, Gmail message id) in `trigger_events`.
- **Who runs the timer:** a small in-process **trigger poller** inside the API (an asyncio task, like runs today). It claims due subscriptions with `… FOR UPDATE SKIP LOCKED` and moves `next_poll_at` forward before polling, so two API copies never poll one mailbox twice. It sits behind a `TriggerScheduler` seam; when procrastinate arrives (ADR 0005) a periodic job replaces the task and nothing else changes. This **amends ADR 0007** ("nothing runs on a timer yet") for triggers only.

### 6. Own Google OAuth client: what a self-hoster sets up

1. A Google Cloud project; enable the **Gmail API**.
2. OAuth consent screen ("Google Auth Platform"):
   - **Google Workspace:** user type **Internal**. Only the domain's users can connect, no verification, no unverified-app screen, refresh tokens don't expire after 7 days. Recommended.
   - **Personal Gmail (or connecting accounts outside the Workspace):** user type **External**, then **Publish app → In production**. Do *not* stay in **Testing**: Google issues refresh tokens that expire after **7 days** to External apps in Testing that ask for anything beyond name, email and profile, so every connection would break weekly. In production but unverified, people see Google's "unverified app" screen (Advanced → continue) and the app is capped at 100 new users, which is plenty for one team. Verification and CASA are only needed for a public app, which an install is not.
3. Add the two scopes (`gmail.readonly`, `gmail.modify`).
4. Create an OAuth client of type **Web application** with the redirect URI `{API_PUBLIC_URL}/api/v1/oauth/callback`. Google requires HTTPS and a host name (no raw IPs) except for `localhost`, so a LAN install needs a real HTTPS name (a reverse proxy) or must be used from `localhost`.
5. Put the client id and secret in the API's environment: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (the secret is a `SecretStr`).

Connect apps shows Gmail as "Not set up on this server" with a link to the guide until both are set, and says why a connection broke when it does (`needs_reconnect` after `invalid_grant`, with a hint about Testing mode if it happened about 7 days after connecting). Google allows 100 refresh tokens per account per client; reconnecting is an upsert of the same row, so this limit only matters for someone reconnecting over and over.

### 7. Testing without Google

- **Plugin tests** use the SDK's `FakeHttp` (ADR 0010 §8) with JSON fixtures in `plugins/gmail/tests/fixtures/`, shaped like the Gmail API reference and scrubbed. A manual script (`plugins/gmail/scripts/record_fixtures.py`, needs a real test account, never in CI) refreshes them. The fixture set includes the injection corpus: an email telling the bot to forward invoices, hidden HTML text, a tracking image, a 2 MB body, a non-UTF-8 body.
- **API tests** of the OAuth flow inject an `httpx.MockTransport` for Google's token and revoke endpoints: success, `invalid_grant`, missing refresh token, scope unticked, state reused, state expired, other user's state.
- **End-to-end (Playwright):** a small **fake Google** (an ASGI app in `apps/api/tests/fakes/google.py`) serving `/authorize` (redirects straight back with a code), `/token`, `/revoke` and the Gmail endpoints used. Only when `ENVIRONMENT=test` may `GOOGLE_OAUTH_BASE_URL` / `GMAIL_API_BASE_URL` point at it.
- Trigger tests drive the poller with a fake clock: new mail, duplicates, expired cursor, two pollers racing.

### 8. What the owner must provide

- A decision on the open questions in the build plan (client in env vs admin UI; member connections in groups).
- For manual testing: a Google Cloud project with the client above, and a test Gmail or Workspace account that may receive test mail.

## Trade-offs

- **`gmail.modify` for the default level** is broad: the token could do anything but permanent delete. What a bot actually does is limited by the tools, the bot's level, taint and approvals; the scope is the ceiling, the policy is the guard. A narrower token is one click away (Read only).
- **Polling every 60 s** means up to a minute's delay and a timer per mailbox. Fine for an assistant; push comes later for those who want seconds.
- **Unverified "In production"** shows people a scary Google screen once. The alternative (Testing) silently breaks every week, which is worse.
- **An in-process poller before the job queue** is one more thing in the API process. It is small, guarded across copies, and replaceable.

## Alternatives rejected

- **`gmail.readonly` + `gmail.compose` + `gmail.modify`**: `modify` already includes the others.
- **`gmail.send` (sensitive, not restricted) for sending + `gmail.readonly`**: two scopes, still restricted because of `readonly`, and no labels or drafts.
- **Pub/Sub push as the default**: needs a public endpoint or a service account and a watch renewal job; most self-hosters have neither.
- **Google's Python client libraries**: need raw credentials in plugin code (ADR 0010 §8), heavy, and hard to fake.
- **Waiting for the job queue before the trigger**: the queue is a larger slice; the poller seam keeps the swap cheap.
- **A shared BotDesk Google client**: there is no hosted service to verify it (ADR 0008).

## Sources

- Gmail scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
- Gmail sync and history: https://developers.google.com/workspace/gmail/api/guides/sync
- Gmail push: https://developers.google.com/workspace/gmail/api/guides/push
- Refresh token expiry (Testing = 7 days; 100 tokens per account per client; 6 months unused): https://developers.google.com/identity/protocols/oauth2
- Web-server OAuth (redirect URI rules, `access_type=offline`, revoke): https://developers.google.com/identity/protocols/oauth2/web-server
- Unverified apps (100 new users, exemptions for internal and in-development apps): https://support.google.com/cloud/answer/7454865

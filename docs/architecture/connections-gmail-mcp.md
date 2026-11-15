# Build plan: Connections, Gmail, MCP servers

Status: proposed with [ADR 0010](../adr/0010-connections-and-credentials.md), [ADR 0011](../adr/0011-gmail-plugin.md) and [ADR 0012](../adr/0012-mcp-servers.md). Roadmap steps 5 (Gmail) and 8 (MCP) in [agents-and-plugins.md §14](agents-and-plugins.md#14-build-order-each-step-small-tested-and-usable), with the connection platform they share pulled out first. Terms: [GLOSSARY.md](../../GLOSSARY.md) (Plugin, Connector, Connection, Binding, Requester, MCP server, Tool snapshot).

Every slice ends **tested and usable**: migrations up and down, API tests on SQLite and Postgres where runtime is touched, web tests, and a screen someone can click. Sizes: **S** ≈ 1 day, **M** ≈ 2–3 days, **L** ≈ 4–5 days.

## The modules (seams first)

Deep modules with small interfaces, so each slice fills one in and tests it at its seam.

| Module | Interface | Hides | Tested with |
|---|---|---|---|
| **Credential vault** `services/credential_vault.py` | `save(connection, secret)`, `open(connection) → Credential` (never prints its secret), `revoke(connection)` | `SecretBox` purpose `botdesk:connections:v1`, JSON bundle, nulling on revoke | round trip, wrong key, rotation, "secret in no log line or response" |
| **OAuth flow** `services/oauth_flow.py` | `start(org, user, connector, owner, access) → authorize_url`; `finish(state, code, iss, session_user) → Connection` | `oauth_flows` rows, PKCE, state hashing, code exchange, account lookup, upsert | `httpx.MockTransport` for token/revoke |
| **Authorised HTTP** `plugins/authorised_http.py` | the SDK's `HttpClient` protocol, bound to one connection + manifest egress | header injection, refresh lease, 401 retry, host allowlist, no redirects, size cap, `GuardedTransport` | fake provider transport |
| **Toolset resolver** `runtime/toolset.py` | `toolset_for(run) → Toolset` (`get(name)`, `for_model()`, `hashes`) | bindings × connection usability × scopes × org off-switch × MCP snapshots | pure function over rows: big table test |
| **Trigger scheduler** `runtime/triggers.py` | `start()`, `stop()`, `poll_once(now)` | claim due subscriptions (`SKIP LOCKED`), call plugin `poll`, dedupe, post event message, start run | fake clock, fake plugin |
| **MCP client** `mcp/client.py` | `list_tools(server)`, `call_tool(server, name, args)`, `oauth_provider(server, owner)` | the `mcp` SDK, `httpx2`, guarded transport, result conversion, limits | in-process MCP test server |

The pipeline (`runtime/tool_pipeline.py`) changes in one place: `prepare` and `execute` take the run's `Toolset` instead of the global `ToolRegistry`, and `_run_tool` builds `ToolContext` with `http`, `connection` and `settings` from the binding.

## Slices, in order

### Slice 5.1 — Connection platform (backend) · M

The vault, the `connections` table, SDK manifest v2, `ctx.http`. No Google yet: proven with an API-key connector.

- **SDK** (`packages/plugin-sdk`): `ApiKeyAuth`, `OAuth2Auth`, `egress`, `ToolSpec.scopes`, `settings_model`, `bot_settings_model`, `TriggerSpec`, `HttpClient`/`HttpResponse` protocols, `ConnectionInfo`; `ToolContext.http/connection/settings` with defaults; `MANIFEST_VERSION = 2`, v1 manifests still validate; `testing.FakeHttp`. SDK minor version bump.
- **API:** rename `provider_service.Connection` → `ProviderAccess`; `SecretBox` takes a purpose; credential vault; `AuthorisedHttp` (API-key flavour first); `connections` + `audit_log` tables; `GET/POST/DELETE /orgs/{org}/connections` (API-key connections only); `API_PUBLIC_URL` setting.
- **Demo:** `plugins/demo` gains an `ApiKeyAuth` tool that echoes which host it called (against a fake), so the whole path runs in tests and locally.
- **Migration:** `connections`, `audit_log`, `tool_executions.connection_id`, `approval_requests.connection_id`.
- **Tests:** vault (round trip, rotation via `SECRET_KEY_OLD`, other purpose can't decrypt); `AuthorisedHttp` refuses non-egress hosts, http, redirects, private IPs, oversize bodies; secret never in responses/logs/run events; SDK v1 + v2 manifests validate; permissions table of ADR 0010 §3 (create/see/disconnect).

### Slice 5.2 — Bindings: each bot's Tools · M

Ends "every bot sees every tool".

- **API:** `bot_tools` table + backfill (every existing bot gets each auth-less built-in plugin, all tools); new bots get the same; `GET/PUT /orgs/{org}/bots/{bot}/tools`; toolset resolver; `runs.requester_id` (hop-0 author, copied down chains); pipeline uses the run's toolset; tool hashes saved in run state, re-checked on resume; approval restricted to the connection owner for member-owned connections; decision trace gains `via=…`; `organization_plugins` off-switch (admins) for built-ins.
- **Web:** per-bot **Tools** tab (see Screens). Store: `useBotTools(botId)`, `actions.setBotTools(...)`; mock data in `data/mock/` for guest mode.
- **Migration:** `bot_tools`, `organization_plugins`, `runs.requester_id`, backfill.
- **Tests:** resolver table (member connection in owner's DM ✓, in someone else's DM ✗, in a group ✗, bot-owned anywhere ✓, `needs_reconnect` ✗, missing scope ✗, plugin off ✗); upgrade keeps today's behaviour; resume after a tool was unbound → refused with reason; only the owner may approve calls through their connection (others get 403).

### Slice 5.3 — OAuth connections and Connect apps · M

- **API:** OAuth flow module; `oauth_flows` table; `POST /orgs/{org}/connections/oauth/start` → `{authorizeUrl}`; `GET /api/v1/oauth/callback` (session cookie, state single-use, 303 to `{WEB_APP_URL}/apps/callback?result=connected|error&code=…`); refresh with lease; `invalid_grant` → `needs_reconnect`; disconnect with provider revocation; `GET /orgs/{org}/connectors` (built-ins + org MCP servers, with `setup: ready|not-configured`, auth type, access levels, triggers). Google as the first `OAuth2Auth` (the Gmail plugin's manifest with **no tools yet** is enough to connect and show the account).
- **Settings:** `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`; test-only `GOOGLE_OAUTH_BASE_URL`, `GMAIL_API_BASE_URL`.
- **Web:** Connect apps on the API (real connectors, "Your connections", "Not set up on this server"), Connect dialog with owner and access level, **OAuth callback page**. Replace the guest-mode-only connect flow behind the store.
- **Tests:** flow cases from ADR 0011 §7; two concurrent refreshes → one token request; disconnect calls revoke and nulls the secret; web tests for dialog and callback page (success, denied, expired, not configured).

### Slice 6.1 — Gmail: read · S

`plugins/gmail` with `search`, `read_thread`, `list_labels`; HTML → text, caps, header filter; fixtures and injection corpus; account label from `users.getProfile`. Usable: "@inbox what did Sara send me this week?" in a DM.

### Slice 6.2 — Gmail: act, with approvals · M

`change_labels`, `archive`, `create_draft`, `send` (new, reply, draft), `trash`. MIME building (plain text, threading headers), recipient limits, approval-card previews (from/to/cc/bcc/subject/body), "as ali@acme.dev" on cards, highlighting recipients and links seen in outside text. Tests: tainted run → every write asks, even Autonomous; Read-only bot → denied; read-only connection → write tools absent; crash after `send` started → `needs_attention`, never a second send.

### Slice 6.3 — `new_email` trigger · M

- **API:** `trigger_subscriptions` (org, bot, connection, plugin, trigger, settings, cursor, `next_poll_at`, status, last error, created_by) and `trigger_events` (subscription, external id, unique); trigger scheduler (in-process task started in the app lifespan, `SKIP LOCKED` claim); the Gmail `poll` handler (`history.list`, expired cursor reset + notice, filters, max 10 runs per poll); event message in the subscriber's DM, run started tainted with the subscriber as requester; `GET/PUT /orgs/{org}/bots/{bot}/triggers`.
- **Web:** "When new email arrives" section in the Tools tab (Switch + label/query fields); event messages rendered as a compact card in the chat.
- **Migration:** both tables.
- **Tests:** fake clock; duplicate delivery; two schedulers racing; restart resumes from the cursor; 404 cursor; filters; budget-stopped bot doesn't poll.

### Slice 6.4 — Self-hoster guide · S (parallel with anything after 5.3)

`docs/self-hosting/gmail.md`: ADR 0011 §6 as click-by-click steps with the redirect URI, Internal vs External/In production, the 7-day Testing trap, the HTTPS-name requirement, and troubleshooting by error code. Linked from Connect apps' "Not set up" state.

### Slice 7.1 — MCP client spike · S (can start any time)

Prove `mcp` 2.x + `httpx2` with the SSRF guard ported to `httpcore2`: list and call against a local test server (2026-07-28 and a handshake-era server), redirects refused off-origin, private address refused. Output: `mcp/client.py` with its seam and tests, or the fallback from ADR 0012 §7.

### Slice 7.2 — MCP servers without OAuth · L

- **API:** `mcp_servers` (org, short id, name, URL, auth kind, timeouts, last checked, status) and `mcp_tools` (server, server name, local name, title, description, schemas, annotations, hash, approved hash, risk, idempotent, enabled, state `approved|pending|changed`); `POST /orgs/{org}/mcp-servers` (validates URL, lists tools), `POST …/{id}/refresh`, `PUT …/{id}/tools` (approve + risk overrides), `DELETE`; API-key auth via the vault; snapshot tools as `RegisteredTool(source="mcp")` in the toolset resolver; drift check at run start; result conversion and limits; every result taints.
- **Web:** **Add MCP server** dialog and the **Review tools** step; MCP servers on Connect apps; binding them in the Tools tab like any plugin.
- **Tests:** in-process MCP server fixtures: normal; rug pull (description changes → tool paused, run refused); new tool → pending; huge output → truncated; injection text → tainted, next call asks; `input_required` → refused; `isError`; timeout; tool names that collide or are too long; non-admin can't add; risk lowered → audited.

### Slice 7.3 — MCP OAuth 2.1 · M

`OAuthClientProvider` with vault-backed `TokenStorage`; pre-registered client fields in the add dialog; CIMD document route; DCR fallback; `resource` and `iss` checks; owner rules from ADR 0010; `insufficient_scope` → Reconnect. Tests against a fake authorization server (PRM, AS metadata, token endpoint).

### Slice 7.4 — Drift review UI · S

Connect apps badge "3 tools changed", a diff view (description and schema before/after) and re-approve. Can merge into 7.2 if it stays small.

## Order and parallel work

```
5.1 ──┬── 5.2 ──────────────┬── 6.2 ── 6.3
      └── 5.3 ── 6.1 ───────┘
                 6.4 (any time after 5.3)
7.1 (any time) ── 7.2 (after 5.2) ── 7.3 (after 5.3) ── 7.4
```

- 5.2 and 5.3 run in parallel after 5.1 (different tables, routes and screens; they meet in the toolset resolver, which 5.2 owns).
- 6.1 needs 5.3 for a real account, but can be written against `FakeHttp` as soon as 5.1's SDK lands.
- 7.1 touches no shared code and can start today. 7.2 needs 5.2's resolver.
- Migrations are linear per branch: each slice adds its own revision; rebase onto the latest head before merging.

## Screens (shadcn first)

All read and write through `apps/web/src/data/store.ts`; guest mode gets matching mock data in `data/mock/`.

| Screen | Where | Components |
|---|---|---|
| **Connect apps** | `/apps` (exists) | `Card`/`Item` per connector, `Badge` (Built in, Connected, Needs reconnect, Not set up), `Tabs` (All / Connected), "Your connections" as `Item` list with `DropdownMenu` (Reconnect, Disconnect → `AlertDialog`), `Empty` for none |
| **Connect dialog** | from Connect apps | `Dialog`, `RadioGroup` (Just me / A bot → `Select` / The organization (admins)), `RadioGroup` access level (Read only / Read, organise, draft and send), `Alert` for "Google will show an unverified-app screen" when relevant, `Button` → full-page redirect |
| **OAuth callback** | `/apps/callback` | `Spinner` while reading the result, then `Alert` (success / error with the mapped message) and a `Button` back; `sonner` toast on success |
| **Bot → Tools tab** | bot profile / edit dialog | `Tabs`, per plugin a `Card` with `Select` (connection), `Switch` per tool with a risk `Badge` and description `Tooltip`, `Alert` above 30 tools, trigger section with `Switch` + `Input` (label, query) |
| **Add MCP server** | Connect apps (admins) | `Dialog` with `Field`/`Input` (name, URL), `RadioGroup` auth (None / Header key / Sign in with OAuth), `InputGroup` for header name + value, `Collapsible` "Advanced" (client id/secret, timeout) |
| **Review tools** | step 2 of the dialog, and drift review | `Table` (tool, description, risk `Select` defaulting to Sends, `Checkbox` available), `Collapsible` arguments (`code-block`), `Alert` explaining taint and why tools ask, `Badge` Changed/New |
| **Approval card** (exists) | chats, approvals inbox | add "as ali@acme.dev" line and highlighted recipients |

Check each in a real browser (Playwright screenshots) and review with `web-design-guidelines`, as AGENTS.md asks.

## Open questions for the owner

1. **Google client in env or in the UI?** Proposed: `GOOGLE_OAUTH_CLIENT_ID/SECRET` in the server's environment (the operator registers the redirect URI anyway). Alternative: admins paste them in Settings, stored encrypted per organization.
2. **Member connections in group chats:** proposed off in v1 (only the owner's DMs). OK, or allow per binding?
3. **Trigger runs before the job queue:** proposed in-process poller (amends ADR 0007 for triggers). Or build the queue (step 4) first?
4. **Default Gmail access level:** proposed "Read, organise, draft and send" (`gmail.modify`). Or default to Read only?
5. **Who may add MCP servers:** proposed owners/admins only.

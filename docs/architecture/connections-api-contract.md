# Connections API contract (slices 5.2 and 5.3)

Status: the web side is built against this (`apps/web`: Connect apps, Tools tab, `/apps/callback`); **the backend is not built yet**. Build exactly this. Background: [ADR 0010](../adr/0010-connections-and-credentials.md), [ADR 0011](../adr/0011-gmail-plugin.md), [build plan](connections-gmail-mcp.md). Terms: [GLOSSARY.md](../../GLOSSARY.md).

JSON is camelCase. Every route is under `/api/v1`, and org-scoped ones are under `/orgs/{org}` (they take `OrgAccess`). Errors are `{"detail": "<sentence people can read>"}`.

## Routes

### Connectors (Connect apps)

`GET /orgs/{org}/connectors` returns `ConnectorOut[]`, one per loaded plugin (it replaces `/plugins` on Connect apps; keep `/plugins` working):

```json
{ "id": "gmail", "name": "Gmail", "description": "…", "version": "0.1.0",
  "authType": "oauth2" | "api_key" | null,
  "setup": "ready" | "not-configured",
  "accessLevels": ["read", "full"],
  "defaultAccess": "full" | null,
  "tools": [{ "name": "gmail.search", "title": "…", "description": "…", "risk": "read" }] }
```

- `accessLevels` holds the keys of `OAuth2Auth.scope_sets`, and is `[]` when the plugin isn't OAuth2.
- `defaultAccess` is `"full"` when that key exists, otherwise the first key, otherwise `null`.
- `setup` is `not-configured` when an OAuth2 plugin's `provider` has no client set on the server. Today only `google` is known, and it needs both `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`. Plugins with no auth or an API key are always `ready`.

### Connections

| Method and path | Body | Response |
|---|---|---|
| `GET /orgs/{org}/connections` | | `ConnectionOut[]` (exists since 5.1) |
| `POST /orgs/{org}/connections` (API key, exists) | `{connectorId, ownerKind, botId?, accountLabel, apiKey}` | 201 `ConnectionOut` |
| `POST /orgs/{org}/connections/oauth/start` | `{connectorId, ownerKind: "member"\|"bot"\|"org", botId?, access?}` | 200 `{authorizeUrl}` |
| `DELETE /orgs/{org}/connections/{id}` | | 204, and the token is now also revoked at the provider |

`ConnectionOut` is `{id, connectorId, ownerKind, ownerUserId, ownerBotId, authType, accountLabel, scopes, status, statusReason, createdAt, lastUsedAt, createdBy}`.

- `status` is one of `active`, `needs_reconnect` or `revoked`. The web hides revoked connections.
- The response never carries a token or any other secret.

`oauth/start` fails with these errors:
- 404 for an unknown connector.
- 400 when the connector isn't OAuth2, when it's not set up ("Gmail isn't set up on this server yet."), when `access` is unknown, or when `ownerKind` is `bot` without a `botId`.
- 403 when the member may not create a connection for that owner (the same rules as the API-key route, ADR 0010 §3).
- Reconnect is the same call with the same owner. It updates the same row, matched by `account_ref`.

### OAuth callback

`GET /api/v1/oauth/callback?state=…&code=…` (or `?error=…`) is not org-scoped. It reads the session cookie, which is `SameSite=Lax` and so arrives on this top-level redirect.

It always answers **303** to the web:
- `{WEB_APP_URL}/apps/callback?result=connected&connector=<id>`, or
- `{WEB_APP_URL}/apps/callback?result=error&code=<code>`.

| `code` | When |
|---|---|
| `denied` | the provider returned `error` (the person cancelled) |
| `expired` | the state is unknown, already used, expired (10 min), or was started by another user |
| `not-configured` | the client was removed after the flow started |
| `signed-out` | there's no session |
| `forbidden` | the user is no longer allowed to create a connection for that owner (role changed, left the org) |
| `failed` | anything else: code exchange, account lookup, network |

Never put provider text in the URL. The web maps any unknown code to the `failed` message.

The redirect URI sent to Google is `{API_PUBLIC_URL}/api/v1/oauth/callback`.

### Bot tools (bindings)

`GET /orgs/{org}/bots/{bot}/tools` returns one entry per loaded plugin. A plugin with no binding comes back with `enabled: false` and `connectionId: null`:

```json
{ "plugins": [{ "pluginId": "demo", "name": "Demo", "description": "…",
  "authType": "api_key" | "oauth2" | null, "enabled": true, "connectionId": "uuid" | null,
  "tools": [{ "name": "demo.send_email", "title": "…", "description": "…", "risk": "external-send" }] }] }
```

`PUT /orgs/{org}/bots/{bot}/tools` takes the body `{ "plugins": [{ "pluginId", "enabled", "connectionId": "uuid" | null }] }`. Only the plugins sent change, and the response has the same shape as GET.

Errors:
- 404 when the plugin or connection is unknown or not visible.
- 400 when the connection belongs to another connector ("That account is for another app.") or has been revoked.
- 403 when the member may not bind that connection, following ADR 0010 §3:
  - a member-owned connection: only its member;
  - a bot-owned one: owners and admins, or the bot's creator;
  - an org-owned one: owners and admins.

Any member may switch a plugin on or off, which is the same rule as editing a bot. Leaving a connection unchanged is never refused.

Write `connection.bound` and `connection.unbound` lines to the audit log.

## Data model (one migration, `down_revision` = current head)

- **`bot_tools`** has `id`, `org_id`, `bot_id` (cascade), `plugin_id` (80), `connection_id` (FK `connections`, `SET NULL`, nullable), `enabled` (bool, default true), `created_by`, `created_at` and `updated_at`.
  - Unique on (`bot_id`, `plugin_id`): one binding per bot and plugin in v1.
  - There is no per-tool `enabled_tools` in v1.
- **`runs.requester_id`** is an FK to `users`, `SET NULL`, nullable.
  - For hop 0 it is the author of the trigger message (`create_runs`).
  - Runs started by a bot reply copy their parent's value (`save_reply` / `_queued_run`). Routines set it to the member who set the routine up.
  - Backfill: `requester_id` = the trigger message's `author_id` where `hop = 0` and `author_type = 'user'`.
- **`oauth_flows`** holds `id`, `org_id`, `user_id`, `state_hash` (sha256 hex, unique), `code_verifier_encrypted` (vault box), `connector_id`, `owner_kind`, `owner_bot_id`, `access`, `scopes` (JSON, as requested), `created_at` and `expires_at` (now + 10 min).
  - The callback consumes the row atomically: `DELETE … WHERE state_hash = ? AND user_id = ? RETURNING`, then it checks expiry.
- **Bindings backfill:** every existing bot gets a binding for each plugin id in `PLUGINS` (read through `Settings`), with `enabled = true`. This keeps today's "every allowlisted tool" behaviour.
  - Its `connection_id` is the bot's own active connection on that connector, otherwise the oldest active org-owned one, otherwise null. This freezes the 5.1 automatic choice.
- **New bots** (`bot_service.create_bot`, which needs the registry) get a binding for every loaded plugin whose `auth` is not `OAuth2Auth`. Demo is included, because its auth-less tools work without a key.

## Runtime rules

- **Toolset resolver** (`runtime/toolset.py`) runs in `call_model`, `prepare_call` and `execute_tool` from the database. Each call re-reads the bindings, so a tool unbound mid-run is refused on resume. For each enabled binding of the bot it decides as follows:
  - No `connection_id`: keep the plugin. Its tools that need an account fail with "connect it first".
  - A `connection_id` that isn't usable in this run: drop the whole plugin.
  - A tool whose `spec.scopes` aren't all among the connection's granted scopes: drop that tool.
- **A connection is usable** when `status == "active"` and one of these holds:
  - **member-owned:** `run.requester_id == owner_user_id` **and** the thread is a DM with `thread.created_by == owner_user_id` and `thread.bot_id == run.bot_id`;
  - **bot-owned:** `owner_bot_id == run.bot_id`;
  - **org-owned:** always.

  Test cases to cover:

  | Case | Usable? |
  |---|---|
  | Member connection in the owner's own DM | yes |
  | Member connection in someone else's DM | no |
  | Member connection in a group | no |
  | Bot-owned connection | yes |
  | `needs_reconnect` | no |
  | Plugin switched off | no |
  | Missing scope | that tool is dropped |
- **Pipeline:**
  - `prepare`/`execute` take a lookup with `get(name)` (the toolset), and `ExecuteDeps` gains `connection_ids: {plugin_id: uuid}`.
  - `ToolAccessProvider.open(…, connection_id)` replaces `connection_service.usable_for_run`.
  - `record` stores `connection_id` on `tool_executions` and `approvals`, and appends ` · via=<plugin>:<label> (<ownerKind>)` to the trace.
- **Requester rule for approvals:** when `approval.connection_id` points at a member-owned connection, only `owner_user_id` may decide it. Anyone else gets **403**. Bot- and org-owned connections keep today's rule (members in the chat).
- **Refresh:**
  - **When:** in `ToolAccessProvider.open`, refresh if an OAuth2 connection's `access_expires_at` is under 60 s away.
  - **Who:** win the lease with `UPDATE connections SET refresh_lease_until = now()+15s WHERE id = ? AND (refresh_lease_until IS NULL OR refresh_lease_until < now())` and commit. A connection that loses polls and re-reads for up to 15 s. Two concurrent refreshes must produce one token request.
  - **The token call:** the winner calls the token endpoint (`grant_type=refresh_token`) with no transaction open, then saves through the vault. If the provider sends no new refresh token, keep the old one.
  - **Failure:** on `invalid_grant`, set `status = needs_reconnect` with a `status_reason`, clear the lease and write an audit line. The tool fails with "<label> needs reconnecting (Connect apps)."
- **Start:**
  - The state is `secrets.token_urlsafe(32)`, stored only as its hash.
  - PKCE: the verifier is `token_urlsafe(48)`; the challenge is S256 (base64url of its sha256, without padding).
  - The authorize URL carries `response_type=code`, `client_id`, `redirect_uri`, `scope` (space-joined `scope_sets[access]`), `state`, `code_challenge` and `code_challenge_method=S256`, plus the manifest's `extra_authorize_params`. For Google those are `access_type=offline`, `prompt=consent` and `include_granted_scopes=true`.
- **Finish:**
  - Consume the flow and re-check membership and owner permission.
  - Exchange the code: a form POST with `code`, `redirect_uri`, `client_id`, `client_secret` and `code_verifier`.
  - Store the granted scopes (the response's `scope`, falling back to the requested ones) and `access_expires_at`.
  - Get the identity from `OAuth2Auth.account(http)`, through an `AuthorisedHttp` that holds the new token and the plugin's egress. Without an account handler, use label = the plugin's name and ref = `"default"`.
  - Upsert by account (the same logic as `connect_api_key`) and audit it as created or reconnected.
- **Disconnect:**
  - Decrypt the token for revocation, revoke in the database (vault), and set `bot_tools.connection_id = NULL` for that connection. Commit.
  - Then POST `revoke_url` with `token=<refresh or access token>`. This is best effort and happens after the commit, so no transaction is held over the network.
- **Secrets:** tokens never go into responses, logs, run state or events. The vault box (`botdesk:connections:v1`) also encrypts the PKCE verifier.
- **HTTP:** the OAuth module's client uses an injectable transport, so tests can pass `httpx.MockTransport` or `FakeProviders` hosts.

## Backend checklist (deferred from 2026-11-15)

- [ ] Migration covering `bot_tools`, `runs.requester_id` and `oauth_flows`, plus both backfills; apply it to the dev DB.
- [x] Settings `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (SecretStr); add both to `apps/api/.env.example` and `deploy/.env.example`.
- [ ] `runtime/toolset.py` and its wiring into the graph, pipeline and `tool_access`; remove `usable_for_run`. Update `tests/test_connections.py`, whose 5.1 tests assume the automatic choice of connection.
- [ ] `requester_id` set in `create_runs` and `save_reply` (routines set their own).
- [ ] Default bindings for new bots.
- [ ] `GET`/`PUT /bots/{bot}/tools`, with the permission and audit rules above.
- [ ] Approval 403 for anyone but the owner on member-owned connections.
- [x] `services/oauth_flow.py`, the `oauth/start` route, the callback route, and `GET /connectors`.
- [x] Refresh with the lease, `needs_reconnect`, and revoke on disconnect.
- [ ] Tests, written first:
  - the resolver table;
  - the backfill keeps behaviour;
  - the approval 403;
  - start and callback: state mismatch, expiry and another user's state refused; PKCE verifier sent; tokens encrypted and never in responses or logs;
  - refresh on expiry, and a failed refresh setting `needs_reconnect`;
  - two concurrent refreshes making one token request;
  - disconnect revoking at the provider.
- [ ] Docs: `docs/backend/README.md`, `docs/ROADMAP.md`, `docs/PROGRESS.md`. The Google guide is already at [google-oauth.md](../self-hosting/google-oauth.md).
- [ ] Later, not v1:
  - a per-binding "use each requester's own connection" option. Today one binding means one member's account per bot;
  - per-tool toggles;
  - the `organization_plugins` off switch;
  - refresh after a 401;
  - tool definition hashes in run state;
  - ~~a `plugins/gmail` manifest stub (slice 6.1)~~: landed with 5.3 (connect only, no tools).

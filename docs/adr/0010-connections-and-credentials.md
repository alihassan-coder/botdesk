# 0010: Connections, credentials and which tools a bot gets

- Status: proposed
- Date: 2026-11-15
- Based on: [ADR 0002](0002-grok-bot-parity-and-plugin-platform.md) (plugins), [ADR 0004](0004-agent-runtime-and-safety.md) (policy, taint), [ADR 0006](0006-repo-structure-plugins-and-project.md) (SDK, allowlist), [ADR 0008](0008-free-and-open-source.md) (self-hosted only), [agents-and-plugins.md §10](../architecture/agents-and-plugins.md#10-plugins), the code as of 2026-11-15
- Build plan: [connections-gmail-mcp.md](../architecture/connections-gmail-mcp.md)

## Context

Today a plugin is code the server loads from the `PLUGINS` allowlist, and **every bot sees every allowlisted tool**. No plugin can hold an account: `ToolContext` has ids and a logger, nothing to call another app with. Gmail (ADR 0011) and remote MCP servers (ADR 0012) both need an account per person, bot or organization, stored safely, refreshed, revoked, and only usable by the runs that should use it.

Earlier docs sketched this with envelope encryption (`BOTDESK_ENCRYPTION_KEYS`, per-org data keys, KMS) and a `plugin_installations` table. Since then, model keys shipped with a simpler scheme (`core/secrets.py`: Fernet keyed from `SECRET_KEY` by HKDF, rotation with `SECRET_KEY_OLD` through `MultiFernet`), and ADR 0008 removed the hosted service those heavier designs were for.

The hard questions are not storage but **whose account a run may use** (a bot anyone can talk to must not become a way into one member's inbox) and **what a plugin's code ever touches** (it must never need a raw token).

## Decisions

### 1. Words

- A **plugin** is what gives bots tools (built-in Python package, or an MCP server an admin added). A **connector** is a plugin as listed on Connect apps. A **connection** is one authorised account on one connector. A **binding** says which bot may use which plugin, through which connection, with which tools. A run's **requester** is the member it acts for.
- There is **no "installation"** concept in v1. A built-in plugin is on for every organization of the server (the operator chose it); an MCP server belongs to the organization that added it. "Turned off for this organization" is a flag, not a lifecycle.
- The `Connection` dataclass in `services/provider_service.py` (a decrypted model key) is renamed (`ProviderAccess`) so the domain word has one meaning.

### 2. Data model

`connections` (one row per authorised account):

| Column | Notes |
|---|---|
| `id`, `org_id`, `created_at`, `updated_at`, `created_by` | `org_id` on every row, as everywhere |
| `connector_id` | the plugin id: `gmail`, or `mcp-<server id>` |
| `owner_kind` | `member` \| `bot` \| `org` |
| `owner_user_id` / `owner_bot_id` | exactly one set for `member` / `bot`; both null for `org` (check constraint) |
| `auth_type` | `oauth2` \| `api_key` |
| `account_label` | what people see: `ali@acme.dev`, "Linear (Acme workspace)" |
| `account_ref` | the provider's stable account id (Google's address or `sub`), for "already connected" checks |
| `encrypted_secret` | Fernet token of a JSON bundle (`access_token`, `refresh_token`, `token_type`, or `api_key` + header name). Nulled on disconnect |
| `scopes` | JSON list of scopes **granted** (from the token response, not what we asked for) |
| `access_expires_at` | when the access token expires; null for API keys |
| `status` | `active` \| `needs_reconnect` \| `revoked`, plus `status_reason` |
| `refresh_lease_until` | see §6 |
| `last_used_at`, `last_refreshed_at` | |

Unique: (`org_id`, `connector_id`, `owner_kind`, owner id, `account_ref`), so connecting the same account twice updates the row (and its tokens) instead of adding one.

`bot_tools` (**bindings**): `org_id`, `bot_id`, `plugin_id`, `connection_id` (null for a plugin that needs no account), `enabled_tools` (explicit JSON list of tool names), `settings` (JSON, validated against the plugin's bot settings model), `created_by`, `updated_at`. One binding per bot and plugin in v1 (so tool names stay unique per bot).

`oauth_flows` (short-lived, see §5) and `audit_log` (append-only, §9). `tool_executions` and `approval_requests` gain `connection_id`.

### 3. Who may do what

| | Member-owned | Bot-owned (the bot's own mailbox) | Org-owned (shared) |
|---|---|---|---|
| Create, reconnect | that member | owners/admins, or the bot's creator | owners/admins |
| See in lists | that member; owners/admins see that it exists (label, status), never its secret | every member | every member |
| Bind to a bot | that member only | owners/admins, or the bot's creator | owners/admins |
| **Used in a run** | **only when the run's requester is that member, and only in that member's DM with the bot** | any run of a bound bot | any run of a bound bot |
| Approve a call through it | **that member only** | members in the chat (as today) | members in the chat (as today) |
| Disconnect | that member, or owners/admins (for safety) | owners/admins, bot's creator | owners/admins |

- **Requester:** the author of the message that started the run's chain (the hop-0 message, ADR 0009), or the member who set up the trigger or routine that started it. Stored on the run (`runs.requester_id`, copied down the chain).
- Keeping member-owned connections to the owner's own DMs means a group chat never shows one member's inbox to the others. Groups use bot- or org-owned connections.

### 4. A run's toolset

A run no longer sees "every tool in the registry". At run start a **toolset resolver** builds the run's tools:

`tools = for each binding of the bot: the plugin's tools ∩ binding.enabled_tools ∩ tools the connection's granted scopes allow`, minus bindings whose connection is not usable in this run (§3), not `active`, or whose plugin is off for the organization; plus MCP tools from approved snapshots (ADR 0012).

- The resolver returns tool names with a hash of each definition. They are kept in the run's state; on resume after an approval the resolver runs again and a call whose tool vanished or changed is refused with a clear reason.
- **Migration:** the backfill gives every existing bot a binding for each built-in plugin that needs no account, with all its tools, so nothing changes on upgrade. New bots get the same defaults. A plugin added to `PLUGINS` later is not bound to anyone until someone turns it on.
- A bot shows a warning above ~30 tools (models choose worse with long tool lists).

### 5. OAuth: one flow module, the API owns the callback

- `OAuthFlow.start(connector, owner, access)` writes an `oauth_flows` row (hash of a random `state`, the PKCE verifier encrypted, requested scopes, org, user, owner target, expiry 10 min) and returns the provider's authorize URL. The web does a full-page redirect.
- The redirect URI is the **API's** public address: `{API_PUBLIC_URL}/api/v1/oauth/callback` (a new setting; the browser already calls the API directly and holds its session cookie, which is `SameSite=Lax` and so arrives on this top-level redirect). The callback checks the `state` is unused and unexpired and that the signed-in user started it, exchanges the code (with PKCE), reads the account identity, upserts the connection, and redirects to the web's `/apps/callback?result=…`. Errors never put provider text in the URL; they use a short code the web maps to a message.
- Provider specifics (endpoints, extra params like Google's `access_type=offline`, how to read the account) live in the plugin manifest's auth spec (§7), not in the flow module.

### 6. Credentials: encryption, refresh, revocation

- **Encryption:** reuse `SecretBox` with its own HKDF purpose (`botdesk:connections:v1`), so a model-key ciphertext can't be swapped into a connection row. Same `SECRET_KEY` / `SECRET_KEY_OLD` rotation; active OAuth connections re-encrypt themselves on their next refresh (hourly for Google). A `botdesk reencrypt` command re-saves the rest before `SECRET_KEY_OLD` is dropped.
- **Decrypt late, hold briefly:** only the **credential vault** (`services/credential_vault.py`) decrypts, only inside a tool call or a refresh, and only into an object that never prints its secret. Tokens never go into run state, checkpoints, run events, tool results, logs or API responses.
- **Refresh** happens inside the authorised HTTP client when the access token has under 60 s left, or once after a 401. A **lease** stops two runs refreshing the same connection at once (some providers rotate refresh tokens, and the loser of a race would save a dead one): `UPDATE connections SET refresh_lease_until = now() + 15 s WHERE id = … AND (refresh_lease_until IS NULL OR refresh_lease_until < now())`. The winner refreshes and saves; the others wait up to 15 s and re-read. No transaction stays open over the network call.
- `invalid_grant` (revoked by the user, expired Testing-mode token, password change) sets `needs_reconnect`. The tool call fails with "Ali's Gmail needs reconnecting (Connect apps)", the run goes on, and Connect apps shows a Reconnect button.
- **Disconnect** calls the provider's revocation endpoint when it has one (best effort), nulls `encrypted_secret`, sets `revoked`, and removes the connection from bindings. The row stays for audit. Deleting a bot deletes its bot-owned connections the same way; a member leaving the organization revokes their member-owned ones.

### 7. Plugin SDK: additive, manifest version 2

Version-1 manifests keep loading unchanged. New, all optional:

- `PluginManifest.auth`: `OAuth2Auth(provider, authorize_url, token_url, revoke_url, scope_sets={"read": (...), "full": (...)}, extra_authorize_params, account=<handler that returns label and ref>)` or `ApiKeyAuth(header, prefix)`. None = needs no account.
- `PluginManifest.egress`: the hosts the plugin may call (`("gmail.googleapis.com",)`). For an authenticated plugin this list is **enforced** (below), not just reviewed.
- `ToolSpec.scopes`: the scopes a tool needs; tools the connection lacks are not offered.
- `PluginManifest.settings_model` / `bot_settings_model`: Pydantic models; their JSON Schema drives the settings forms.
- `PluginManifest.triggers`: `TriggerSpec(name, title, poll=<handler>, interval_seconds, untrusted_payload=True)` (used by ADR 0011).
- `ToolContext` gains `http` (below), `connection` (`ConnectionInfo`: id, connector, account label, owner kind, granted scopes; **no secret**) and `settings` (the binding's validated settings). Defaults keep old plugins and tests working.

`MANIFEST_VERSION` becomes 2; `to_json()` adds `auth`, `egress`, per-tool `scopes`, `triggers` and the settings schemas, so consent screens and upgrade diffs show them.

### 8. What a tool gets: an authorised HTTP client, never a token

`ctx.http` is an SDK `Protocol` (`request(method, url, *, params, json, data, headers) → HttpResponse`), so the SDK still depends only on Pydantic. The API's implementation:

- adds the connection's credential to each request itself (the plugin never sees it), refreshing as in §6;
- allows only `https` URLs whose host is in the manifest's `egress`, and never follows redirects;
- goes through `GuardedTransport` (`core/url_guard.py`) with private addresses always refused;
- caps response size (default 10 MB) and time (the tool timeout), and strips `Authorization` from anything it logs;
- records `last_used_at`.

The SDK's `testing` module gets `FakeHttp`: a route table with canned responses, which also asserts that only manifest hosts are called. Plugin tests never need a token or a network.

### 9. Policy, approvals and audit

- The policy table and taint rules (ADR 0004) do not change. The decision trace gains the account: `… · via=gmail:ali@acme.dev (member) → ask`. Approval cards show "as ali@acme.dev".
- Calls through a member-owned connection can be decided **only by that member** (§3).
- **`credential` risk class** is for tool actions that change who can reach what: mail forwarding, filters that forward, delegates, sharing settings, creating keys, and any MCP tool an admin classes that way. It always asks, and saved rules can never allow it. **Creating, reconnecting, widening or binding a connection is never a tool**: only a person in the UI does it, so a bot cannot grant itself access, whatever an email tells it.
- `audit_log` (append-only; the app never updates or deletes rows) records connection created, scopes granted, reconnected, refresh failed, disconnected, bound, unbound, enabled tools changed, with actor, target and time. Each tool call's connection is on its `tool_executions` row.

## Trade-offs

- **Member connections only in DMs** is stricter than Grok Bot may be. It costs some convenience in groups, and buys a simple, explainable privacy rule. Revisit with per-binding "allow in groups" if people ask.
- **One `SECRET_KEY`-derived key, no per-org keys or KMS.** Losing the database alone leaks nothing; losing the database *and* `SECRET_KEY` leaks everything. That is the same bar as model keys, and right for self-hosting. A KMS backend can sit behind the vault later.
- **Explicit bindings** add a step ("turn Gmail on for this bot"), but a bot's tools become visible and small, which models and people both need.
- **The callback lives on the API**, so self-hosters must give the API a public HTTPS name for Google (ADR 0011). It avoids handing an authorization code through the web app.

## Alternatives rejected

- **Envelope encryption with `BOTDESK_ENCRYPTION_KEYS` and per-org data keys** (agents-and-plugins.md §10.3, high-level.md §9.5): more moving parts than a self-hosted app needs, and a second key scheme next to model keys.
- **Handing tools the access token** (`ctx.token`): any plugin bug or log line could leak it, and egress could not be enforced. Built-in plugins call REST APIs with `ctx.http`; Google's client libraries (which want a raw credential) are not used.
- **Keeping "every bot sees every tool"**: fine for one demo plugin, wrong for Gmail plus MCP servers (privacy, and model quality past ~30 tools).
- **A `plugin_installations` lifecycle (install → configure → upgrade)**: no third-party code is installed per organization in v1; the operator's allowlist plus an off switch covers built-ins, and MCP servers carry their own snapshot (ADR 0012).
- **Letting any member's connection serve any run of a bot they bound it to**: the confused-deputy hole, where Sara asks the bot to read Ali's inbox.
- **Web-hosted OAuth callback that forwards the code to the API**: one more hop carrying a live code, and the web server never calls the API today.

## Consequences

- New settings: `API_PUBLIC_URL`; `ALLOW_PRIVATE_MCP_URLS` (ADR 0012).
- New tables: `connections`, `bot_tools`, `oauth_flows`, `audit_log`; new columns: `runs.requester_id`, `tool_executions.connection_id`, `approval_requests.connection_id`.
- `ToolRegistry` stays the startup catalogue of built-in code; the per-run toolset resolver sits between it and the pipeline.
- GLOSSARY gains **Binding** and **Requester**, and sharpens **Plugin**, **Connector** and **Connection**.

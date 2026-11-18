# 0016: MCP sign-in and tool review, as built

- Status: proposed (built in slices 7.3 and 7.4 on 2026-11-18; needs the owner's OK)
- Date: 2026-11-18
- Changes: [ADR 0012](0012-mcp-servers.md) §3 (the SDK's `OAuthClientProvider` does the protocol), §4 (the drift check at run start) and §7 (`start_oauth` in `mcp/client.py`)

## Context

ADR 0012 planned MCP sign-in through the `mcp` SDK's `OAuthClientProvider` with a vault-backed `TokenStorage`, and a drift check at run start every 5 minutes. Building 7.3 and 7.4 showed both are a poor fit for what BotDesk already has:

- The SDK's provider makes its discovery, registration and token requests through the HTTP client it is given. Ours is locked to the MCP server's origin (`mcp/_guard.py`), and authorization servers are almost always on another origin. Opening that lock for OAuth would weaken the guard for every MCP call.
- Slice 5.3 already has what the provider would duplicate: `oauth_flows` (hashed state, sealed PKCE verifier, single use, bound to the member), the one callback route, the vault, and the refresh lease with backoff and `needs_reconnect`. A second token store and refresh path would be two ways to get the same thing wrong.
- Slice 7.2 shipped a stricter drift check than §4: every call lists the tools again and compares the hash before it runs.

## Decisions

### 1. Sign-in uses BotDesk's own OAuth flow, not the SDK's provider

- `mcp/oauth.py` (no database) does the protocol: Protected Resource Metadata (RFC 9728, from the 401's `resource_metadata` or the well-known addresses), authorization-server metadata (RFC 8414 / OpenID, in the MCP spec's order, `issuer` must match), PKCE S256 required, `resource` (RFC 8707) on every authorization, token and refresh request, `iss` (RFC 9207) checked on the callback.
- Client registration in the spec's order: the client the admin pasted; a **Client ID Metadata Document** at `{API_PUBLIC_URL}/api/v1/oauth/client-metadata/{server id}.json` when the authorization server advertises `client_id_metadata_document_supported` and `API_PUBLIC_URL` is public https; else dynamic registration (RFC 7591).
- Every sign-in address (metadata, registration, token, revocation, and the authorize page the browser is sent to) goes through the same SSRF rules as MCP servers: https, no user info, public addresses unless `ALLOW_PRIVATE_MCP_URLS`, the checked IP pinned, no redirects, answers capped at 256 KB.
- The state, PKCE verifier and callback are the shared `oauth_flows` + `/api/v1/oauth/callback` of ADR 0010 §5. The tokens are a `connections` row (`connector_id` = the server's plugin id), sealed by the vault and refreshed with ADR 0010 §6's lease. The SDK client gets the access token as a header, as it does a header key.
- Removing the server or disconnecting the sign-in revokes the token at the authorization server (RFC 7009) after the commit, best effort.
- A 403 `insufficient_scope` fails the call with "needs more access", marks the sign-in `needs_reconnect` and adds the scopes the server named, so Reconnect asks for them (ADR 0012 §3's rule, unchanged).
- `McpServerConfig.auth` stays as a seam; `mcp/client.py` gets no `start_oauth`.

### 2. One sign-in per server, the organization's, for now

ADR 0012 §3 lets MCP sign-ins be member-, bot- or org-owned. v1 builds the organization's only: an owner or admin signs in once for the server, every member sees it, and ADR 0010 §3's org-owned rules apply. So switching a server that uses the organization's sign-in **or header key** on or off for a bot takes an owner or admin (binding an org-owned account), not any member as for keyless servers. Member- and bot-owned sign-ins (a member's own account, only in their DMs) are left for later; they need the toolset resolver to pick the binding's connection for an MCP server and a per-owner sign-in route.

### 3. Nothing is offered before the first review; drift is checked on every call

- A new server's tools (and a signed-in server's first listing) are `pending`: no bot is offered any of them until an admin approves them on Review tools, as ADR 0012 §4 says. Servers saved before 7.4 keep their tools as they were trusted.
- The drift check runs **before every call** (list, compare the hash, then call), not at run start every 5 minutes. A changed tool fails the call, is recorded as `changed` with what was approved (`previous`), and stops being offered until re-approved; new tools wait as `pending`; removed ones show as `removed` until the next review. Refresh records the same and never trusts anything by itself. The trade-off is one `tools/list` per call instead of one per 5 minutes per server; the gain is that a tool can't change between the check and the call by more than one round trip, and no stream or schedule is needed.

## Trade-offs

- More of the OAuth protocol is our own code than ADR 0012 hoped. It is small (about 300 lines), pure apart from its HTTP client, and tested against a fake authorization server, including the refusals.
- Org-owned only means a team can't yet let each member use their own Linear or GitHub account through MCP.
- An extra `tools/list` per MCP call.

## Not done

- Member- and bot-owned MCP sign-ins (§2).
- A drift check that notices changes when no one calls the tool or presses Refresh (a scheduled re-list on the job queue would do it).
- Tested only against the SDK's own server and a fake authorization server, not a real provider.

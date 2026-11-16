# 0012: Remote MCP servers

- Status: accepted (owner decisions 2026-11-15 in [connections-gmail-mcp.md](../architecture/connections-gmail-mcp.md#owner-decisions-2026-11-15))
- Date: 2026-11-15
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md), [ADR 0006](0006-repo-structure-plugins-and-project.md) §4 (third-party plugins are MCP servers; every MCP tool starts as `external-send`; hash-pinned tool lists), [ADR 0010](0010-connections-and-credentials.md), [agents-and-plugins.md §10.5](../architecture/agents-and-plugins.md#105-mcp-servers-the-rules); sources at the end
- Build plan: [connections-gmail-mcp.md](../architecture/connections-gmail-mcp.md)

## Context

MCP is how anyone else adds tools to BotDesk in v1: they run a server, BotDesk never runs their code. An MCP server is outside text all the way down: its tool descriptions are read by the model (an injection path), its results are written by someone else, its annotations ("read only") are self-reported, and it can change its tool list after an admin trusted it.

The current spec is **2026-07-28**. It made Streamable HTTP stateless (no `Mcp-Session-Id`, no GET stream), replaced the `initialize` handshake with per-request `_meta` and an optional `server/discover`, and moved server-to-client requests (sampling, elicitation) into `input_required` results. Most servers in the wild still speak the handshake versions (2025-03-26 to 2025-11-25). The old HTTP+SSE transport (2024-11-05) is deprecated.

The official Python SDK `mcp` is at 2.x (MIT). Its client speaks 2026-07-28 and falls back to the handshake versions automatically, takes a caller-built HTTP client, and has an OAuth client (`OAuthClientProvider` with a pluggable `TokenStorage`). It is built on **`httpx2`** (BSD-3, the Pydantic-maintained continuation of httpx), not on `httpx`, which BotDesk uses today.

## Decisions

### 1. Remote servers over Streamable HTTP only

- Supported: Streamable HTTP, both the 2026-07-28 shape and the handshake versions, through the SDK's automatic mode.
- Not supported: the deprecated HTTP+SSE transport, and **stdio** (that would run a third party's program inside the API; local servers belong in a bot's computer later, tier T4).
- **The address goes through the SSRF guard**: `check_base_url` when it is saved, and every request through a guarded transport that pins the checked IP, with private addresses refused unless `ALLOW_PRIVATE_MCP_URLS=true` (its own switch, separate from model servers). The SDK only follows same-origin 307/308 redirects and http→https on the same host; that stays inside the guard.

### 2. An MCP server is an organization's plugin

- **Owners and admins** add a server: name, URL, auth. It gets a plugin id `mcp-<short id>`, appears on Connect apps next to built-in connectors, and is private to that organization.
- Its tools are named `mcp-<short id>.<local name>`. The local name is the server's tool name lowered to `[a-z0-9_]`, cut so the model-side name (`mcp-<id>__<name>`) fits 64 characters, with a short hash suffix on collision. The snapshot keeps the mapping to the server's real name. No server can name a tool that lands in another plugin's space.
- Bots get its tools through **bindings**, exactly like a built-in plugin (ADR 0010 §4).

### 3. Auth: none, a header key, or OAuth 2.1

- **None.** No connection; the binding has `connection_id = null`.
- **API key in a header** (header name + value, e.g. `Authorization: Bearer …` or `X-API-Key`): an org-owned `api_key` connection, created by an admin with the server. Encrypted in `connections` like everything else (ADR 0010 §6).
- **OAuth 2.1** as the MCP authorization spec describes: discovery through Protected Resource Metadata (RFC 9728), authorization-server metadata (RFC 8414 or OpenID discovery), PKCE, the `resource` parameter (RFC 8707) set to the server's canonical URL, and the `iss` check (RFC 9207). Client registration, in the spec's order of preference: **pre-registered** client id/secret pasted by the admin; **Client ID Metadata Document** served by the API at `{API_PUBLIC_URL}/api/v1/oauth/client-metadata/{server id}.json` when that address is public HTTPS; **dynamic registration** as the fallback the spec keeps for older servers. Connections may be member-, bot- or org-owned, with ADR 0010's rules (a member's Linear account is used only in that member's DMs).
- The SDK's `OAuthClientProvider` does the protocol; BotDesk gives it a `TokenStorage` backed by the credential vault, and a redirect step that is our own callback route (ADR 0010 §5). Tokens are only ever sent to the server they were issued for; BotDesk never passes a person's other tokens through.
- A 403 `insufficient_scope` during a run is not fixed inside the run: the call fails with "needs more access", the connection shows Reconnect with the extra scopes, and a person does it.

### 4. Tool snapshot, hash pinning, re-approval

- On add (and on Refresh), BotDesk calls `tools/list` (all pages; at most 200 tools; each schema at most 64 KB) and stores a **tool snapshot**: per tool the server name, local name, title, description, input schema, output schema, annotations and a **hash** (SHA-256 of the canonical JSON of name, title, description, input and output schema).
- The admin **reviews and approves** the snapshot: sees each tool's description and arguments, picks which tools are available, and may change each tool's risk. Nothing is offered to a bot before this.
- **Drift check:** at run start, if the server's list was last checked more than 5 minutes ago (or the server's `ttlMs` has passed), BotDesk lists again and compares hashes. A **changed** tool is paused (not offered to bots) until an admin approves it again; a **new** tool waits unapproved; a **removed** tool disappears. The admin sees a diff (description and schema before/after). A paused run that resumes into a changed tool is refused (ADR 0010 §4). Listing failures keep the last approved snapshot and mark the server "unreachable".
- `notifications/tools/list_changed` and `subscriptions/listen` are not used in v1; the check above is enough and needs no long-lived stream.

### 5. Risk: we decide, starting at `external-send`

- Every MCP tool starts as **`external-send`, egress `open`, untrusted output**. Annotations (`readOnlyHint`, `destructiveHint` …) are shown to the admin as the server's claims and never set the risk (the spec says clients must treat them as untrusted).
- Admins may set any risk class per tool. Lowering below `external-send` is an explicit, audited choice with a warning ("this server will see the arguments; if it can reach the internet, this is still a way out").
- Egress stays `open` for every MCP tool, and every result taints the run. So in practice: the **first** MCP call of an untainted run follows the admin's risk; after any MCP result, every MCP call above `write-internal` asks. That is the honest consequence of "output is untrusted", and the UI says so.
- Tools are not idempotent unless the admin marks them so (a crash mid-call goes to `needs_attention`, ADR 0004 §2).

### 6. Calls: limits and how results reach the model

- Timeouts: connect 10 s; a call 60 s by default, settable per server up to 300 s. Closing the response stream is the cancellation (2026-07-28).
- Result handling: `structuredContent` if present, else the text parts; images and audio are replaced by "[image omitted]"; `resource_link`s are shown as text and never fetched; embedded resources contribute their text. Results are cut at 256 KB of text (with a note). `isError: true` becomes a failed tool call whose text the model still sees, tainted.
- `input_required` results (elicitation, sampling, roots) are refused in v1 with a clear error. **Sampling is never allowed**: a server must not spend the organization's model key.
- `x-mcp-header` mirroring and the other per-request headers are the SDK's job; tools whose `x-mcp-header` annotations break the spec's rules are dropped at listing, as the spec requires.

### 7. Library: the official `mcp` SDK, behind our own seam

- `mcp` 2.x (MIT) is the client, wrapped in `apps/api/src/mcp/client.py` with three operations: `list_tools(server)`, `call_tool(server, name, args)`, `start_oauth(server, owner)`. Nothing else in the app imports `mcp`.
- It brings `httpx2` (BSD-3). The SSRF guard (`PinnedNetworkBackend` / `GuardedTransport`) is ported to `httpx2`/`httpcore2` for MCP calls. **The first build step is a one-day spike** to prove the guard plugs into `httpx2` the way it plugs into httpx; if it can't, the fallback is to run the SDK's transport through an `httpx2` custom transport that delegates to our existing guarded `httpx` transport.
- In the registry, an MCP server's tools are `RegisteredTool`s with `source="mcp"` built from the approved snapshot, with one generic handler that calls `McpClient.call_tool`. The policy, approvals, taint and `tool_executions` see no difference from a built-in tool.

## Trade-offs

- **`external-send` by default means many approval cards** for MCP tools. That is ADR 0006's decision; per-tool admin overrides and saved rules (later) are the relief.
- **A second HTTP stack (`httpx2`)** in the API, until httpx and httpx2 converge or we move everything to httpx2.
- **Drift checks at run start** add up to one `tools/list` round trip every 5 minutes per server. Cheap, and simpler than a listening stream.
- **No HTTP+SSE**: a few old servers won't connect. They are deprecated, and supporting them needs a separate, unguarded code path in the SDK.

## Alternatives rejected

- **Deriving risk from annotations** (high-level.md §8.6): annotations are the server's own claims.
- **`langchain[mcp]` / `langchain-mcp-adapters`**: they turn MCP tools straight into LangChain tools, hiding exactly the list → snapshot → approve → call steps BotDesk must control; the adapters package is no longer maintained.
- **Our own MCP client** on httpx: 2026-07-28 alone is small, but handshake-era servers (most of them today), OAuth discovery, CIMD and `iss` checks are a lot to get right; the official SDK is MIT and maintained.
- **FastMCP's client**: compatible (Apache-2.0) but one more layer over the same SDK.
- **stdio servers in the API process**: running third-party code on the server, the thing ADR 0006 rules out.
- **Members adding MCP servers**: a server's descriptions go into the model's prompt for every bot that binds it; adding one is an admin decision.

## Sources

- MCP versioning (current 2026-07-28): https://modelcontextprotocol.io/specification/versioning
- Streamable HTTP (2026-07-28 changes, HTTP+SSE deprecated): https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- Authorization (RFC 9728, 8707, 9207, CIMD, DCR deprecated): https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- Tools (annotations untrusted, results, `input_required`, naming): https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- Python SDK `mcp` 2.3.0, MIT: https://pypi.org/project/mcp/ ; transports (`streamable_http_client(url, http_client=…)`, redirect rules): https://py.sdk.modelcontextprotocol.io/client/transports/ ; OAuth (`OAuthClientProvider`, `TokenStorage`): https://py.sdk.modelcontextprotocol.io/client/oauth-clients/ ; protocol versions: https://py.sdk.modelcontextprotocol.io/protocol-versions/
- `httpx2` (BSD-3): https://pypi.org/project/httpx2/

## Spike result (2026-11-16)

Slice 7.1 checked §7 against the real packages; the assumption **held**, no change of decision.

- `mcp` **2.3.0** (MIT) is current on PyPI. It depends on `httpx2` 2.16.0 / `httpcore2` (BSD-3), `mcp-types` (MIT), `sse-starlette` (BSD-3), `PyJWT` (MIT), `truststore` (MIT): all allowed.
- The guard ports to `httpx2`/`httpcore2` as is: same `AsyncNetworkBackend` and `AsyncConnectionPool(network_backend=…)` shape, so `src/mcp/_guard.py` is the httpx guard with three additions for MCP: requests are locked to the server's origin, https only, and a response size cap. The fallback (delegating to the httpx transport) isn't needed. `safe_addresses` stays shared with model servers.
- `streamable_http_client(url, http_client=…)` takes our guarded `httpx2.AsyncClient`; the SDK follows only same-origin redirects itself, and our transport refuses any other origin regardless.
- `Client(mode="auto")` probes `server/discover` (2026-07-28) and falls back to `initialize` (tested against a server that 404s `server/discover`).
- `input_required` is refused with `input_required_max_rounds=0` and no sampling, elicitation or roots callbacks.
- Interface as built: `list_tools(server, *, network)`, `call_tool(server, name, args, *, network)` in `src/mcp/client.py`; `server` is `McpServerConfig` (URL, header auth, timeouts, byte cap, and `auth: httpx2.Auth | None` as the seam for 7.3's `OAuthClientProvider`). `start_oauth` is left to 7.3.

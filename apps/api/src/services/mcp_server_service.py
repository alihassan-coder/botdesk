"""MCP servers (ADR 0012, slices 7.2-7.4): an organization's remote MCP servers and their tools as bot tools.

    server, sign_in_url = await add(db, runtime, actor, McpServerIn(...))  # connects, lists, snapshots
    await refresh(db, runtime, actor, server_id)               # lists again; changes wait for review
    await review(db, actor, server_id, McpToolsReviewIn(...))  # an admin approves, turns off, sets risk
    url = await start_sign_in(db, runtime, actor, server_id)   # OAuth: (re)connect the org's sign-in
    registry = await org_registry(db, registry, org_id, runtime)  # the registry + this org's servers

Each server is the plugin `mcp-<short id>`, built from its tool snapshot (never from what the
server says now), offering only the tools an admin approved as they are and left on. Their risk is
`external-send` unless an admin chose another on the review screen (audited); egress is open and
their output untrusted whatever the server's annotations claim, so results taint the run.

Before each call the server's list is read again and the tool's hash compared with the snapshot:
a changed (or vanished) tool is refused, and the change is recorded on the server so Connect apps
shows "Tools changed" until an admin approves it in the review. Refresh records changes the same
way; it never trusts them by itself.

**OAuth** (slice 7.3, ADR 0016): a server that answers 401 (or that the admin says uses sign-in)
is discovered (`mcp/oauth.py`). The client is the one the admin pasted, else a Client ID Metadata
Document the API serves (`client_metadata`), else a dynamic registration. The sign-in goes
through the shared `oauth_flows` + `/api/v1/oauth/callback` (5.3). The tokens are the
organization's connection (`connector_id` = the plugin id), sealed by the vault, refreshed with
the same lease as Google's; a refused refresh (or a 401 with a token) leaves it `needs_reconnect`
and the server shows Reconnect. A 403 `insufficient_scope` does the same with the extra scopes
added, so Reconnect asks for them. Removing the server or disconnecting the sign-in revokes the
token at the authorization server too (RFC 7009, best effort). Tokens go only to the server and
authorization server they belong to.

Only owners and admins add, refresh, review, sign in or remove servers, and switch a server that
uses the organization's key or sign-in on or off for a bot (ADR 0010 §3: binding an org-owned
account); every member may see them (no secrets). Callers own the transaction, except
`finish_sign_in`, which commits.
"""

import json
import logging
import secrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx
from botdesk_plugin_sdk import (
    RISK_CLASSES,
    NotDone,
    PluginError,
    PluginManifest,
    ToolContext,
    ToolSpec,
    validate_manifest,
)
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core import url_guard
from src.core.database import utcnow
from src.core.errors import AppError, BadRequest, Conflict, Forbidden, NotFound
from src.core.secrets import SecretUnreadable
from src.core.url_guard import GuardedTransport, UnsafeUrl, safe_addresses
from src.mcp import client as mcp
from src.mcp import oauth as mcp_oauth
from src.mcp.client import (
    MAX_RESULT_TEXT,
    McpAuthRequired,
    McpClientError,
    McpInsufficientScope,
    McpNetwork,
    McpProtocolError,
    McpRefused,
    McpServerConfig,
    McpUnsafeUrl,
)
from src.mcp.oauth import McpSignInError
from src.mcp.snapshot import approve, normalized, offered, review_diff, snapshot, snapshot_hash, tool_hash
from src.models import AuditEntry, BotTool, Connection, McpServer, User
from src.plugins.registry import ToolRegistry
from src.schemas.mcp_server import McpServerIn, McpToolsReviewIn
from src.services import connection_service, organization_service
from src.services.connection_service import Actor, Owner
from src.services.credential_vault import CredentialVault
from src.services.oauth_flow import ConsumedFlow, FlowFailed, OAuth, TokenRefused, Tokens, read_tokens

logger = logging.getLogger(__name__)

PLUGIN_PREFIX = "mcp-"
CALL_TIMEOUT_SECONDS = 60.0  # the whole call (re-check + call); the tool pipeline enforces it
MAX_DESCRIPTION = 4000  # what the model reads of a tool's description
OAUTH_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
NOT_FOUND = "This MCP server doesn't exist."
ADMINS_ONLY = "Only owners and admins can add, refresh or remove MCP servers."
CHANGED = "This tool changed on the server; an admin must review it in Connect apps before bots use it again."
STALE_REVIEW = "The server's tools changed again since you opened the review. Look at them again."
UNKNOWN_TOOL = "This server has no tool called {name}."
KEY_REFUSED = "The server refused that key. Check the header name and value."
NOT_SIGN_IN = "This MCP server doesn't use sign-in."
SIGN_IN_UNAVAILABLE = "Signing in to MCP servers isn't available on this server."
UNSAFE_SIGN_IN = "This MCP server's sign-in uses an address BotDesk won't connect to (it must be public https)."
PRIVATE_SIGN_IN = (
    "This MCP server's sign-in is on a private network, which this server doesn't allow. "
    "Self-hosting? Set ALLOW_PRIVATE_MCP_URLS=true."
)
RECONNECT = "{name} needs signing in again: an owner or admin can reconnect it in Connect apps."
MORE_ACCESS = (
    "{name} needs more access than it was given ({scopes}): an owner or admin can reconnect it in "
    "Connect apps to grant it."
)
ADMINS_BIND = "Only owners and admins can switch {name} on or off for a bot: it uses the organization's {what}."
CLIENT_METADATA_PATH = "/api/v1/oauth/client-metadata/{server_id}.json"
NO_CLIENT_METADATA = "There's no such client."


class McpNeedsSignIn(McpClientError):
    """The server's OAuth sign-in is missing or no longer works: an admin must reconnect it."""

    status_code = 409


@dataclass(frozen=True)
class McpRuntime:
    """What talking to MCP servers needs: the vault (header keys, OAuth tokens), where we may
    connect (`ALLOW_PRIVATE_MCP_URLS`; tests swap in a network that reaches a local server) and,
    for OAuth servers, the shared OAuth service (redirect URI, flows, the refresh lease) and a
    sessionmaker (tokens are read and refreshed in their own short transactions; changed tools
    noticed during a call are recorded the same way). `oauth_transport` replaces the network for
    sign-in requests (tests: a fake authorization server)."""

    vault: CredentialVault
    network: McpNetwork
    oauth: OAuth | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    oauth_transport: httpx.AsyncBaseTransport | None = None

    def http(self) -> httpx.AsyncClient:
        """For discovery, registration and token requests: through the SSRF guard, no redirects."""
        transport = self.oauth_transport or GuardedTransport(
            allow_private=self.network.allow_private, resolve=self.network.resolve
        )
        return httpx.AsyncClient(
            transport=transport, follow_redirects=False, trust_env=False, timeout=OAUTH_HTTP_TIMEOUT
        )

    async def guard(self, url: str) -> str:
        """An address sign-in may call: https (http only on a test network), no user info, and
        public unless ALLOW_PRIVATE_MCP_URLS. The guarded transport checks again as it connects."""
        try:
            parts = httpx.URL(url.strip())
        except httpx.InvalidURL as error:
            raise McpSignInError(UNSAFE_SIGN_IN) from error
        schemes = ("https", "http") if self.network.allow_http else ("https",)
        if parts.scheme not in schemes or not parts.host or parts.userinfo:
            raise McpSignInError(UNSAFE_SIGN_IN)
        try:
            await safe_addresses(parts.host, allow_private=self.network.allow_private, resolve=self.network.resolve)
        except UnsafeUrl as error:
            raise McpSignInError(
                PRIVATE_SIGN_IN if error.message == url_guard.PRIVATE_NETWORK else UNSAFE_SIGN_IN
            ) from error
        return url.strip()


def is_mcp_plugin(plugin_id: str) -> bool:
    return plugin_id.startswith(PLUGIN_PREFIX)


# Reading


async def list_servers(db: AsyncSession, org_id: uuid.UUID) -> list[McpServer]:
    rows = await db.scalars(select(McpServer).where(McpServer.org_id == org_id).order_by(McpServer.created_at))
    return list(rows)


async def get_server(db: AsyncSession, org_id: uuid.UUID, server_id: uuid.UUID) -> McpServer:
    server = await db.scalar(select(McpServer).where(McpServer.org_id == org_id, McpServer.id == server_id))
    if server is None:
        raise NotFound(NOT_FOUND)
    return server


@dataclass(frozen=True)
class SignIn:
    """The organization's sign-in to one OAuth server: its connection's status and why."""

    status: str  # active | needs_reconnect | revoked
    reason: str | None = None


async def sign_in_states(db: AsyncSession, org_id: uuid.UUID) -> dict[str, SignIn]:
    """{plugin id: sign-in} of the organization's MCP sign-ins (`active`, `needs_reconnect`, `revoked`)."""
    rows = await db.execute(
        select(Connection.connector_id, Connection.status, Connection.status_reason).where(
            Connection.org_id == org_id,
            Connection.connector_id.startswith(PLUGIN_PREFIX),
            Connection.owner_kind == "org",
        )
    )
    states: dict[str, SignIn] = {}
    for connector_id, status, reason in rows:
        known = states.get(connector_id)
        if known is None or known.status != "active":  # the active one wins if there are several
            states[connector_id] = SignIn(status, reason)
    return states


def status_of(server: McpServer, sign_in: SignIn | None) -> str:
    """What Connect apps shows: an OAuth server without a working sign-in says so first."""
    if server.auth_kind == "oauth":
        if sign_in is None or sign_in.status == "revoked":
            return "needs_sign_in"
        if sign_in.status == "needs_reconnect":
            return "needs_reconnect"
    return "unreachable" if server.status == "unreachable" else "active"


@dataclass(frozen=True)
class ToolsTabEntry:
    """What a bot's Tools tab says about one MCP server besides its tools (slice 7.4's badge)."""

    plugin_id: str
    name: str
    description: str
    waiting: int  # changed or new tools no bot is offered until an admin reviews them
    problem: str | None  # why its tools may not work now (sign-in, unreachable)
    auth_kind: str  # none | header | oauth

    @property
    def org_account(self) -> bool:
        """It uses the organization's key or sign-in: owners and admins bind it (ADR 0010 §3)."""
        return self.auth_kind in ("header", "oauth")


_PROBLEMS = {
    "needs_sign_in": "Not signed in yet: an owner or admin signs in to it on Connect apps.",
    "needs_reconnect": "Needs signing in again: an owner or admin can reconnect it on Connect apps.",
    "unreachable": "Couldn't be reached the last time BotDesk checked.",
}


async def tools_tab(db: AsyncSession, org_id: uuid.UUID) -> dict[str, ToolsTabEntry]:
    """{plugin id: entry} for each of the organization's servers (two queries)."""
    states = await sign_in_states(db, org_id)
    entries: dict[str, ToolsTabEntry] = {}
    for server in await list_servers(db, org_id):
        tools = [normalized(entry) for entry in server.tools]
        entries[server.plugin_id] = ToolsTabEntry(
            plugin_id=server.plugin_id,
            name=server.name,
            description=_description(server),
            waiting=sum(1 for entry in tools if entry["state"] in ("changed", "pending")),
            problem=_PROBLEMS.get(status_of(server, states.get(server.plugin_id))),
            auth_kind=server.auth_kind,
        )
    return entries


def bind_check(entries: Mapping[str, ToolsTabEntry]) -> Callable[[Actor, str], None]:
    """The extra rule for switching an MCP server on or off for a bot: one that uses the
    organization's key or sign-in is an org-owned account, which only owners and admins bind."""

    def check(actor: Actor, plugin_id: str) -> None:
        entry = entries.get(plugin_id)
        if entry is not None and entry.org_account and not actor.is_admin:
            what = "sign-in" if entry.auth_kind == "oauth" else "key"
            raise Forbidden(ADMINS_BIND.format(name=entry.name, what=what))

    return check


async def org_registry(
    db: AsyncSession, registry: ToolRegistry, org_id: uuid.UUID, runtime: McpRuntime | None
) -> ToolRegistry:
    """`registry` with this organization's MCP servers added as plugins. Without a runtime (or
    servers) it is `registry` itself."""
    if runtime is None:
        return registry
    plugins: list[PluginManifest] = []
    for server in await list_servers(db, org_id):
        if not any(offered(entry) for entry in server.tools):
            continue  # nothing to offer; a plugin needs tools
        try:
            plugins.append(validate_manifest(manifest(server, runtime)))
        except PluginError as error:  # one odd snapshot must not break every bot's Tools
            logger.warning("MCP server %s skipped: %s", server.id, "; ".join(error.problems))
    return registry.extended(plugins) if plugins else registry


# Changing (owners and admins)


async def add(db: AsyncSession, runtime: McpRuntime, actor: Actor, data: McpServerIn) -> tuple[McpServer, str | None]:
    """Connect to the server (through the SSRF guard), list its tools and save the snapshot.
    Nothing is saved if the server can't be reached. A server that wants a sign-in (it answers
    401, or the admin said so) is saved waiting for it: the second value is where to sign in."""
    _require_admin(actor)
    server = McpServer(
        id=uuid.uuid4(),  # known before the flush: a metadata-document client id names it
        org_id=actor.org_id,
        short_id=secrets.token_hex(4),
        name=data.name.strip(),
        url=data.url.strip(),
        auth_kind="header" if data.api_key_header else "none",
        auth_header=data.api_key_header,
        created_by=actor.user_id,
        tools=[],
        tools_hash="",
    )
    if data.api_key_header and data.api_key_value is not None:
        secret = json.dumps({"header": data.api_key_header, "value": data.api_key_value.get_secret_value()})
        server.encrypted_auth = runtime.vault.seal(secret)
    challenge = ""
    if not data.sign_in:
        try:
            tools = await mcp.list_tools(_header_config(server, runtime), network=runtime.network)
        except McpAuthRequired as needs:
            if data.api_key_header:
                raise BadRequest(KEY_REFUSED) from needs
            challenge = needs.challenge
        else:
            _save_snapshot(server, tools)
            db.add(server)
            await db.flush()
            _audit(db, actor, "mcp_server.added", server)
            return server, None

    await _set_up_oauth(runtime, server, challenge, data.oauth_client_id, data.oauth_client_secret)
    db.add(server)
    await db.flush()
    _audit(db, actor, "mcp_server.added", server)
    return server, await start_sign_in(db, runtime, actor, server.id)


async def refresh(db: AsyncSession, runtime: McpRuntime, actor: Actor, server_id: uuid.UUID) -> McpServer:
    """List the tools again. Changed and new tools are recorded and wait for an admin's review
    (refreshing never trusts them by itself). A server that can't be reached keeps its last
    snapshot and is marked unreachable; one whose sign-in stopped working needs reconnecting."""
    _require_admin(actor)
    server = await get_server(db, actor.org_id, server_id)
    try:
        tools = await mcp.list_tools(await _config(server, runtime), network=runtime.network)
    except McpNeedsSignIn:
        return server  # Connect apps shows Reconnect from the connection's state
    except McpAuthRequired as needs:
        if server.auth_kind == "oauth":
            await _sign_in_refused(runtime, server.org_id, server.plugin_id)
            return server
        server.status, server.status_reason = "unreachable", KEY_REFUSED if server.auth_kind == "header" else str(needs)
        server.last_checked_at = utcnow()
        return server
    except McpInsufficientScope as more:
        if server.auth_kind == "oauth" and server.oauth:
            server.oauth, extra = _with_scopes(server.oauth, more.challenge)
            await _mark_more_access(db, server.org_id, server.plugin_id, server.name, extra)
            return server
        server.status, server.status_reason = "unreachable", str(more)
        server.last_checked_at = utcnow()
        return server
    except McpClientError as error:
        server.status, server.status_reason = "unreachable", str(error)
        server.last_checked_at = utcnow()
        return server
    _save_snapshot(server, tools)
    _audit(db, actor, "mcp_server.refreshed", server)
    return server


async def review(db: AsyncSession, actor: Actor, server_id: uuid.UUID, data: McpToolsReviewIn) -> McpServer:
    """The review screen's save: each tool named in `data` is approved as it is now, offered to
    bots or not, at the risk chosen; tools not named stay as they were (a changed or new one keeps
    waiting). Removed tools leave the list. `tools_hash` must be the one the admin looked at.
    Every risk change is its own audit line (ADR 0012 §5)."""
    _require_admin(actor)
    server = await get_server(db, actor.org_id, server_id)
    if data.tools_hash != server.tools_hash:
        raise Conflict(STALE_REVIEW)
    entries = [normalized(entry) for entry in server.tools]
    names = {entry["name"] for entry in entries if entry["state"] != "removed"}
    choices = {choice.server_name: choice for choice in data.tools}
    for name in choices:
        if name not in names:
            raise BadRequest(UNKNOWN_TOOL.format(name=name))

    approved: list[str] = []
    kept: list[dict[str, Any]] = []
    for entry in entries:
        choice = choices.get(entry["name"])
        if entry["state"] == "removed":
            continue
        if choice is None:
            kept.append(entry)
            continue
        full_name = f"{server.plugin_id}.{entry['localName']}"
        if entry["state"] != "approved":
            approved.append(full_name)
        if choice.risk != entry["risk"]:
            _risk_changed(db, actor, server, full_name, entry["risk"], choice.risk)
        kept.append(approve(entry, enabled=choice.enabled, risk=choice.risk))
    server.tools = kept
    server.tools_hash = snapshot_hash(kept)
    db.add(
        AuditEntry(
            org_id=actor.org_id,
            actor_user_id=actor.user_id,
            action="mcp_server.tools_reviewed",
            target_kind="mcp_server",
            target_id=server.id,
            details={
                "name": server.name,
                "approved": approved,
                "offered": sorted(f"{server.plugin_id}.{e['localName']}" for e in kept if offered(e)),
            },
        )
    )
    return server


async def remove(db: AsyncSession, runtime: McpRuntime, actor: Actor, server_id: uuid.UUID) -> list["Revocation"]:
    """Remove the server, every bot's binding to it, and its sign-in's tokens. Returns the tokens
    to revoke at the authorization server once that is committed (`revoke_at_server`)."""
    _require_admin(actor)
    server = await get_server(db, actor.org_id, server_id)
    await db.execute(delete(BotTool).where(BotTool.org_id == actor.org_id, BotTool.plugin_id == server.plugin_id))
    signed_in = await db.scalars(
        select(Connection).where(Connection.org_id == actor.org_id, Connection.connector_id == server.plugin_id)
    )
    revocations: list[Revocation] = []
    for connection in signed_in:
        token = runtime.vault.revocation_token(connection) if connection.status != "revoked" else None
        if token is not None and (revocation := _revocation(server, runtime, token)) is not None:
            revocations.append(revocation)
        runtime.vault.revoke(connection, reason=f"The MCP server {server.name} was removed.")
    _audit(db, actor, "mcp_server.removed", server)
    await db.delete(server)
    return revocations


def _require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise Forbidden(ADMINS_ONLY)


def _save_snapshot(server: McpServer, tools: list[mcp.McpToolInfo]) -> None:
    """The listing compared with what an admin approved (`review_diff`): changed and new tools
    wait for the review; the first snapshot is approved as it is."""
    server.tools = review_diff(list(server.tools or []), snapshot(tools))
    server.tools_hash = snapshot_hash(server.tools)
    server.status, server.status_reason = "active", None
    server.last_checked_at = utcnow()


def _audit(db: AsyncSession, actor: Actor, action: str, server: McpServer) -> None:
    db.add(
        AuditEntry(
            org_id=actor.org_id,
            actor_user_id=actor.user_id,
            action=action,
            target_kind="mcp_server",
            target_id=server.id,
            details={"name": server.name, "url": server.url, "tools": len(server.tools)},
        )
    )


def _risk_changed(db: AsyncSession, actor: Actor, server: McpServer, tool: str, before: str, after: str) -> None:
    db.add(
        AuditEntry(
            org_id=actor.org_id,
            actor_user_id=actor.user_id,
            action="mcp_tool.risk_changed",
            target_kind="mcp_server",
            target_id=server.id,
            details={
                "server": server.name,
                "tool": tool,
                "from": before,
                "to": after,
                "lowered": RISK_CLASSES.index(after) < RISK_CLASSES.index(before),
            },
        )
    )


# OAuth sign-in (slice 7.3)


async def _set_up_oauth(
    runtime: McpRuntime, server: McpServer, challenge: str, client_id: str | None, client_secret: SecretStr | None
) -> None:
    """Discover how to sign in, and register BotDesk as a client unless the admin gave one."""
    if runtime.oauth is None:
        raise BadRequest(SIGN_IN_UNAVAILABLE)
    await runtime.guard(server.url)
    public_url = runtime.oauth.settings.api_public_url
    async with runtime.http() as http:
        try:
            found = await mcp_oauth.discover(http, server.url, mcp_oauth.parse_challenge(challenge), runtime.guard)
            secret = client_secret.get_secret_value() if client_secret else None
            # The MCP spec's order: pasted, then a metadata document, then dynamic registration.
            if client_id:
                kind = "pre-registered"
            elif found.get("metadataDocuments") and mcp_oauth.is_public_https(public_url):
                client_id, kind = client_metadata_url(public_url, server.id), "metadata-document"
            else:
                client_id, secret = await mcp_oauth.register(http, found, runtime.oauth.redirect_uri, runtime.guard)
                kind = "dynamic"
        except httpx.HTTPError as error:
            raise McpSignInError(f"Couldn't reach this MCP server's sign-in ({type(error).__name__}).") from error
    server.auth_kind, server.auth_header = "oauth", None
    server.oauth = {**found, "clientId": client_id, "client": kind}
    server.encrypted_auth = runtime.vault.seal(json.dumps({"clientSecret": secret})) if secret else None
    server.status, server.status_reason = "needs_sign_in", None


async def start_sign_in(db: AsyncSession, runtime: McpRuntime, actor: Actor, server_id: uuid.UUID) -> str:
    """The authorization server's sign-in page for the organization's sign-in to this server
    (first time, or Reconnect). One `oauth_flows` row, as for Google; the caller commits."""
    _require_admin(actor)
    server = await get_server(db, actor.org_id, server_id)
    if server.auth_kind != "oauth" or not server.oauth:
        raise BadRequest(NOT_SIGN_IN)
    if runtime.oauth is None:
        raise BadRequest(SIGN_IN_UNAVAILABLE)
    found = dict(server.oauth)
    scopes = [str(scope) for scope in found.get("scopes") or []]
    state, code_challenge = await runtime.oauth.begin_flow(db, actor, server.plugin_id, Owner("org"), "mcp", scopes)
    return mcp_oauth.authorize_url(
        found, str(found["clientId"]), runtime.oauth.redirect_uri, state=state, code_challenge=code_challenge
    )


async def finish_sign_in(
    db: AsyncSession, runtime: McpRuntime, flow: ConsumedFlow, code: str | None, iss: str | None, user: User
) -> Connection:
    """The callback, for an MCP server's flow (`OAuth.finish` consumed it and checked the state,
    the user and the expiry). Exchanges the code, lists the tools with the new token and saves
    the organization's connection. Commits; raises `FlowFailed`."""
    oauth = runtime.oauth
    short_id = flow.connector_id.removeprefix(PLUGIN_PREFIX)
    server = await db.scalar(select(McpServer).where(McpServer.org_id == flow.org_id, McpServer.short_id == short_id))
    if oauth is None or server is None or server.auth_kind != "oauth" or not server.oauth:
        raise FlowFailed("failed", "the MCP server is gone or no longer uses sign-in")
    found_role = await organization_service.org_and_role(db, org_id=flow.org_id, user_id=user.id)
    if found_role is None:
        raise FlowFailed("forbidden", "no longer a member")
    actor = Actor(org_id=flow.org_id, user_id=user.id, role=found_role[1])
    if not actor.is_admin:
        raise FlowFailed("forbidden", "no longer an owner or admin")
    if not code:
        raise FlowFailed("failed", "no code in the callback")
    found = dict(server.oauth)
    # RFC 9207: an `iss` that names another server is a mix-up; a missing one is refused when the
    # authorization server said it sends one.
    if (iss is not None and iss.rstrip("/") != found["issuer"]) or (iss is None and found.get("issParameter")):
        raise FlowFailed("failed", "the callback's issuer is missing or another one")
    server_id, plugin_id, name, url = server.id, server.plugin_id, server.name, server.url
    client_secret = _client_secret(server, runtime)
    await db.rollback()  # no transaction open while the servers are called

    try:
        verifier = runtime.vault.unseal(flow.code_verifier_encrypted)
    except SecretUnreadable as unreadable:
        raise FlowFailed("failed", "the verifier can't be read (SECRET_KEY changed?)") from unreadable
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": oauth.redirect_uri,
        "code_verifier": verifier,
    }
    try:
        async with runtime.http() as http:
            answer = await mcp_oauth.token_request(
                http, found, str(found["clientId"]), client_secret, form, runtime.guard
            )
        tokens = read_tokens(answer)
    except (TokenRefused, httpx.HTTPError, AppError, ValueError) as failed:
        raise FlowFailed("failed", f"the code exchange failed ({type(failed).__name__})") from failed
    listed: list[mcp.McpToolInfo] | None = None
    unreachable = ""
    try:
        bearer = {"Authorization": f"Bearer {tokens.access_token}"}
        listed = await mcp.list_tools(McpServerConfig(url=url, headers=bearer), network=runtime.network)
    except McpClientError as error:
        unreachable = str(error)

    scopes = tokens.scope.split() if tokens.scope else list(flow.scopes)
    try:
        connection = await connection_service.save_account(
            db,
            actor,
            plugin_id,
            Owner("org"),
            auth_type="oauth2",
            label=name,
            ref="oauth",
            scopes=scopes,
            save_secret=lambda row: _save_tokens(oauth, row, tokens),
            details={"server": name},
        )
    except AppError as conflict:
        raise FlowFailed("failed", conflict.message) from conflict
    row = await db.get(McpServer, server_id)
    if row is not None:
        if listed is not None:
            _save_snapshot(row, listed)
        else:
            row.status, row.status_reason, row.last_checked_at = "unreachable", unreachable, utcnow()
    await db.commit()
    logger.info("Signed in to the MCP server %s.", plugin_id)
    return connection


def _save_tokens(oauth: OAuth, row: Connection, tokens: Tokens) -> None:
    oauth.save_tokens(row, tokens)


def _client_secret(server: McpServer, runtime: McpRuntime) -> str | None:
    if server.auth_kind != "oauth" or not server.encrypted_auth:
        return None
    secret = json.loads(runtime.vault.unseal(server.encrypted_auth)).get("clientSecret")
    return str(secret) if secret else None


# Client ID Metadata Documents (slice 7.3)


def client_metadata_url(api_public_url: str, server_id: uuid.UUID) -> str:
    """The client id BotDesk uses with an authorization server that reads metadata documents:
    an https address of the API that serves the document (`client_metadata`)."""
    return api_public_url.rstrip("/") + CLIENT_METADATA_PATH.format(server_id=server_id)


async def client_metadata(db: AsyncSession, runtime: McpRuntime, file_name: str) -> dict[str, Any]:
    """The document at `…/oauth/client-metadata/<server id>.json`, for a server that signs in
    with it. Public (the authorization server fetches it) and holds nothing secret: BotDesk's
    name, the callback and the grants. Anything else is `NotFound`."""
    raw_id = file_name.removesuffix(".json")
    try:
        server_id = uuid.UUID(raw_id)
    except ValueError as error:
        raise NotFound(NO_CLIENT_METADATA) from error
    if runtime.oauth is None or file_name == raw_id:
        raise NotFound(NO_CLIENT_METADATA)
    server = await db.get(McpServer, server_id)
    client_id = client_metadata_url(runtime.oauth.settings.api_public_url, server_id)
    found = server.oauth if server is not None and server.auth_kind == "oauth" else None
    if not found or found.get("client") != "metadata-document" or found.get("clientId") != client_id:
        raise NotFound(NO_CLIENT_METADATA)
    return mcp_oauth.client_metadata_document(client_id, runtime.oauth.redirect_uri)


# Revoking at the authorization server (slice 7.3; ADR 0010 §6: best effort, after the commit)


@dataclass(frozen=True, repr=False)
class Revocation:
    """A token to revoke and where. Its repr hides the token and the client secret."""

    found: Mapping[str, Any]
    client_id: str
    client_secret: str | None
    token: SecretStr


def _revocation(server: McpServer, runtime: McpRuntime, token: SecretStr) -> Revocation | None:
    found = server.oauth if server.auth_kind == "oauth" else None
    if not found or not found.get("revocationEndpoint"):
        return None
    try:
        secret = _client_secret(server, runtime)
    except SecretUnreadable:
        secret = None
    return Revocation(dict(found), str(found["clientId"]), secret, token)


async def revocation_for(
    db: AsyncSession, runtime: McpRuntime, org_id: uuid.UUID, plugin_id: str, token: SecretStr
) -> Revocation | None:
    """For a disconnected MCP sign-in (Your connections): where its token is revoked, if anywhere."""
    short_id = plugin_id.removeprefix(PLUGIN_PREFIX)
    server = await db.scalar(select(McpServer).where(McpServer.org_id == org_id, McpServer.short_id == short_id))
    return _revocation(server, runtime, token) if server is not None else None


async def revoke_at_server(runtime: McpRuntime, revocations: list[Revocation]) -> None:
    """RFC 7009 for each; nothing it meets is raised, and no token reaches a log line."""
    for revocation in revocations:
        try:
            async with runtime.http() as http:
                said_yes = await mcp_oauth.revoke(
                    http,
                    revocation.found,
                    revocation.client_id,
                    revocation.client_secret,
                    revocation.token.get_secret_value(),
                    runtime.guard,
                )
        except (httpx.HTTPError, AppError) as failed:  # AppError: the guard, or a body over the cap
            logger.warning("Revoking an MCP sign-in failed (%s).", type(failed).__name__)
            continue
        if not said_yes:
            logger.warning("Revoking an MCP sign-in: the authorization server didn't confirm it.")


async def _oauth_headers(
    runtime: McpRuntime, org_id: uuid.UUID, plugin_id: str, name: str, found: Mapping[str, Any], sealed: str | None
) -> dict[str, str]:
    """The organization's access token for this server, refreshed first when it has under a
    minute left (one refresh at a time: the lease in `OAuth.refresh_with`)."""
    reconnect = RECONNECT.format(name=name)
    if runtime.oauth is None or runtime.sessionmaker is None:
        raise McpNeedsSignIn(reconnect)
    async with runtime.sessionmaker() as db:
        connection = await db.scalar(
            select(Connection).where(
                Connection.org_id == org_id,
                Connection.connector_id == plugin_id,
                Connection.owner_kind == "org",
                Connection.status == "active",
            )
        )
    if connection is None:
        raise McpNeedsSignIn(reconnect)
    client_secret = json.loads(runtime.vault.unseal(sealed)).get("clientSecret") if sealed else None

    async def renew(refresh_token: SecretStr) -> Tokens:
        form = {"grant_type": "refresh_token", "refresh_token": refresh_token.get_secret_value()}
        async with runtime.http() as http:
            answer = await mcp_oauth.token_request(
                http, found, str(found["clientId"]), client_secret, form, runtime.guard
            )
        return read_tokens(answer)

    connection = await runtime.oauth.refresh_with(runtime.sessionmaker, connection, plugin_id, reconnect, renew)
    if connection.status != "active":
        raise McpNeedsSignIn(reconnect)
    return runtime.vault.open(connection).auth_headers()


async def _sign_in_refused(runtime: McpRuntime, org_id: uuid.UUID, plugin_id: str) -> None:
    """The server answered 401 to a token we hold: someone has to sign in again."""
    if runtime.sessionmaker is None:
        return
    async with runtime.sessionmaker() as db:
        await db.execute(
            update(Connection)
            .where(
                Connection.org_id == org_id,
                Connection.connector_id == plugin_id,
                Connection.owner_kind == "org",
                Connection.status == "active",
            )
            .values(status="needs_reconnect", status_reason="The MCP server stopped accepting this sign-in.")
        )
        await db.commit()
    logger.warning("An MCP sign-in needs reconnecting (%s refused its token).", plugin_id)


def _with_scopes(oauth: Mapping[str, Any], challenge: str) -> tuple[dict[str, Any], list[str]]:
    """A 403 `insufficient_scope` names the scopes the call needs (MCP step-up authorization):
    the sign-in settings with them added, so Reconnect asks for them, and the ones that are new."""
    asked = mcp_oauth.safe_scopes((mcp_oauth.parse_challenge(challenge).scope or "").split())
    had = [str(scope) for scope in oauth.get("scopes") or []]
    extra = [scope for scope in asked if scope not in had]
    return {**oauth, "scopes": mcp_oauth.safe_scopes([*had, *asked])}, extra or asked


async def _mark_more_access(db: AsyncSession, org_id: uuid.UUID, plugin_id: str, name: str, scopes: list[str]) -> None:
    """The organization's sign-in needs reconnecting with more access (in `db`'s transaction)."""
    reason = MORE_ACCESS.format(name=name, scopes=", ".join(scopes) or "the server didn't say which")
    connection = await db.scalar(
        select(Connection).where(
            Connection.org_id == org_id,
            Connection.connector_id == plugin_id,
            Connection.owner_kind == "org",
            Connection.status == "active",
        )
    )
    if connection is None:
        return
    connection.status, connection.status_reason = "needs_reconnect", reason
    connection_service.audit_line(
        db,
        org_id,
        None,
        "connection.needs_reconnect",
        connection.id,
        {"connector": plugin_id, "reason": "insufficient_scope", "scopes": scopes},
    )


async def _needs_more_access(runtime: McpRuntime, ref: "_ServerRef", challenge: str) -> str:
    """A call met 403 `insufficient_scope`: record the extra scopes on the server and mark the
    sign-in for Reconnect, in its own transaction. Returns what the call fails with."""
    extra: list[str] = []
    if runtime.sessionmaker is not None:
        async with runtime.sessionmaker() as db:
            server = await db.get(McpServer, ref.id)
            if server is not None and server.oauth:
                server.oauth, extra = _with_scopes(server.oauth, challenge)
                await _mark_more_access(db, ref.org_id, ref.plugin_id, ref.name, extra)
                await db.commit()
    logger.warning("An MCP sign-in needs more access (%s answered insufficient_scope).", ref.plugin_id)
    return MORE_ACCESS.format(name=ref.name, scopes=", ".join(extra) or "the server didn't say which")


# The plugin


@dataclass(frozen=True)
class _ServerRef:
    """What a tool call needs of its server, read once when the toolset is built."""

    id: uuid.UUID
    org_id: uuid.UUID
    plugin_id: str
    name: str
    url: str
    auth_kind: str
    sealed: str | None
    oauth: Mapping[str, Any] | None


def _ref(server: McpServer) -> _ServerRef:
    return _ServerRef(
        id=server.id,
        org_id=server.org_id,
        plugin_id=server.plugin_id,
        name=server.name,
        url=server.url,
        auth_kind=server.auth_kind,
        sealed=server.encrypted_auth,
        oauth=dict(server.oauth) if server.oauth else None,
    )


async def _config(server: McpServer, runtime: McpRuntime) -> McpServerConfig:
    return await _config_for(_ref(server), runtime)


def _header_config(server: McpServer, runtime: McpRuntime) -> McpServerConfig:
    headers: dict[str, str] = {}
    if server.auth_kind == "header" and server.encrypted_auth:
        auth = json.loads(runtime.vault.unseal(server.encrypted_auth))
        headers[str(auth["header"])] = str(auth["value"])
    return McpServerConfig(url=server.url, headers=headers)


async def _config_for(ref: _ServerRef, runtime: McpRuntime) -> McpServerConfig:
    """How to reach the server now: its header key, or the organization's (fresh) access token."""
    headers: dict[str, str] = {}
    if ref.auth_kind == "header" and ref.sealed:
        auth = json.loads(runtime.vault.unseal(ref.sealed))
        headers[str(auth["header"])] = str(auth["value"])
    elif ref.auth_kind == "oauth" and ref.oauth:
        headers = await _oauth_headers(runtime, ref.org_id, ref.plugin_id, ref.name, ref.oauth, ref.sealed)
    return McpServerConfig(url=ref.url, headers=headers)


def manifest(server: McpServer, runtime: McpRuntime) -> PluginManifest:
    """The server as a plugin, from its snapshot: only the tools offered to bots."""
    ref = _ref(server)
    return PluginManifest(
        id=server.plugin_id,
        name=server.name,
        version="1",
        description=_description(server),
        tools=tuple(_tool(ref, entry, runtime) for entry in server.tools if offered(entry)),
    )


def _description(server: McpServer) -> str:
    return f"Tools from the MCP server at {server.url}."


def _tool(ref: _ServerRef, entry: Mapping[str, Any], runtime: McpRuntime) -> ToolSpec:
    remote_name, pinned = str(entry["name"]), str(entry["hash"])

    async def call(args: BaseModel, _ctx: ToolContext) -> dict[str, Any]:
        # BotDesk can't see an MCP call's requests, so whatever fails before the tool is called
        # says so (`NotDone`): the call then fails instead of stopping the run (ADR 0004 §2).
        try:
            config = await _config_for(ref, runtime)  # the key or token is read only now, inside the call
            current = await mcp.list_tools(config, network=runtime.network)
        except Exception as error:
            raise await _refused(runtime, ref, error) from error
        found = next((tool for tool in current if tool.name == remote_name), None)
        if found is None or tool_hash(found) != pinned:
            await _record_drift(runtime, ref.id, current)
            raise ToolChanged(CHANGED)
        try:
            result = await mcp.call_tool(config, remote_name, args.model_dump(mode="json"), network=runtime.network)
        except McpRefused as error:
            # Turned down before anything ran (unknown tool, bad arguments). Its message carries the
            # server's own words: give it to the model as (tainting) output; trying again is safe.
            return {"text": str(error)[:MAX_RESULT_TEXT], "isError": True}
        except McpProtocolError as error:
            # Any other MCP error, an answer that isn't MCP, or a request for input may come after
            # the tool did its thing: not `NotDone`, so the run stops for a person (ADR 0004 §2).
            raise AnswerUnusable(ANSWER_UNUSABLE) from error
        except (McpAuthRequired, McpInsufficientScope, McpUnsafeUrl) as error:
            # Refused before the tool ran: signing in (or more access) was needed, or the guard
            # wouldn't connect. Anything else (a timeout, a dropped connection) may have happened.
            raise await _refused(runtime, ref, error) from error
        answer: dict[str, Any] = {"text": result.text}
        if result.is_error:
            answer["isError"] = True  # the tool ran and failed: the model still reads why
        return answer

    entry = normalized(dict(entry))
    title = str(entry.get("title") or "").strip() or remote_name
    description = (str(entry.get("description") or "").strip() or title)[:MAX_DESCRIPTION]
    return ToolSpec(
        name=str(entry["localName"]),
        title=title[:200],
        description=description,
        args_model=_args_model(entry.get("inputSchema") or {"type": "object"}, f"mcp_{ref.id.hex}"),
        risk=entry["risk"],  # external-send unless an admin chose otherwise (audited)
        handler=call,
        egress="open",
        idempotent=False,
        untrusted_output=True,
    )


async def _refused(runtime: McpRuntime, ref: _ServerRef, error: Exception) -> NotDone:
    """An MCP call refused before its tool ran, as `NotDone` (the call fails, the run goes on).
    A sign-in the server turned down is marked for Reconnect; a 403 `insufficient_scope` records
    the scopes Reconnect must ask for (ADR 0012 §3: never fixed inside the run)."""
    if isinstance(error, McpAuthRequired) and ref.auth_kind == "oauth":
        await _sign_in_refused(runtime, ref.org_id, ref.plugin_id)
    if isinstance(error, McpInsufficientScope) and ref.auth_kind == "oauth" and ref.oauth:
        return NotDone(await _needs_more_access(runtime, ref, error.challenge))
    return NotDone(str(error) or type(error).__name__)


async def _record_drift(runtime: McpRuntime, server_id: uuid.UUID, tools: list[mcp.McpToolInfo]) -> None:
    """A call found the server's tools changed: record it, so Connect apps shows "Tools changed"."""
    if runtime.sessionmaker is None:
        return
    try:
        async with runtime.sessionmaker() as db:
            server = await db.get(McpServer, server_id)
            if server is not None:
                _save_snapshot(server, tools)
                await db.commit()
    except Exception as failed:  # the refusal is what matters to the run
        logger.warning("Couldn't record an MCP server's changed tools (%s).", type(failed).__name__)


ANSWER_UNUSABLE = "The MCP server's answer to this call couldn't be used, so it may or may not have run."


class AnswerUnusable(Exception):
    """The server answered a call with an error that doesn't say the tool didn't run. Its message
    is our own sentence, never the server's words (they would reach the needs-attention notice)."""


class ToolChanged(NotDone):
    """The tool's definition on the server isn't the one an admin trusted. It wasn't called."""


class _McpArgs(BaseModel):
    """Arguments for an MCP tool: passed through as sent (the server checks them against its
    schema); the model is shown the server's own schema."""

    model_config = ConfigDict(extra="allow")
    schema_: ClassVar[dict[str, Any]] = {"type": "object"}

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        copy: dict[str, Any] = json.loads(json.dumps(cls.schema_))
        return copy


def _args_model(schema: dict[str, Any], name: str) -> type[BaseModel]:
    return type(name, (_McpArgs,), {"schema_": schema, "__module__": __name__})

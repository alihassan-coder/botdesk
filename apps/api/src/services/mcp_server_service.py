"""MCP servers (ADR 0012, slice 7.2): an organization's remote MCP servers and their tools as bot tools.

    server = await add(db, runtime, actor, McpServerIn(...))   # connects, lists, snapshots
    await refresh(db, runtime, actor, server_id)               # snapshots again (re-trusts)
    registry = await org_registry(db, registry, org_id, runtime)  # the registry + this org's servers

Each server is the plugin `mcp-<short id>`, built from its tool snapshot (never from what the
server says now). Its tools are all `external-send` with open egress and untrusted output, whatever
the server's annotations claim: they ask under "Ask before acting", and their results taint the run.
Before each call the server's list is read again and the tool's hash compared with the snapshot;
a changed (or vanished) tool is refused until an admin refreshes the server.

Only owners and admins add, refresh or remove servers; every member may see them (no secrets).
Callers own the transaction.
"""

import json
import logging
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from botdesk_plugin_sdk import PluginError, PluginManifest, ToolContext, ToolSpec, validate_manifest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utcnow
from src.core.errors import Forbidden, NotFound
from src.mcp import client as mcp
from src.mcp.client import MAX_RESULT_TEXT, McpClientError, McpNetwork, McpProtocolError, McpServerConfig
from src.mcp.snapshot import snapshot, snapshot_hash, tool_hash
from src.models import AuditEntry, BotTool, McpServer
from src.plugins.registry import ToolRegistry
from src.schemas.mcp_server import McpServerIn
from src.services.connection_service import Actor
from src.services.credential_vault import CredentialVault

logger = logging.getLogger(__name__)

PLUGIN_PREFIX = "mcp-"
CALL_TIMEOUT_SECONDS = 60.0  # the whole call (re-check + call); the tool pipeline enforces it
MAX_DESCRIPTION = 4000  # what the model reads of a tool's description
NOT_FOUND = "This MCP server doesn't exist."
ADMINS_ONLY = "Only owners and admins can add, refresh or remove MCP servers."
CHANGED = "This tool changed on the server; an admin must refresh it."


@dataclass(frozen=True)
class McpRuntime:
    """What talking to MCP servers needs: the vault (header keys) and where we may connect
    (`ALLOW_PRIVATE_MCP_URLS`; tests swap in a network that reaches a local server)."""

    vault: CredentialVault
    network: McpNetwork


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


async def org_registry(
    db: AsyncSession, registry: ToolRegistry, org_id: uuid.UUID, runtime: McpRuntime | None
) -> ToolRegistry:
    """`registry` with this organization's MCP servers added as plugins. Without a runtime (or
    servers) it is `registry` itself."""
    if runtime is None:
        return registry
    plugins: list[PluginManifest] = []
    for server in await list_servers(db, org_id):
        if not server.tools:
            continue  # nothing to offer; a plugin needs tools
        try:
            plugins.append(validate_manifest(manifest(server, runtime)))
        except PluginError as error:  # one odd snapshot must not break every bot's Tools
            logger.warning("MCP server %s skipped: %s", server.id, "; ".join(error.problems))
    return registry.extended(plugins) if plugins else registry


# Changing (owners and admins)


async def add(db: AsyncSession, runtime: McpRuntime, actor: Actor, data: McpServerIn) -> McpServer:
    """Connect to the server (through the SSRF guard), list its tools and save the snapshot.
    Nothing is saved if the server can't be reached."""
    _require_admin(actor)
    server = McpServer(
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
    _save_snapshot(server, await mcp.list_tools(_config(server, runtime), network=runtime.network))
    db.add(server)
    await db.flush()
    _audit(db, actor, "mcp_server.added", server)
    return server


async def refresh(db: AsyncSession, runtime: McpRuntime, actor: Actor, server_id: uuid.UUID) -> McpServer:
    """List the tools again and trust what the server says now: changed tools are offered (and
    callable) again. A server that can't be reached keeps its last snapshot and is marked
    unreachable."""
    _require_admin(actor)
    server = await get_server(db, actor.org_id, server_id)
    try:
        tools = await mcp.list_tools(_config(server, runtime), network=runtime.network)
    except McpClientError as error:
        server.status, server.status_reason = "unreachable", str(error)
        server.last_checked_at = utcnow()
        return server
    _save_snapshot(server, tools)
    _audit(db, actor, "mcp_server.refreshed", server)
    return server


async def remove(db: AsyncSession, actor: Actor, server_id: uuid.UUID) -> None:
    """Remove the server and every bot's binding to it."""
    _require_admin(actor)
    server = await get_server(db, actor.org_id, server_id)
    await db.execute(delete(BotTool).where(BotTool.org_id == actor.org_id, BotTool.plugin_id == server.plugin_id))
    _audit(db, actor, "mcp_server.removed", server)
    await db.delete(server)


def _require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise Forbidden(ADMINS_ONLY)


def _save_snapshot(server: McpServer, tools: list[mcp.McpToolInfo]) -> None:
    server.tools = snapshot(tools)
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


# The plugin


def _config(server: McpServer, runtime: McpRuntime) -> McpServerConfig:
    return _config_for(server.url, server.encrypted_auth, runtime)


def manifest(server: McpServer, runtime: McpRuntime) -> PluginManifest:
    """The server as a plugin, from its snapshot."""
    return PluginManifest(
        id=server.plugin_id,
        name=server.name,
        version="1",
        description=f"Tools from the MCP server at {server.url}.",
        tools=tuple(_tool(server, entry, runtime) for entry in server.tools),
    )


def _tool(server: McpServer, entry: Mapping[str, Any], runtime: McpRuntime) -> ToolSpec:
    server_id, url, sealed = server.id, server.url, server.encrypted_auth
    remote_name, pinned = str(entry["name"]), str(entry["hash"])

    async def call(args: BaseModel, _ctx: ToolContext) -> dict[str, Any]:
        config = _config_for(url, sealed, runtime)  # the key is unsealed only now, inside the call
        current = await mcp.list_tools(config, network=runtime.network)
        found = next((tool for tool in current if tool.name == remote_name), None)
        if found is None or tool_hash(found) != pinned:
            raise ToolChanged(CHANGED)
        try:
            result = await mcp.call_tool(config, remote_name, args.model_dump(mode="json"), network=runtime.network)
        except McpProtocolError as error:
            # Its message carries the server's own words: give it to the model as (tainting) output.
            return {"text": str(error)[:MAX_RESULT_TEXT], "isError": True}
        answer: dict[str, Any] = {"text": result.text}
        if result.is_error:
            answer["isError"] = True  # the tool ran and failed: the model still reads why
        return answer

    title = str(entry.get("title") or "").strip() or remote_name
    description = (str(entry.get("description") or "").strip() or title)[:MAX_DESCRIPTION]
    return ToolSpec(
        name=str(entry["localName"]),
        title=title[:200],
        description=description,
        args_model=_args_model(entry.get("inputSchema") or {"type": "object"}, f"mcp_{server_id.hex}"),
        risk="external-send",
        handler=call,
        egress="open",
        idempotent=False,
        untrusted_output=True,
    )


def _config_for(url: str, sealed: str | None, runtime: McpRuntime) -> McpServerConfig:
    headers: dict[str, str] = {}
    if sealed:
        auth = json.loads(runtime.vault.unseal(sealed))
        headers[str(auth["header"])] = str(auth["value"])
    return McpServerConfig(url=url, headers=headers)


class ToolChanged(Exception):
    """The tool's definition on the server isn't the one an admin trusted."""


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

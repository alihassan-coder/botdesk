"""Handles MCP server requests (ADR 0012). Every member may see the organization's servers and
their tools; only owners and admins add, refresh, review, sign in or remove them."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.mcp.snapshot import normalized
from src.models import McpServer
from src.schemas.mcp_server import (
    McpServerAddedOut,
    McpServerIn,
    McpServerOut,
    McpSignInOut,
    McpToolBeforeOut,
    McpToolOut,
    McpToolsReviewIn,
)
from src.services import mcp_server_service
from src.services.connection_service import Actor
from src.services.mcp_server_service import McpRuntime, SignIn


def _actor(access: Access) -> Actor:
    return Actor(org_id=access.org.id, user_id=access.user.id, role=access.role)


def _tool_out(server: McpServer, raw: dict[str, Any]) -> McpToolOut:
    entry = normalized(raw)
    previous = entry.get("previous")
    return McpToolOut(
        name=f"{server.plugin_id}.{entry['localName']}",
        server_name=entry["name"],
        title=entry.get("title"),
        description=entry.get("description"),
        annotations=entry.get("annotations") or {},
        input_schema=entry.get("inputSchema") or {"type": "object"},
        output_schema=entry.get("outputSchema"),
        state=entry["state"],
        enabled=entry["enabled"],
        risk=entry["risk"],
        previous=McpToolBeforeOut(
            title=previous.get("title"),
            description=previous.get("description"),
            input_schema=previous.get("inputSchema"),
            output_schema=previous.get("outputSchema"),
        )
        if entry["state"] == "changed" and isinstance(previous, dict)
        else None,
    )


def server_out(server: McpServer, sign_in: SignIn | None = None) -> McpServerOut:
    tools = [_tool_out(server, entry) for entry in server.tools]
    status = mcp_server_service.status_of(server, sign_in)
    return McpServerOut(
        id=server.id,
        plugin_id=server.plugin_id,
        name=server.name,
        url=server.url,
        auth_kind="oauth" if server.auth_kind == "oauth" else "header" if server.auth_kind == "header" else "none",
        auth_header=server.auth_header,
        status=status,  # one of the four
        # Why the sign-in stopped working ("needs more access…") comes from its connection.
        status_reason=sign_in.reason if status == "needs_reconnect" and sign_in else server.status_reason,
        tools=tools,
        tools_hash=server.tools_hash,
        tools_changed=sum(1 for tool in tools if tool.state != "approved"),
        last_checked_at=server.last_checked_at,
        created_at=server.created_at,
        created_by=server.created_by,
    )


async def _out(db: AsyncSession, server: McpServer) -> McpServerOut:
    states = await mcp_server_service.sign_in_states(db, server.org_id)
    return server_out(server, states.get(server.plugin_id))


async def list_servers(db: AsyncSession, access: Access) -> list[McpServerOut]:
    states = await mcp_server_service.sign_in_states(db, access.org.id)
    servers = await mcp_server_service.list_servers(db, access.org.id)
    return [server_out(server, states.get(server.plugin_id)) for server in servers]


async def add_server(db: AsyncSession, access: Access, body: McpServerIn, runtime: McpRuntime) -> McpServerAddedOut:
    server, authorize_url = await mcp_server_service.add(db, runtime, _actor(access), body)
    await db.commit()
    out = await _out(db, server)
    return McpServerAddedOut(**out.model_dump(), authorize_url=authorize_url)


async def refresh_server(db: AsyncSession, access: Access, server_id: uuid.UUID, runtime: McpRuntime) -> McpServerOut:
    server = await mcp_server_service.refresh(db, runtime, _actor(access), server_id)
    await db.commit()
    return await _out(db, server)


async def review_tools(db: AsyncSession, access: Access, server_id: uuid.UUID, body: McpToolsReviewIn) -> McpServerOut:
    server = await mcp_server_service.review(db, _actor(access), server_id, body)
    await db.commit()
    return await _out(db, server)


async def start_sign_in(db: AsyncSession, access: Access, server_id: uuid.UUID, runtime: McpRuntime) -> McpSignInOut:
    url = await mcp_server_service.start_sign_in(db, runtime, _actor(access), server_id)
    await db.commit()
    return McpSignInOut(authorize_url=url)


async def remove_server(db: AsyncSession, access: Access, server_id: uuid.UUID, runtime: McpRuntime) -> None:
    revocations = await mcp_server_service.remove(db, runtime, _actor(access), server_id)
    await db.commit()
    # Now that nothing can use the sign-in, tell its authorization server too (best effort).
    await mcp_server_service.revoke_at_server(runtime, revocations)


async def client_metadata(db: AsyncSession, file_name: str, runtime: McpRuntime) -> dict[str, Any]:
    return await mcp_server_service.client_metadata(db, runtime, file_name)

"""Handles MCP server requests (ADR 0012). Every member may see the organization's servers and
their tools; only owners and admins add, refresh or remove them."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.models import McpServer
from src.schemas.mcp_server import McpServerIn, McpServerOut, McpToolOut
from src.services import mcp_server_service
from src.services.connection_service import Actor
from src.services.mcp_server_service import McpRuntime


def _actor(access: Access) -> Actor:
    return Actor(org_id=access.org.id, user_id=access.user.id, role=access.role)


def server_out(server: McpServer) -> McpServerOut:
    return McpServerOut(
        id=server.id,
        plugin_id=server.plugin_id,
        name=server.name,
        url=server.url,
        auth_kind="header" if server.auth_kind == "header" else "none",
        auth_header=server.auth_header,
        status="unreachable" if server.status == "unreachable" else "active",
        status_reason=server.status_reason,
        tools=[
            McpToolOut(
                name=f"{server.plugin_id}.{entry['localName']}",
                server_name=entry["name"],
                title=entry.get("title"),
                description=entry.get("description"),
                annotations=entry.get("annotations") or {},
            )
            for entry in server.tools
        ],
        last_checked_at=server.last_checked_at,
        created_at=server.created_at,
        created_by=server.created_by,
    )


async def list_servers(db: AsyncSession, access: Access) -> list[McpServerOut]:
    return [server_out(server) for server in await mcp_server_service.list_servers(db, access.org.id)]


async def add_server(db: AsyncSession, access: Access, body: McpServerIn, runtime: McpRuntime) -> McpServerOut:
    server = await mcp_server_service.add(db, runtime, _actor(access), body)
    await db.commit()
    return server_out(server)


async def refresh_server(db: AsyncSession, access: Access, server_id: uuid.UUID, runtime: McpRuntime) -> McpServerOut:
    server = await mcp_server_service.refresh(db, runtime, _actor(access), server_id)
    await db.commit()
    return server_out(server)


async def remove_server(db: AsyncSession, access: Access, server_id: uuid.UUID) -> None:
    await mcp_server_service.remove(db, _actor(access), server_id)
    await db.commit()

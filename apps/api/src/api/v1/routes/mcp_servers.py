import uuid

from fastapi import APIRouter, status

from src.api.deps import Db, OrgAccess, Runs
from src.controllers import mcp_server_controller
from src.schemas.mcp_server import McpServerIn, McpServerOut

router = APIRouter(prefix="/orgs/{org_id}/mcp-servers", tags=["mcp-servers"])


@router.get("")
async def list_mcp_servers(access: OrgAccess, db: Db) -> list[McpServerOut]:
    """The organization's MCP servers and their tools. Every member may see them; never a key."""
    return await mcp_server_controller.list_servers(db, access)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_mcp_server(body: McpServerIn, access: OrgAccess, db: Db, runs: Runs) -> McpServerOut:
    """Owners and admins: connect to the server (https, public addresses only), list its tools and
    save them as the tool snapshot. It becomes the plugin `pluginId`, off for every bot until bound."""
    return await mcp_server_controller.add_server(db, access, body, runs.mcp)


@router.post("/{server_id}/refresh")
async def refresh_mcp_server(server_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> McpServerOut:
    """Owners and admins: list the tools again and trust them as they are now (changed tools work
    again). A server that can't be reached keeps its tools and shows `unreachable`."""
    return await mcp_server_controller.refresh_server(db, access, server_id, runs.mcp)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mcp_server(server_id: uuid.UUID, access: OrgAccess, db: Db) -> None:
    """Owners and admins: remove the server and every bot's binding to it."""
    await mcp_server_controller.remove_server(db, access, server_id)

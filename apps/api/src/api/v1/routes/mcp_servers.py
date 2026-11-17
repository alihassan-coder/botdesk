import uuid

from fastapi import APIRouter, status

from src.api.deps import Db, OrgAccess, Runs
from src.controllers import mcp_server_controller
from src.schemas.mcp_server import McpServerAddedOut, McpServerIn, McpServerOut, McpSignInOut, McpToolsReviewIn

router = APIRouter(prefix="/orgs/{org_id}/mcp-servers", tags=["mcp-servers"])


@router.get("")
async def list_mcp_servers(access: OrgAccess, db: Db) -> list[McpServerOut]:
    """The organization's MCP servers and their tools. Every member may see them; never a key or token."""
    return await mcp_server_controller.list_servers(db, access)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_mcp_server(body: McpServerIn, access: OrgAccess, db: Db, runs: Runs) -> McpServerAddedOut:
    """Owners and admins: connect to the server (https, public addresses only), list its tools and
    save them as the tool snapshot. It becomes the plugin `pluginId`, off for every bot until bound.
    A server that wants an OAuth sign-in is saved waiting for it, with `authorizeUrl` to go to."""
    return await mcp_server_controller.add_server(db, access, body, runs.mcp)


@router.post("/{server_id}/refresh")
async def refresh_mcp_server(server_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> McpServerOut:
    """Owners and admins: list the tools again. Changed and new tools wait for the review
    (`toolsChanged`). A server that can't be reached keeps its tools and shows `unreachable`."""
    return await mcp_server_controller.refresh_server(db, access, server_id, runs.mcp)


@router.put("/{server_id}/tools")
async def review_mcp_tools(server_id: uuid.UUID, body: McpToolsReviewIn, access: OrgAccess, db: Db) -> McpServerOut:
    """Owners and admins: approve the named tools as they are now, offered to bots or not, at the
    chosen risk (each change audited). 409 when the tools changed since `toolsHash`."""
    return await mcp_server_controller.review_tools(db, access, server_id, body)


@router.post("/{server_id}/sign-in")
async def sign_in_mcp_server(server_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> McpSignInOut:
    """Owners and admins: (re)connect the organization's OAuth sign-in to this server."""
    return await mcp_server_controller.start_sign_in(db, access, server_id, runs.mcp)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mcp_server(server_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> None:
    """Owners and admins: remove the server, every bot's binding to it and its sign-in."""
    await mcp_server_controller.remove_server(db, access, server_id, runs.mcp)

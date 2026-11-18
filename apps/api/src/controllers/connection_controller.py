"""Handles Connect apps' connection requests (ADR 0010). Members connect their own accounts;
owners and admins (and a bot's creator) connect bot and organization accounts. Responses never
carry a credential."""

import logging
import uuid
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.errors import NotFound
from src.plugins.registry import ToolRegistry
from src.schemas.connection import ApiKeyConnectionIn, ConnectionOut, OAuthStartIn, OAuthStartOut
from src.services import auth_service, connection_service, mcp_server_service
from src.services.connection_service import Actor
from src.services.credential_vault import CredentialVault
from src.services.mcp_server_service import McpRuntime
from src.services.oauth_flow import FlowFailed, OAuth

logger = logging.getLogger(__name__)


def _actor(access: Access) -> Actor:
    return Actor(org_id=access.org.id, user_id=access.user.id, role=access.role)


async def list_connections(db: AsyncSession, access: Access) -> list[ConnectionOut]:
    connections = await connection_service.list_visible(db, _actor(access))
    return [ConnectionOut.model_validate(connection) for connection in connections]


async def get_connection(db: AsyncSession, access: Access, connection_id: uuid.UUID) -> ConnectionOut:
    return ConnectionOut.model_validate(await connection_service.get_visible(db, _actor(access), connection_id))


async def connect_api_key(
    db: AsyncSession, access: Access, body: ApiKeyConnectionIn, *, registry: ToolRegistry, vault: CredentialVault
) -> ConnectionOut:
    connector = registry.plugin(body.connector_id)
    if connector is None:
        raise NotFound(connection_service.UNKNOWN_CONNECTOR)
    connection = await connection_service.connect_api_key(db, _actor(access), connector, body, vault)
    await db.commit()
    return ConnectionOut.model_validate(connection)


async def start_oauth(
    db: AsyncSession, access: Access, body: OAuthStartIn, *, registry: ToolRegistry, oauth: OAuth
) -> OAuthStartOut:
    connector = registry.plugin(body.connector_id)
    if connector is None:
        raise NotFound(connection_service.UNKNOWN_CONNECTOR)
    url = await oauth.start(db, _actor(access), connector, body)
    await db.commit()
    return OAuthStartOut(authorize_url=url)


async def finish_oauth(
    db: AsyncSession,
    session_token: str | None,
    *,
    state: str | None,
    code: str | None,
    error: str | None,
    iss: str | None,
    oauth: OAuth,
    web_app_url: str,
) -> str:
    """Where the browser goes after the provider's sign-in page: the web's callback page with
    `result=connected&connector=…` or `result=error&code=…`. Never the provider's own words."""
    user = await auth_service.user_for_token(db, session_token) if session_token else None
    try:
        connection = await oauth.finish(db, state=state, code=code, error=error, iss=iss, session_user=user)
        query = {"result": "connected", "connector": connection.connector_id}
    except FlowFailed as failed:
        await db.rollback()
        if failed.reason:
            logger.info("OAuth sign-in refused (%s): %s", failed.code, failed.reason)
        query = {"result": "error", "code": failed.code}
    except Exception as unexpected:  # the browser always gets a page it can show
        await db.rollback()
        logger.warning("OAuth sign-in failed (%s).", type(unexpected).__name__)
        query = {"result": "error", "code": "failed"}
    return f"{web_app_url.rstrip('/')}/apps/callback?{urlencode(query)}"


async def disconnect(
    db: AsyncSession,
    access: Access,
    connection_id: uuid.UUID,
    *,
    vault: CredentialVault,
    oauth: OAuth,
    mcp: McpRuntime | None = None,
) -> None:
    connection, token = await connection_service.disconnect(db, _actor(access), connection_id, vault)
    connector_id = connection.connector_id
    await db.commit()
    if token is None:
        return
    # An OAuth token: tell the provider too, now that nothing waits on it.
    if mcp is not None and mcp_server_service.is_mcp_plugin(connector_id):  # an MCP server's sign-in
        revocation = await mcp_server_service.revocation_for(db, mcp, access.org.id, connector_id, token)
        await db.rollback()  # end that read before the network
        await mcp_server_service.revoke_at_server(mcp, [revocation] if revocation else [])
        return
    await oauth.revoke(oauth.registry.plugin(connector_id), token)

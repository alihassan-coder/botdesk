"""Handles Connect apps' connection requests (ADR 0010). Members connect their own accounts;
owners and admins (and a bot's creator) connect bot and organization accounts. Responses never
carry a credential."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.errors import NotFound
from src.plugins.registry import ToolRegistry
from src.schemas.connection import ApiKeyConnectionIn, ConnectionOut
from src.services import connection_service
from src.services.connection_service import Actor
from src.services.credential_vault import CredentialVault


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


async def disconnect(db: AsyncSession, access: Access, connection_id: uuid.UUID, *, vault: CredentialVault) -> None:
    await connection_service.disconnect(db, _actor(access), connection_id, vault)
    await db.commit()

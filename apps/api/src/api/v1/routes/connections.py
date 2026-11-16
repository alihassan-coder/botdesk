import uuid

from fastapi import APIRouter, status

from src.api.deps import Db, OAuthFlows, OrgAccess, Runs, Vault
from src.controllers import connection_controller
from src.schemas.connection import ApiKeyConnectionIn, ConnectionOut, OAuthStartIn, OAuthStartOut

router = APIRouter(prefix="/orgs/{org_id}/connections", tags=["connections"])


@router.get("")
async def list_connections(access: OrgAccess, db: Db) -> list[ConnectionOut]:
    """The organization's connections you may see: your own, the bots' and the organization's
    (owners and admins also see that other members' exist). Never a credential."""
    return await connection_controller.list_connections(db, access)


@router.post("", status_code=status.HTTP_201_CREATED)
async def connect_api_key(
    body: ApiKeyConnectionIn, access: OrgAccess, db: Db, runs: Runs, vault: Vault
) -> ConnectionOut:
    """Connect an account with an API key (for a connector whose plugin uses `ApiKeyAuth`).
    The same connector, owner and label again replaces the key. OAuth apps use `oauth/start`."""
    return await connection_controller.connect_api_key(db, access, body, registry=runs.registry, vault=vault)


@router.post("/oauth/start")
async def start_oauth(body: OAuthStartIn, access: OrgAccess, db: Db, runs: Runs, oauth: OAuthFlows) -> OAuthStartOut:
    """Start signing in with an OAuth app (Gmail): send the browser to `authorizeUrl`; it comes
    back through `/api/v1/oauth/callback`. The same owner again reconnects the same account."""
    return await connection_controller.start_oauth(db, access, body, registry=runs.registry, oauth=oauth)


@router.get("/{connection_id}")
async def get_connection(connection_id: uuid.UUID, access: OrgAccess, db: Db) -> ConnectionOut:
    return await connection_controller.get_connection(db, access, connection_id)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(connection_id: uuid.UUID, access: OrgAccess, db: Db, vault: Vault, oauth: OAuthFlows) -> None:
    """Forget the credential and mark the connection disconnected (kept for the audit log). An
    OAuth token is also revoked at the provider, best effort, once that is saved."""
    await connection_controller.disconnect(db, access, connection_id, vault=vault, oauth=oauth)

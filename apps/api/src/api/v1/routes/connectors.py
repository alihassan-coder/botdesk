from fastapi import APIRouter

from src.api.deps import AppSettings, OrgAccess, Runs
from src.controllers import plugin_controller
from src.schemas.plugin import ConnectorOut

router = APIRouter(prefix="/orgs/{org_id}/connectors", tags=["connections"])


@router.get("")
async def list_connectors(access: OrgAccess, runs: Runs, settings: AppSettings) -> list[ConnectorOut]:
    """Connect apps: one entry per loaded plugin, with how it connects (`authType`, `accessLevels`)
    and whether this server can connect it yet (`setup`: an OAuth app needs its provider's client)."""
    return await plugin_controller.list_connectors(access, runs, settings)

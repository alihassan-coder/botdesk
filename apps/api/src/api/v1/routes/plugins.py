from fastapi import APIRouter

from src.api.deps import OrgAccess, Runs
from src.controllers import plugin_controller
from src.schemas.plugin import PluginOut

router = APIRouter(prefix="/orgs/{org_id}/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(access: OrgAccess, runs: Runs) -> list[PluginOut]:
    """The plugins this server loaded (the `PLUGINS` allowlist) and their tools, with each tool's
    risk class. No handlers or code: just what a person needs to know."""
    return await plugin_controller.list_plugins(access, runs)

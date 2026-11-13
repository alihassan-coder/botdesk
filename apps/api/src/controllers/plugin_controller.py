"""Handles plugin requests. Every member of an organization may see which tools exist: the
"Connect apps" page and the approval cards both need them."""

from src.api.deps import Access
from src.runtime.runner import RunManager
from src.schemas.plugin import PluginOut
from src.services import plugin_service


async def list_plugins(_access: Access, runs: RunManager) -> list[PluginOut]:
    return plugin_service.plugin_views(runs.registry)

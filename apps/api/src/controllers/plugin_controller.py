"""Handles plugin requests. Every member of an organization may see which tools exist: the
"Connect apps" page and the approval cards both need them."""

from src.api.deps import Access
from src.core.config import Settings
from src.runtime.runner import RunManager
from src.schemas.plugin import ConnectorOut, PluginOut
from src.services import plugin_service


async def list_plugins(_access: Access, runs: RunManager) -> list[PluginOut]:
    return plugin_service.plugin_views(runs.registry)


async def list_connectors(_access: Access, runs: RunManager, settings: Settings) -> list[ConnectorOut]:
    return plugin_service.connector_views(runs.registry, settings)

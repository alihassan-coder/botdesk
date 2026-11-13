"""Plugins as the API shows them. The registry is built once at startup from the `PLUGINS`
allowlist, so every organization on this server sees the same list; switching a plugin on or
off per organization comes with installations (build step 5)."""

from src.plugins.registry import ToolRegistry
from src.schemas.plugin import PluginOut, PluginToolOut


def plugin_views(registry: ToolRegistry) -> list[PluginOut]:
    return [
        PluginOut(
            id=plugin.id,
            name=plugin.name,
            version=plugin.version,
            description=plugin.description,
            tools=[
                PluginToolOut(
                    name=f"{plugin.id}.{tool.name}", title=tool.title, description=tool.description, risk=tool.risk
                )
                for tool in plugin.tools
            ],
        )
        for plugin in registry.plugins()
    ]

"""Plugins as the API shows them. The registry is built once at startup from the `PLUGINS`
allowlist, so every organization on this server sees the same list; switching a plugin on or
off per organization comes with installations (build step 5)."""

from botdesk_plugin_sdk import ApiKeyAuth, OAuth2Auth, PluginManifest

from src.core.config import Settings
from src.plugins.registry import ToolRegistry
from src.schemas.plugin import ConnectorOut, PluginOut, PluginToolOut
from src.services.oauth_flow import default_access, setup_state


def _tools(plugin: PluginManifest) -> list[PluginToolOut]:
    return [
        PluginToolOut(name=f"{plugin.id}.{tool.name}", title=tool.title, description=tool.description, risk=tool.risk)
        for tool in plugin.tools
    ]


def plugin_views(registry: ToolRegistry) -> list[PluginOut]:
    return [
        PluginOut(
            id=plugin.id,
            name=plugin.name,
            version=plugin.version,
            description=plugin.description,
            tools=_tools(plugin),
        )
        for plugin in registry.plugins()
    ]


def connector_views(registry: ToolRegistry, settings: Settings) -> list[ConnectorOut]:
    """Connect apps' list (GET /connectors): each plugin, how it connects, and whether this server
    can connect it yet."""
    views = []
    for plugin in registry.plugins():
        auth = plugin.auth
        oauth = auth if isinstance(auth, OAuth2Auth) else None
        views.append(
            ConnectorOut(
                id=plugin.id,
                name=plugin.name,
                description=plugin.description,
                version=plugin.version,
                auth_type="oauth2" if oauth else "api_key" if isinstance(auth, ApiKeyAuth) else None,
                setup=setup_state(settings, plugin),
                access_levels=list(oauth.scope_sets) if oauth else [],
                default_access=default_access(oauth) if oauth else None,
                tools=_tools(plugin),
            )
        )
    return views

"""What the "Connect apps" page reads: the plugins this server loaded and their tools.

Only what a person needs to decide whether to use a tool. Handlers, args models and anything
else executable stay on the server.
"""

from typing import Literal

from botdesk_plugin_sdk import RiskClass

from src.schemas.common import ApiModel


class PluginToolOut(ApiModel):
    name: str  # full name, as on approval cards: "demo.send_email"
    title: str
    description: str
    risk: RiskClass


class PluginOut(ApiModel):
    id: str
    name: str
    version: str
    description: str
    tools: list[PluginToolOut]


class ConnectorOut(ApiModel):
    """A plugin as Connect apps shows it: how it connects and whether this server can do that."""

    id: str
    name: str
    description: str
    version: str
    auth_type: Literal["oauth2", "api_key"] | None
    # not-configured: an OAuth app whose provider has no client on this server yet.
    setup: Literal["ready", "not-configured"]
    access_levels: list[str]  # the OAuth scope sets' names ("read", "full"); [] otherwise
    default_access: str | None
    tools: list[PluginToolOut]

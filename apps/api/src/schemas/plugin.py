"""What the "Connect apps" page reads: the plugins this server loaded and their tools.

Only what a person needs to decide whether to use a tool. Handlers, args models and anything
else executable stay on the server.
"""

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

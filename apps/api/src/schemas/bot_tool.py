"""A bot's Tools tab (slice 5.2): one entry per loaded plugin, with the bot's binding."""

import uuid
from typing import Literal

from pydantic import Field

from src.schemas.common import ApiModel
from src.schemas.plugin import PluginToolOut


class BotTriggerOut(ApiModel):
    """One of the plugin's triggers (slice 6.3), and whether this bot reacts to it."""

    name: str  # "new_email"
    title: str  # "React to new email"
    description: str
    enabled: bool
    subscriber_id: uuid.UUID | None  # who switched it on: its events go to their DM with the bot
    problem: str | None  # why the last poll did nothing ("Paused: … needs reconnecting")


class BotTriggerIn(ApiModel):
    enabled: bool


class BotToolMcpOut(ApiModel):
    """For an MCP server (ADR 0012, slice 7.4): what its card says besides the tools offered."""

    tools_waiting: int  # changed or new tools no bot gets until an owner or admin reviews them
    problem: str | None  # "Needs signing in again: …", or the server couldn't be reached
    org_account: bool  # it uses the organization's key or sign-in: only owners and admins switch it


class BotToolOut(ApiModel):
    plugin_id: str
    name: str
    description: str
    auth_type: Literal["api_key", "oauth2"] | None
    enabled: bool  # false for a plugin the bot has no binding for
    connection_id: uuid.UUID | None
    tools: list[PluginToolOut]  # an MCP server whose tools all wait for a review has none
    triggers: list[BotTriggerOut] = Field(default_factory=list)
    mcp: BotToolMcpOut | None = None  # MCP servers only


class BotToolsOut(ApiModel):
    plugins: list[BotToolOut]


class BotToolChange(ApiModel):
    plugin_id: str = Field(min_length=1, max_length=80)
    enabled: bool
    connection_id: uuid.UUID | None  # required: null means "no account"


class BotToolsIn(ApiModel):
    """Only the plugins sent change."""

    plugins: list[BotToolChange] = Field(max_length=200)

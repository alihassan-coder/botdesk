"""A bot's Tools tab (slice 5.2): one entry per loaded plugin, with the bot's binding."""

import uuid
from typing import Literal

from pydantic import Field

from src.schemas.common import ApiModel
from src.schemas.plugin import PluginToolOut


class BotToolOut(ApiModel):
    plugin_id: str
    name: str
    description: str
    auth_type: Literal["api_key", "oauth2"] | None
    enabled: bool  # false for a plugin the bot has no binding for
    connection_id: uuid.UUID | None
    tools: list[PluginToolOut]


class BotToolsOut(ApiModel):
    plugins: list[BotToolOut]


class BotToolChange(ApiModel):
    plugin_id: str = Field(min_length=1, max_length=80)
    enabled: bool
    connection_id: uuid.UUID | None  # required: null means "no account"


class BotToolsIn(ApiModel):
    """Only the plugins sent change."""

    plugins: list[BotToolChange] = Field(max_length=200)

"""A bot's browser, for people: is it open, what's on it, and taking over (ADR 0017 §5)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from src.browser.browsers import KEYS, VIEWPORT
from src.schemas.common import ApiModel


class BrowserOut(ApiModel):
    # Whether people can watch and take over this bot's browser on this server.
    available: bool
    open: bool
    url: str | None
    title: str | None
    width: int = VIEWPORT["width"]
    height: int = VIEWPORT["height"]


class ClickIn(ApiModel):
    kind: Literal["click"]
    x: int = Field(ge=0, lt=VIEWPORT["width"])
    y: int = Field(ge=0, lt=VIEWPORT["height"])


class TypeIn(ApiModel):
    kind: Literal["type"]
    text: str = Field(min_length=1, max_length=500)


class KeyIn(ApiModel):
    kind: Literal["key"]
    key: Literal[KEYS]  # type: ignore[valid-type]


class ScrollIn(ApiModel):
    kind: Literal["scroll"]
    dy: int = Field(ge=-3000, le=3000)


class OpenIn(ApiModel):
    kind: Literal["open"]
    url: str = Field(min_length=4, max_length=2000)


PersonInputIn = Annotated[ClickIn | TypeIn | KeyIn | ScrollIn | OpenIn, Field(discriminator="kind")]


BrowserProviderId = Literal["local", "steel", "browserbase", "kernel"]


class BrowserProviderIn(ApiModel):
    """Local, or a cloud provider with the organization's key. `apiKey` may be left out when
    changing other fields of the provider already chosen: the saved key is kept."""

    provider: BrowserProviderId
    api_key: str | None = Field(default=None, min_length=8, max_length=400)
    project_id: str = Field(default="", max_length=100)  # Browserbase only, optional


class BrowserProviderOut(ApiModel):
    provider: BrowserProviderId
    key_hint: str | None  # the key's last 4 characters
    project_id: str
    # Whether this server lets bots use a browser on its own machine (LOCAL_BROWSER).
    local_available: bool
    checked_at: datetime | None

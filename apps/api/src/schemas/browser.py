"""A bot's browser, for people: is it open, what's on it, and taking over (ADR 0017 §5)."""

from typing import Annotated, Literal

from pydantic import Field

from src.browser.local import KEYS, VIEWPORT
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

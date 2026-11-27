"""Bots' cloud computers, for people (ADR 0020): the organization's provider, a bot's computer, and
taking it over."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from src.schemas.common import ApiModel

ComputerState = Literal["none", "creating", "starting", "running", "stopping", "stopped", "error"]

# Keys people may press on a bot's computer, and the X11 keysym each one sends.
KEYS: dict[str, str] = {
    "Enter": "Return",
    "Tab": "Tab",
    "Escape": "Escape",
    "BackSpace": "BackSpace",
    "Delete": "Delete",
    "Up": "Up",
    "Down": "Down",
    "Left": "Left",
    "Right": "Right",
    "Home": "Home",
    "End": "End",
    "Page_Up": "Page_Up",
    "Page_Down": "Page_Down",
    "ctrl+c": "ctrl+c",
    "ctrl+v": "ctrl+v",
    "ctrl+a": "ctrl+a",
    "ctrl+l": "ctrl+l",
}
KeyName = Literal[
    "Enter",
    "Tab",
    "Escape",
    "BackSpace",
    "Delete",
    "Up",
    "Down",
    "Left",
    "Right",
    "Home",
    "End",
    "Page_Up",
    "Page_Down",
    "ctrl+c",
    "ctrl+v",
    "ctrl+a",
    "ctrl+l",
]
SCREEN_MAX = 7680  # pixels: no screen is wider or taller


class ComputerProviderIn(ApiModel):
    """Orgo with the organization's key. Leave `apiKey` out to check the saved one again."""

    provider: Literal["orgo"]
    api_key: str | None = Field(default=None, min_length=8, max_length=400)


class ComputerProviderOut(ApiModel):
    provider: Literal["orgo"] | None  # None: no cloud computers for this organization's bots
    key_hint: str | None  # the key's last 4 characters
    checked_at: datetime | None
    # key_refused: Orgo answered 401 since the key was saved (paste a working one again).
    status: Literal["ok", "key_refused"] | None


class ComputerAppOut(ApiModel):
    name: str
    port: int | None
    status: str  # Orgo's: running, starting, crashing, stopped, exited, failed, pending, off, unknown


class ComputerPreviewOut(ApiModel):
    url: str
    port: int
    access: str  # team (people in the Orgo workspace) | people | link (anyone with it)


class ComputerOut(ApiModel):
    status: ComputerState
    name: str | None = None
    remote_id: str | None = None
    cpu: float | None = None
    ram: int | None = None  # GB
    region: str | None = None
    started_at: datetime | None = None
    last_used_at: datetime | None = None
    idle_stops_at: datetime | None = None  # when it stops by itself if nobody uses it (running only)
    error: str | None = None
    orgo_url: str | None = None  # the computer in Orgo's dashboard, for people with the Orgo account
    apps: list[ComputerAppOut] = Field(default_factory=list)
    previews: list[ComputerPreviewOut] = Field(default_factory=list)


class ComputerInputIn(ApiModel):
    """Taking over: a click (screen pixels), text, an allowed key, or a scroll."""

    kind: Literal["click", "double_click", "right_click", "type", "key", "scroll"]
    x: int | None = Field(default=None, ge=0, lt=SCREEN_MAX)
    y: int | None = Field(default=None, ge=0, lt=SCREEN_MAX)
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    key: KeyName | None = None
    direction: Literal["up", "down"] | None = None

    @model_validator(mode="after")
    def _has_what_its_kind_needs(self) -> Self:
        if self.kind in ("click", "double_click", "right_click") and (self.x is None or self.y is None):
            raise ValueError("A click needs x and y.")
        if self.kind == "type" and not self.text:
            raise ValueError("Typing needs text.")
        if self.kind == "key" and self.key is None:
            raise ValueError("Pressing a key needs key.")
        if self.kind == "scroll" and self.direction is None:
            raise ValueError("Scrolling needs direction (up or down).")
        return self

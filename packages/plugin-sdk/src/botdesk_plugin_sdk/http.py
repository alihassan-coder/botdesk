"""`ctx.http`: how a tool calls another app's API (ADR 0010 §8).

A tool never holds a token. It calls `await ctx.http.request("GET", "https://…")` and BotDesk's
client adds the connection's credential itself, reaches only the hosts the manifest lists in
`egress` (over https), never follows a redirect, refuses private addresses, caps the response
size and times out. In tests, `botdesk_plugin_sdk.testing.FakeHttp` stands in for it.

`HttpClient` is a `Protocol` so the SDK depends on nothing but Pydantic: any object with this
`request` method works.
"""

import json as jsonlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

Params = Mapping[str, str | int | float | bool]


class HttpError(Exception):
    """A request `ctx.http` wouldn't make or couldn't finish. The message is safe to show people
    and never contains a credential. A tool may let it propagate: the call then fails with it."""


class HostNotAllowed(HttpError):
    """The URL isn't https, or its host isn't in the plugin's `egress`."""


class ResponseTooLarge(HttpError):
    """The answer was bigger than BotDesk accepts for one tool call."""


class NotConnected(HttpError):
    """There is no usable account for this call: none connected, revoked, or it needs reconnecting."""


@dataclass(frozen=True)
class HttpResponse:
    """A finished response. `headers` keys are lowercase."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    content: bytes = b""
    url: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return jsonlib.loads(self.content)


class HttpClient(Protocol):
    """What `ctx.http` is. Send `json` (a JSON body) or `data` (a form), not both."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Params | None = None,
        json: Any = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse: ...


class NoHttp:
    """`ctx.http` for a tool whose plugin declares no hosts: every request is refused."""

    def __init__(self, reason: str = "This tool has no web access: its plugin lists no hosts in egress.") -> None:
        self.reason = reason

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Params | None = None,
        json: Any = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        raise NotConnected(self.reason)

"""Helpers for testing a plugin without BotDesk: no database, no server, no model, no network.

    result = await call_tool(my_plugin(), "create_note", {"title": "Hi"})

    http = FakeHttp(my_plugin())                       # only the manifest's egress hosts
    http.route("GET", "https://api.example.com/me", json={"name": "Acme"})
    result = await call_tool(my_plugin(), "whoami", {}, make_context(http=http))

`call_tool` does what the app does before a handler runs (check the manifest, validate the
arguments against the args model), then calls the handler with a throwaway context. It does
not apply the approval policy: that belongs to the app, not to the plugin.
"""

import json as jsonlib
import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from botdesk_plugin_sdk.http import HostNotAllowed, HttpResponse, Params
from botdesk_plugin_sdk.manifest import PluginManifest
from botdesk_plugin_sdk.tool import ToolContext, ToolResult
from botdesk_plugin_sdk.validation import validate_manifest


def make_context(**overrides: Any) -> ToolContext:
    """A `ToolContext` with fresh random ids. Pass any field to fix it (`org_id=...`)."""
    call_id = overrides.pop("tool_call_id", f"test-{uuid.uuid4().hex[:8]}")
    values: dict[str, Any] = {
        "org_id": uuid.uuid4(),
        "bot_id": uuid.uuid4(),
        "run_id": uuid.uuid4(),
        "tool_call_id": call_id,
        "idempotency_key": f"test:{call_id}",
        "logger": logging.getLogger("botdesk.plugins.test"),
    }
    values.update(overrides)
    return ToolContext(**values)


async def call_tool(
    manifest: PluginManifest, tool_name: str, args: dict[str, Any], ctx: ToolContext | None = None
) -> ToolResult:
    """Run one tool the way BotDesk would. Raises `pydantic.ValidationError` for bad arguments."""
    validate_manifest(manifest)
    tool = next((t for t in manifest.tools if t.name == tool_name), None)
    if tool is None:
        raise KeyError(f"Plugin {manifest.id!r} has no tool called {tool_name!r}.")
    parsed = tool.args_model.model_validate(args)
    return await tool.handler(parsed, ctx or make_context())


@dataclass(frozen=True)
class FakeRequest:
    """One request a tool made through `FakeHttp`."""

    method: str
    url: str  # without the query string; the query is in `params`
    params: dict[str, Any] = field(default_factory=dict)
    json: Any = None
    data: dict[str, str] | None = None
    headers: dict[str, str] = field(default_factory=dict)


class FakeHttp:
    """`ctx.http` for tests: canned answers by method and URL, and the same host rule as BotDesk.

    Only https URLs on the manifest's `egress` hosts are allowed (`HostNotAllowed` otherwise), so
    a test fails when a tool calls a host its manifest doesn't declare. A request with no route
    fails the test (`AssertionError`). There is no credential here: BotDesk adds it, never the tool.
    """

    def __init__(self, egress: PluginManifest | Iterable[str]) -> None:
        self.hosts = frozenset(egress.egress if isinstance(egress, PluginManifest) else egress)
        self.routes: dict[tuple[str, str], HttpResponse] = {}
        self.requests: list[FakeRequest] = []

    def route(
        self,
        method: str,
        url: str,
        *,
        status: int = 200,
        json: Any = None,
        content: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Answer `method url` (no query string) with this response from now on."""
        if json is not None:
            content = jsonlib.dumps(json).encode()
            headers = {"content-type": "application/json", **(headers or {})}
        response = HttpResponse(status, {k.lower(): v for k, v in (headers or {}).items()}, content, url)
        self.routes[(method.upper(), url)] = response

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
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise HostNotAllowed(f"Only https addresses are allowed, not {url!r}.")
        if parts.hostname not in self.hosts:
            raise HostNotAllowed(f"{parts.hostname} is not in this plugin's egress hosts.")
        base = parts._replace(query="", fragment="").geturl()
        query = dict(part.split("=", 1) for part in parts.query.split("&") if "=" in part)
        self.requests.append(
            FakeRequest(
                method=method.upper(),
                url=base,
                params={**query, **(params or {})},
                json=json,
                data=dict(data) if data is not None else None,
                headers=dict(headers or {}),
            )
        )
        response = self.routes.get((method.upper(), base))
        if response is None:
            raise AssertionError(f"FakeHttp has no route for {method.upper()} {base}")
        return response

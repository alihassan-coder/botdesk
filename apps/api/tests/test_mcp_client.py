"""The MCP client (slice 7.1, ADR 0012) against a real MCP server built with the SDK's server side,
served by uvicorn on 127.0.0.1 in a background thread.

Every request goes through the SSRF guard for real: the server is reached by made-up host names
("mcp.test", "other.test") that a test resolver maps to 127.0.0.1, so the guard resolves, checks and
pins the address exactly as it would in production. Reaching it at all needs the test-only network
policy (private addresses and plain http allowed); the safety tests use the production policy."""

import asyncio
import base64
import json
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import mcp_types
import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp.types import Icon
from mcp_types import INTERNAL_ERROR, INVALID_PARAMS, METHOD_NOT_FOUND, REQUEST_TIMEOUT
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from src.mcp.client import (
    McpCallResult,
    McpClientError,
    McpIcon,
    McpNetwork,
    McpProtocolError,
    McpRefused,
    McpResponseTooLarge,
    McpServerConfig,
    McpTimeout,
    McpUnsafeUrl,
    _translate,
    call_tool,
    list_tools,
)

HUGE = 300 * 1024  # more text than a tool result may carry (256 KB)
# A 1x1 PNG: the icon the test server names for itself, and serves at /icon.png.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


# The test server


def build_server() -> MCPServer:
    icon = Icon.model_validate({"src": PNG_URI, "mimeType": "image/png", "sizes": ["16x16"]})
    server = MCPServer("botdesk-test", icons=[icon])

    @server.tool(description="Adds two numbers.", structured_output=False)
    def add(a: int, b: int) -> str:
        return str(a + b)

    @server.tool(description="Always fails.", structured_output=False)
    def broken() -> str:
        raise ToolError("the database is on fire")

    @server.tool(description="Takes its time.", structured_output=False)
    async def slow(seconds: float) -> str:
        await asyncio.sleep(seconds)
        return "done"

    @server.tool(description="Says a lot.", structured_output=False)
    def chatty(size: int) -> str:
        return "x" * size

    @server.tool(description="Answers with structured content.")
    def weather(city: str) -> dict[str, Any]:
        return {"city": city, "celsius": 21}

    return server


@dataclass
class Recorder:
    """Every HTTP request the test server received: host and headers."""

    requests: list[dict[str, str]] = field(default_factory=list)

    def wrap(self, app: ASGIApp) -> ASGIApp:
        async def recording(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
                self.requests.append(headers | {":method": scope["method"]})
            await app(scope, receive, send)

        return recording


@dataclass
class LiveServer:
    port: int
    recorder: Recorder

    def url(self, host: str = "mcp.test", path: str = "/mcp") -> str:
        return f"http://{host}:{self.port}{path}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server() -> Iterator[LiveServer]:
    port = _free_port()
    mcp_app = build_server().streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def icon(_request: Request) -> Response:
        return Response(PNG, media_type="image/png")

    async def big_icon(_request: Request) -> Response:
        return Response(PNG + b"0" * (70 * 1024), media_type="image/png")

    async def page(_request: Request) -> Response:
        return Response("<html>not an icon</html>", media_type="text/html")

    async def moved(_request: Request) -> RedirectResponse:
        # A 307 to the same server under another host name: another origin, so never followed.
        return RedirectResponse(f"http://other.test:{port}/mcp", status_code=307)

    async def handshake_era(scope: Scope, receive: Receive, send: Send) -> None:
        """A server from before 2026-07-28: it doesn't know `server/discover`, so the client must
        fall back to the `initialize` handshake."""
        headers = dict(scope.get("headers", []))
        if headers.get(b"mcp-method") == b"server/discover":
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await mcp_app(scope, receive, send)

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = Starlette(
        routes=[
            Route("/moved", moved, methods=["POST", "GET"]),
            Route("/icon.png", icon),
            Route("/big.png", big_icon),
            Route("/page", page),
            Mount("/mcp", app=mcp_app),
            Mount("/legacy", app=handshake_era),
        ],
        lifespan=lifespan,
    )
    recorder = Recorder()
    server = uvicorn.Server(uvicorn.Config(recorder.wrap(app), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "test MCP server didn't start"
        time.sleep(0.05)
    yield LiveServer(port=port, recorder=recorder)
    server.should_exit = True
    thread.join(timeout=5)


async def resolve_to_loopback(host: str) -> list[str]:
    assert host in ("mcp.test", "other.test"), f"unexpected lookup of {host}"
    return ["127.0.0.1"]


TEST_NETWORK = McpNetwork(allow_private=True, allow_http=True, resolve=resolve_to_loopback)


def config(live: LiveServer, **overrides: Any) -> McpServerConfig:
    return McpServerConfig(url=overrides.pop("url", live.url()), **overrides)


# Listing and calling


async def test_lists_the_servers_tools_and_icons(live_server: LiveServer) -> None:
    listing = await list_tools(config(live_server), network=TEST_NETWORK)
    tools = listing.tools
    assert listing.icons == [McpIcon(src=PNG_URI, mime_type="image/png", sizes=("16x16",), theme=None)]

    by_name = {tool.name: tool for tool in tools}
    assert set(by_name) == {"add", "broken", "slow", "chatty", "weather"}
    assert by_name["add"].description == "Adds two numbers."
    assert set(by_name["add"].input_schema["properties"]) == {"a", "b"}


async def test_calls_a_tool_and_gets_its_text(live_server: LiveServer) -> None:
    result = await call_tool(config(live_server), "add", {"a": 2, "b": 3}, network=TEST_NETWORK)

    assert result == McpCallResult(text="5", is_error=False, truncated=False)


async def test_structured_content_is_preferred_over_the_text_parts(live_server: LiveServer) -> None:
    result = await call_tool(config(live_server), "weather", {"city": "Lahore"}, network=TEST_NETWORK)

    assert result.is_error is False
    assert json.loads(result.text) == {"city": "Lahore", "celsius": 21}


async def test_a_tool_that_fails_is_an_error_result_the_model_still_reads(live_server: LiveServer) -> None:
    result = await call_tool(config(live_server), "broken", {}, network=TEST_NETWORK)

    assert result.is_error is True
    assert "the database is on fire" in result.text


async def test_falls_back_to_the_handshake_with_an_older_server(live_server: LiveServer) -> None:
    before = len(live_server.recorder.requests)

    result = await call_tool(
        config(live_server, url=live_server.url(path="/legacy")), "add", {"a": 1, "b": 1}, network=TEST_NETWORK
    )

    assert result.text == "2"
    sent = live_server.recorder.requests[before:]
    assert sent[0].get("mcp-method") == "server/discover"  # tried 2026-07-28 first
    assert sent[-1][":method"] == "DELETE"  # handshake-era session closed at the end
    assert {r.get("mcp-protocol-version") for r in sent[2:]} <= {None, "2025-11-25"}


async def test_header_auth_reaches_the_server(live_server: LiveServer) -> None:
    before = len(live_server.recorder.requests)

    await list_tools(config(live_server, headers={"X-API-Key": "k-123"}), network=TEST_NETWORK)

    sent = live_server.recorder.requests[before:]
    assert sent
    assert all(r.get("x-api-key") == "k-123" for r in sent)


# Limits


async def test_a_slow_tool_times_out(live_server: LiveServer) -> None:
    started = time.monotonic()

    with pytest.raises(McpTimeout, match="took too long"):
        await call_tool(config(live_server, call_timeout=0.5), "slow", {"seconds": 5}, network=TEST_NETWORK)

    assert time.monotonic() - started < 3


def test_the_sdks_own_request_timeout_counts_as_a_timeout() -> None:
    """A slow tool races two clocks: httpx2's read timeout and the SDK's request timeout.
    Whichever fires first, the caller sees a timeout, not a protocol error."""
    error = MCPError(code=REQUEST_TIMEOUT, message="Request 'tools/call' timed out")

    translated = _translate(error, "mcp.test")

    assert isinstance(translated, McpTimeout)
    assert "took too long" in str(translated)


@pytest.mark.parametrize(
    ("code", "refused"),
    [
        (METHOD_NOT_FOUND, True),  # the call was refused: nothing ran
        (INVALID_PARAMS, True),  # an unknown tool or bad arguments: nothing ran
        (INTERNAL_ERROR, False),  # may come after the tool did its thing
        (-32000, False),  # a server's own error code: can't tell
    ],
)
def test_only_refusals_say_the_tool_did_not_run(code: int, refused: bool) -> None:
    translated = _translate(MCPError(code=code, message="nope"), "mcp.test")
    assert isinstance(translated, McpProtocolError)
    assert isinstance(translated, McpRefused) is refused


def test_an_answer_that_isnt_mcp_is_not_a_refusal() -> None:
    with pytest.raises(ValidationError) as invalid:
        mcp_types.CallToolResult.model_validate({"content": "not a list"})
    translated = _translate(invalid.value, "mcp.test")
    assert isinstance(translated, McpProtocolError) and not isinstance(translated, McpRefused)


async def test_huge_output_is_cut_with_a_note(live_server: LiveServer) -> None:
    result = await call_tool(config(live_server), "chatty", {"size": HUGE}, network=TEST_NETWORK)

    assert result.truncated is True
    assert result.text.startswith("xxxx")
    assert result.text.endswith("[output cut at 256 KB]")
    assert len(result.text) < 256 * 1024 + 100


async def test_an_answer_over_the_byte_cap_is_refused(live_server: LiveServer) -> None:
    with pytest.raises(McpResponseTooLarge, match="larger than 64 KB"):
        await call_tool(
            config(live_server, max_response_bytes=64 * 1024), "chatty", {"size": HUGE}, network=TEST_NETWORK
        )


# The guard


async def test_an_off_origin_redirect_is_not_followed(live_server: LiveServer) -> None:
    before = len(live_server.recorder.requests)

    with pytest.raises(McpClientError, match="not followed"):
        await list_tools(config(live_server, url=live_server.url(path="/moved")), network=TEST_NETWORK)

    hosts = {r["host"].split(":")[0] for r in live_server.recorder.requests[before:]}
    assert hosts == {"mcp.test"}  # nothing ever went to other.test


async def test_a_private_address_is_refused_before_anything_is_sent(live_server: LiveServer) -> None:
    before = len(live_server.recorder.requests)
    production_but_http = McpNetwork(allow_private=False, allow_http=True, resolve=resolve_to_loopback)

    with pytest.raises(McpUnsafeUrl, match="private network"):
        await list_tools(config(live_server), network=production_but_http)

    assert len(live_server.recorder.requests) == before


async def test_plain_http_is_refused_outside_tests(live_server: LiveServer) -> None:
    before = len(live_server.recorder.requests)

    with pytest.raises(McpUnsafeUrl, match="https"):
        await list_tools(config(live_server))

    assert len(live_server.recorder.requests) == before


async def test_a_host_that_resolves_to_cloud_metadata_is_refused() -> None:
    async def metadata(_host: str) -> list[str]:
        return ["169.254.169.254"]

    with pytest.raises(McpUnsafeUrl, match="private network"):
        await list_tools(McpServerConfig(url="https://mcp.example/mcp"), network=McpNetwork(resolve=metadata))

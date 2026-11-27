"""The MCP client: list an MCP server's tools and call one, over Streamable HTTP, through the SSRF guard.

ADR 0012. The only module that imports the `mcp` SDK. Two operations:

- `list_tools(server)` → `McpListing`: every tool (all pages, at most `MAX_TOOLS`) as `McpToolInfo`,
  and the icons the server names for itself in the handshake (`McpIcon`; see `mcp/icons.py`);
- `call_tool(server, name, args)` → `McpCallResult`: text for the model plus `is_error`.

What callers get for free:

- **The guard** (`_guard.py`): private and loopback addresses refused (unless the network policy
  allows them), the checked IP is the IP connected to, https only, no request leaves the server's
  origin, and an off-origin redirect is never followed (the SDK follows only same-origin 307/308).
- **Limits**: connect timeout, a whole-operation timeout, a response body cap, a cap on the text
  a result hands to the model (`MAX_RESULT_TEXT`, cut with a note).
- **The protocol**: the SDK's `auto` mode speaks 2026-07-28 and falls back to the handshake
  versions. Sampling, elicitation and roots are never offered; a tool that asks for input fails.
- **Errors**: everything that goes wrong is an `McpClientError` subclass with a message that's safe
  for people and the model. A tool that ran and failed is not an error: it's `is_error=True`. Of
  the MCP errors a call can get, only `McpRefused` (method not found, invalid params) says the tool
  didn't run; any other `McpProtocolError` may come after it did.

Each operation opens its own connection (stateless): no session outlives a call.

OAuth (slice 7.3): a server that answers 401 raises `McpAuthRequired` with its challenge, and
403 `insufficient_scope` raises `McpInsufficientScope`; once signed in, the access token goes in
`headers` like a header key (`services/mcp_server_service.py` refreshes it first). The SDK's
`OAuthClientProvider` isn't used (ADR 0016): its discovery and token requests would go through
this origin-locked transport, and our callback, vault and refresh lease already exist (5.3).
`McpServerConfig.auth` stays as a seam.
"""

import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx2
import mcp_types
from mcp.client import Client, InputRequiredRoundsExceededError
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from src.core.errors import AppError
from src.core.url_guard import Resolver, resolve_host
from src.mcp._guard import GuardedTransport, GuardRefused, ResponseTooLarge

logger = logging.getLogger(__name__)

MAX_TOOLS = 200
MAX_RESULT_TEXT = 256 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CALL_TIMEOUT = 300.0
CLIENT_INFO = mcp_types.Implementation(name="botdesk", version="0.1.0")
# JSON-RPC errors that mean the request was turned down before anything ran.
_REFUSALS = frozenset({mcp_types.METHOD_NOT_FOUND, mcp_types.INVALID_PARAMS})


# Errors


class McpClientError(AppError):
    """Talking to an MCP server failed. The message is safe for people and the model."""

    status_code = 502


class McpUnsafeUrl(McpClientError):
    """The guard refused the address: private network, plain http, or off the server's origin."""

    status_code = 400


class McpUnreachable(McpClientError):
    """The server couldn't be reached, or answered with something that isn't MCP."""


class McpTimeout(McpClientError):
    """The server took longer than the timeout."""

    status_code = 504


class McpResponseTooLarge(McpClientError):
    """The server's answer is over `max_response_bytes`."""


class McpAuthRequired(McpClientError):
    """The server answered 401: it wants an OAuth sign-in (slice 7.3), or the token it had was
    refused. `challenge` is its `WWW-Authenticate` header (not a secret: where to sign in)."""

    def __init__(self, message: str, challenge: str) -> None:
        super().__init__(message)
        self.challenge = challenge


class McpInsufficientScope(McpClientError):
    """The server answered 403 `insufficient_scope`: the token works but needs more access (MCP
    step-up authorization). `challenge` is its `WWW-Authenticate` header, naming the scopes."""

    def __init__(self, message: str, challenge: str) -> None:
        super().__init__(message)
        self.challenge = challenge


class McpProtocolError(McpClientError):
    """The server answered, but with an MCP error, or with something that isn't MCP, or the tool
    asked for input. For a call this can come after the tool did its thing (an internal error once
    the email is out): unless it's an `McpRefused`, whether the tool ran is unknown."""


class McpRefused(McpProtocolError):
    """The server refused the call before running anything: JSON-RPC "method not found" or
    "invalid params" (an unknown tool, arguments that don't fit). Nothing ran."""


# Inputs and outputs


@dataclass(frozen=True)
class McpServerConfig:
    """How to reach one MCP server. `headers` is header auth (`{"Authorization": "Bearer …"}` or
    `{"X-API-Key": …}`); `auth` is the OAuth seam (an `httpx2.Auth`, slice 7.3)."""

    url: str
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    auth: httpx2.Auth | None = field(default=None, repr=False)
    connect_timeout: float = 10.0
    call_timeout: float = 60.0
    max_response_bytes: int = MAX_RESPONSE_BYTES


@dataclass(frozen=True)
class McpNetwork:
    """Where the client may connect. The default is production: public https only.
    `allow_private` is `ALLOW_PRIVATE_MCP_URLS`; `allow_http` is for tests only."""

    allow_private: bool = False
    allow_http: bool = False
    resolve: Resolver = resolve_host


PUBLIC_ONLY = McpNetwork()


@dataclass(frozen=True)
class McpToolInfo:
    """One tool as the server describes it. Everything here is the server's own (untrusted) text."""

    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]


@dataclass(frozen=True)
class McpIcon:
    """An icon the server names for itself in the handshake (`serverInfo.icons`, MCP 2025-11-25).
    The server's own (untrusted) words: `mcp/icons.py` decides whether to fetch it."""

    src: str  # an https address or a data: URI
    mime_type: str | None
    sizes: tuple[str, ...]  # "48x48", "any"…
    theme: str | None  # "light" | "dark": the background it's drawn for


@dataclass(frozen=True)
class McpListing:
    """What listing a server finds: its tools, and its icons."""

    tools: list[McpToolInfo]
    icons: list[McpIcon]


@dataclass(frozen=True)
class McpCallResult:
    """What a tool call gives the model. `is_error`: the tool ran and reported a failure."""

    text: str
    is_error: bool
    truncated: bool


# Operations


async def list_tools(server: McpServerConfig, *, network: McpNetwork = PUBLIC_ONLY) -> McpListing:
    async def walk(client: Client) -> McpListing:
        tools: list[McpToolInfo] = []
        cursor: str | None = None
        while True:
            page = await client.list_tools(cursor=cursor)
            tools.extend(_tool_info(tool) for tool in page.tools)
            if len(tools) > MAX_TOOLS:
                raise McpProtocolError(f"The server lists more than {MAX_TOOLS} tools, the limit.")
            cursor = page.next_cursor
            if not cursor:
                return McpListing(tools, _icons(client.server_info))

    return await _with_client(server, network, walk)


async def call_tool(
    server: McpServerConfig, name: str, args: Mapping[str, Any], *, network: McpNetwork = PUBLIC_ONLY
) -> McpCallResult:
    async def call(client: Client) -> McpCallResult:
        try:
            result = await client.call_tool(name, dict(args), read_timeout_seconds=_call_timeout(server))
        except InputRequiredRoundsExceededError as error:
            raise McpProtocolError(
                f"The tool {name} asked for more input (elicitation or sampling), which BotDesk doesn't support."
            ) from error
        return _to_result(result)

    return await _with_client(server, network, call)


# Inside


MAX_ICONS = 8  # of a server's own icons, the most considered


def _icons(info: Any) -> list[McpIcon]:
    """The icons in the server's handshake, if it names any (servers before 2025-11-25 don't)."""
    icons = getattr(info, "icons", None) or []
    return [
        McpIcon(
            src=str(icon.src),
            mime_type=icon.mime_type,
            sizes=tuple(str(size) for size in icon.sizes or ()),
            theme=icon.theme,
        )
        for icon in icons[:MAX_ICONS]
        if isinstance(getattr(icon, "src", None), str)
    ]


def _call_timeout(server: McpServerConfig) -> float:
    return min(server.call_timeout, MAX_CALL_TIMEOUT)


async def _with_client[T](
    server: McpServerConfig, network: McpNetwork, operation: Callable[[Client], Awaitable[T]]
) -> T:
    url = _checked_url(server.url, network)
    call_timeout = _call_timeout(server)
    # A 401's or 403's WWW-Authenticate: the SDK only reports "an error response".
    refused: list[tuple[int, str]] = []

    async def on_response(response: httpx2.Response) -> None:
        if response.status_code in (401, 403) and not refused:
            refused.append((response.status_code, response.headers.get("www-authenticate", "")[:2000]))

    transport = GuardedTransport(
        server_url=url,
        allow_private=network.allow_private,
        allow_http=network.allow_http,
        resolve=network.resolve,
        max_bytes=server.max_response_bytes,
    )
    http = httpx2.AsyncClient(
        transport=transport,
        headers=dict(server.headers),
        auth=server.auth,
        timeout=httpx2.Timeout(call_timeout, connect=server.connect_timeout),
        follow_redirects=False,
        trust_env=False,
        event_hooks={"response": [on_response]},
    )
    try:
        # One deadline for the whole operation (connect, handshake, all pages / the call).
        with anyio.fail_after(server.connect_timeout + call_timeout):
            async with (
                http,
                Client(
                    streamable_http_client(str(url), http_client=http, max_sse_event_size=server.max_response_bytes),
                    read_timeout_seconds=call_timeout,
                    client_info=CLIENT_INFO,
                    input_required_max_rounds=0,  # elicitation / sampling / roots: never answered
                    cache=None,
                ) as client,
            ):
                return await operation(client)
    except Exception as error:
        status, challenge = refused[0] if refused else (0, "")
        if status == 401:
            raise McpAuthRequired(f"{url.host} needs signing in.", challenge) from error
        if status == 403 and "insufficient_scope" in challenge.lower():
            raise McpInsufficientScope(f"{url.host} needs more access.", challenge) from error
        raise _translate(error, url.host) from error


def _checked_url(raw: str, network: McpNetwork) -> httpx2.URL:
    try:
        url = httpx2.URL(raw.strip())
    except httpx2.InvalidURL as error:
        raise McpUnsafeUrl("That isn't a valid address.") from error
    allowed = ("https", "http") if network.allow_http else ("https",)
    if url.scheme not in allowed or not url.host:
        raise McpUnsafeUrl("Use an address that starts with https://.")
    if url.userinfo:
        raise McpUnsafeUrl("Leave the user name and password out of the address; use header auth instead.")
    return url


def _leaves(error: BaseException) -> list[BaseException]:
    """The SDK runs requests in task groups, so a failure can arrive wrapped in exception groups."""
    if isinstance(error, BaseExceptionGroup):
        return [leaf for inner in error.exceptions for leaf in _leaves(inner)]
    return [error]


def _translate(error: Exception, host: str) -> McpClientError:
    leaves = _leaves(error)
    # Most specific first: our own refusals beat the timeouts and protocol errors they cause.
    for leaf in leaves:
        if isinstance(leaf, McpClientError):
            return leaf
        if isinstance(leaf, GuardRefused):
            return McpUnsafeUrl(str(leaf))
        if isinstance(leaf, ResponseTooLarge):
            return McpResponseTooLarge(str(leaf))
    for leaf in leaves:
        # The SDK's own request timeout races httpx2's read timeout; either one is a timeout.
        timed_out = isinstance(leaf, MCPError) and leaf.error.code == mcp_types.REQUEST_TIMEOUT
        if timed_out or isinstance(leaf, TimeoutError | httpx2.TimeoutException):
            return McpTimeout(f"{host} took too long to answer.")
        if isinstance(leaf, MCPError):
            refused = leaf.error.code in _REFUSALS
            return (McpRefused if refused else McpProtocolError)(f"{host} answered with an error: {leaf.error.message}")
        if isinstance(leaf, httpx2.HTTPError):
            return McpUnreachable(f"Couldn't reach {host} ({type(leaf).__name__}).")
        if isinstance(leaf, ValidationError):
            return McpProtocolError(f"{host} sent an answer that isn't valid MCP.")
    logger.warning("MCP call to %s failed unexpectedly", host, exc_info=error)
    return McpUnreachable(f"Couldn't talk to {host} ({type(leaves[0]).__name__}).")


def _tool_info(tool: mcp_types.Tool) -> McpToolInfo:
    return McpToolInfo(
        name=tool.name,
        title=tool.title,
        description=tool.description,
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        annotations=tool.annotations.model_dump(exclude_none=True) if tool.annotations else {},
    )


def _to_result(result: mcp_types.CallToolResult) -> McpCallResult:
    """ADR 0012 §6: structured content if present, else the text parts; media omitted, links shown
    as text and never fetched, embedded resources contribute their text; cut at `MAX_RESULT_TEXT`."""
    if result.structured_content is not None:
        text = json.dumps(result.structured_content, ensure_ascii=False)
    else:
        text = "\n".join(_block_text(block) for block in result.content)
    truncated = len(text) > MAX_RESULT_TEXT
    if truncated:
        text = text[:MAX_RESULT_TEXT] + f"\n[output cut at {MAX_RESULT_TEXT // 1024} KB]"
    return McpCallResult(text=text, is_error=result.is_error, truncated=truncated)


def _block_text(block: mcp_types.ContentBlock) -> str:
    match block:
        case mcp_types.TextContent():
            return block.text
        case mcp_types.ImageContent():
            return "[image omitted]"
        case mcp_types.AudioContent():
            return "[audio omitted]"
        case mcp_types.ResourceLink():
            return f"[link: {block.name} {block.uri}]"
        case mcp_types.EmbeddedResource():
            resource = block.resource
            if isinstance(resource, mcp_types.TextResourceContents):
                return resource.text
            return f"[file omitted: {resource.uri}]"
    return f"[{block.type} omitted]"

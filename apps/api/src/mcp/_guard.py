"""The SSRF guard for MCP traffic: `core/url_guard.py` ported from httpx/httpcore to httpx2/httpcore2,
which is what the `mcp` SDK is built on (ADR 0012 §7, slice 7.1 spike).

The address checks (`safe_addresses`) are shared with model servers. What's here:

- `PinnedNetworkBackend`: resolves the host once, checks every address, connects to a checked IP.
  TLS (SNI, certificate) and the Host header still use the name, because httpcore2 takes them
  from the URL, not the socket. Same reasoning as `core/url_guard.py` (DNS rebinding).
- `GuardedTransport`: httpx2's normal transport with that backend underneath, plus three rules the
  model-server guard doesn't need:
  1. **one origin**: a request to any other scheme, host or port is refused before it leaves.
     The SDK already refuses off-origin redirects; this makes it true whatever the SDK does.
     (Slice 7.3, OAuth: discovery and token requests go to the authorization server, so the
     OAuth flow will need its own guarded client, or this origin list widened to the
     discovered, checked authorization-server origin.)
  2. **https only**, unless the network policy allows plain http (tests);
  3. **a size cap**: a response body larger than `max_bytes` fails mid-stream.
"""

from collections.abc import AsyncIterator, Iterable

import httpcore2
import httpx2

from src.core import url_guard
from src.core.url_guard import Resolver, UnsafeUrl, safe_addresses

PRIVATE_NETWORK = (
    "That MCP server's address is on a private network, which this server doesn't allow. "
    "Self-hosting? Set ALLOW_PRIVATE_MCP_URLS=true."
)


class GuardRefused(Exception):
    """The guard refused a request. `str()` is safe to show to people and to the model."""


class ResponseTooLarge(Exception):
    """A response body went past the size cap."""


class PinnedNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(self, *, allow_private: bool, resolve: Resolver) -> None:
        self.allow_private = allow_private
        self.resolve = resolve
        self.inner = httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore2's interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        try:
            addresses = await safe_addresses(host, allow_private=self.allow_private, resolve=self.resolve)
        except UnsafeUrl as error:
            message = PRIVATE_NETWORK if error.message == url_guard.PRIVATE_NETWORK else error.message
            raise GuardRefused(message) from error
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self.inner.connect_tcp(
                    address, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout) as error:
                last_error = error
        assert last_error is not None  # `safe_addresses` never returns an empty list
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore2's interface
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise GuardRefused("MCP servers are reached over TCP only.")

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


def origin(url: httpx2.URL) -> tuple[str, str, int]:
    default = 443 if url.scheme == "https" else 80
    return (url.scheme, url.host, url.port or default)


class _CappedStream(httpx2.AsyncByteStream):
    def __init__(self, inner: httpx2.AsyncByteStream, max_bytes: int, host: str) -> None:
        self._inner = inner
        self._max_bytes = max_bytes
        self._host = host

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in self._inner:
            size += len(chunk)
            if size > self._max_bytes:
                raise ResponseTooLarge(f"{self._host}'s answer is larger than {self._max_bytes // 1024} KB, the limit.")
            yield chunk

    async def aclose(self) -> None:
        await self._inner.aclose()


class GuardedTransport(httpx2.AsyncHTTPTransport):
    """Every request to one MCP server goes through this. `trust_env=False`: a proxy from the
    environment would decide where the connection goes instead of the pinned backend."""

    def __init__(
        self,
        *,
        server_url: httpx2.URL,
        allow_private: bool,
        allow_http: bool,
        resolve: Resolver,
        max_bytes: int,
    ) -> None:
        super().__init__(trust_env=False)
        limits = httpx2.Limits(max_connections=10, max_keepalive_connections=5)
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpx2.create_ssl_context(trust_env=False),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=PinnedNetworkBackend(allow_private=allow_private, resolve=resolve),
        )
        self._origin = origin(server_url)
        self._allow_http = allow_http
        self._max_bytes = max_bytes

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.scheme != "https" and not (self._allow_http and request.url.scheme == "http"):
            raise GuardRefused("MCP servers must use https.")
        if origin(request.url) != self._origin:
            raise GuardRefused(f"Refused a request to {request.url.host}: it isn't the MCP server's address.")
        response = await super().handle_async_request(request)
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_bytes:
            await response.aclose()
            raise ResponseTooLarge(
                f"{request.url.host}'s answer is larger than {self._max_bytes // 1024} KB, the limit."
            )
        assert isinstance(response.stream, httpx2.AsyncByteStream)
        return httpx2.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_CappedStream(response.stream, self._max_bytes, request.url.host),
            extensions=response.extensions,
        )

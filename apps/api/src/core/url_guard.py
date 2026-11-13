"""Checks the address of a custom (OpenAI-compatible) model server, and connects to it safely.

The API makes requests to whatever address an admin types in, so without a guard anyone with an
admin role could make the server call its own private network (SSRF): a cloud metadata service
at 169.254.169.254, a database admin page, another tenant's service. So:

- only http and https, with no user name or password in the address;
- the host must resolve only to public addresses (no private, loopback, link-local, shared or
  reserved ones). This is on everywhere, development included; a machine that runs its model
  server on its own network (Ollama on localhost) opts out with ALLOW_PRIVATE_MODEL_URLS=true;
- redirects are never followed, so a public server can't bounce a request (with the
  conversation and the key in it) to a private one.

Two layers do this:

1. `check_base_url` runs when a key is saved and before a run starts, and turns a bad address
   into a message people can act on.
2. `GuardedTransport` is the httpx transport every call to a custom server goes through. It
   resolves the host once, checks every address, and connects to the checked address itself.
   Checking and then letting httpx resolve the name again would leave a gap (DNS rebinding):
   a name with a very short TTL can answer "public" to the check and "127.0.0.1" a moment
   later to the connection. Here the address that was checked is the address connected to,
   while the Host header and TLS (SNI and the certificate check) still use the original host
   name, because httpcore takes those from the URL, not from the socket.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable

import httpcore
import httpx

from src.core.errors import BadRequest

Resolver = Callable[[str], Awaitable[list[str]]]

PRIVATE_NETWORK = (
    "That address is on a private network, which this server doesn't allow. "
    "Self-hosting? Set ALLOW_PRIVATE_MODEL_URLS=true."
)


class UnsafeUrl(BadRequest):
    """The address can't be used for a model server."""


async def resolve_host(host: str) -> list[str]:
    """Every IP address the host name resolves to."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone like "%eth0"
    return ip.is_global and not ip.is_multicast


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return True


async def safe_addresses(host: str, *, allow_private: bool, resolve: Resolver = resolve_host) -> list[str]:
    """The addresses `host` may be reached at: all of them public, or `UnsafeUrl`.

    One private address among public ones is enough to refuse: which one a connection picks is
    up to the resolver's order, so a mix can't be trusted."""
    host = host.strip("[]")  # an IPv6 literal from a URL: "[::1]"
    try:
        addresses = [host] if _is_ip(host) else await resolve(host)
    except OSError as error:
        raise UnsafeUrl(f"We couldn't find {host}.") from error
    if not addresses:
        raise UnsafeUrl(f"We couldn't find {host}.")
    if not allow_private and not all(_is_public(address) for address in addresses):
        raise UnsafeUrl(PRIVATE_NETWORK)
    return addresses


async def check_base_url(url: str, *, allow_private: bool, resolve: Resolver = resolve_host) -> str:
    """The URL without a trailing slash, or `UnsafeUrl` with a message people can act on."""
    cleaned = url.strip().rstrip("/")
    try:
        # httpx's own parser, so the host checked here is the host httpx will call.
        parts = httpx.URL(cleaned)
    except httpx.InvalidURL:
        parts = None
    if parts is None or parts.scheme not in ("http", "https") or not parts.host:
        raise UnsafeUrl("Use an address that starts with http:// or https://.")
    if parts.username or parts.password:
        raise UnsafeUrl("Leave the user name and password out of the address; put a key in the API key field.")
    if not allow_private:
        await safe_addresses(parts.host, allow_private=False, resolve=resolve)
    return cleaned


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Opens TCP connections only to addresses the guard approved, and to exactly those.

    httpcore asks the backend to connect to the URL's host name. Instead of handing the name to
    the operating system (which would resolve it again), this resolves it once, checks every
    address, and connects to a checked IP. TLS runs afterwards on the stream with the original
    host name, so certificates are still checked against the name, not the IP."""

    def __init__(
        self,
        *,
        allow_private: bool,
        resolve: Resolver = resolve_host,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self.allow_private = allow_private
        self.resolve = resolve
        self.inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            async with asyncio.timeout(timeout):
                addresses = await safe_addresses(host, allow_private=self.allow_private, resolve=self.resolve)
        except TimeoutError as error:
            raise httpcore.ConnectTimeout(f"looking up {host} took too long") from error
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self.inner.connect_tcp(
                    address, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
        assert last_error is not None  # `safe_addresses` never returns an empty list
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """A model server is always a URL; a Unix socket would skip the address check."""
        raise UnsafeUrl("Model servers are reached over TCP only.")

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)  # httpx's own defaults


class GuardedTransport(httpx.AsyncHTTPTransport):
    """httpx's normal transport (connection pool, HTTP/1.1, TLS), with `PinnedNetworkBackend`
    underneath. Use it for every request to a custom model server, with `follow_redirects=False`
    on the client.

    `httpx.AsyncHTTPTransport` doesn't take a network backend, so the pool is rebuilt here with
    the same settings httpx uses. `trust_env=False`: a proxy from the environment would make
    the proxy, not this backend, decide where the connection goes."""

    def __init__(
        self,
        *,
        allow_private: bool,
        resolve: Resolver = resolve_host,
        inner: httpcore.AsyncNetworkBackend | None = None,
        limits: httpx.Limits = DEFAULT_LIMITS,
    ) -> None:
        super().__init__(trust_env=False, limits=limits)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=PinnedNetworkBackend(allow_private=allow_private, resolve=resolve, inner=inner),
        )

"""Checks the base URL of a custom (OpenAI-compatible) model server before the API calls it.

The API makes requests to whatever address an admin types in, so without a check anyone with an
admin role could make the server call its own private network (SSRF): a cloud metadata service,
a database admin page, another tenant's service. So:

- only http and https, with no user name or password in the address;
- in production, the host must resolve only to public addresses (no private, loopback,
  link-local, shared or reserved ones) unless ALLOW_PRIVATE_MODEL_URLS=true;
- outside production anything goes, so Ollama on localhost works.

The check runs when the key is saved and again before every call, so a DNS name that later
points somewhere private is caught then. Redirects are never followed (httpx's default).
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from src.core.errors import BadRequest

Resolver = Callable[[str], Awaitable[list[str]]]


class UnsafeUrl(BadRequest):
    """The address can't be used for a model server."""


async def resolve_host(host: str) -> list[str]:
    """Every IP address the host name resolves to."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone like "%eth0"
    return ip.is_global and not ip.is_multicast


async def check_base_url(url: str, *, allow_private: bool, resolve: Resolver = resolve_host) -> str:
    """The URL without a trailing slash, or `UnsafeUrl` with a message people can act on."""
    cleaned = url.strip().rstrip("/")
    parts = urlsplit(cleaned)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrl("Use an address that starts with http:// or https://.")
    if parts.username or parts.password:
        raise UnsafeUrl("Leave the user name and password out of the address; put a key in the API key field.")
    if allow_private:
        return cleaned
    try:
        addresses = [parts.hostname] if _is_ip(parts.hostname) else await resolve(parts.hostname)
    except OSError as error:
        raise UnsafeUrl(f"We couldn't find {parts.hostname}.") from error
    if not addresses or not all(_is_public(address) for address in addresses):
        raise UnsafeUrl(
            "That address is on a private network, which this server doesn't allow. "
            "Self-hosting? Set ALLOW_PRIVATE_MODEL_URLS=true."
        )
    return cleaned


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True

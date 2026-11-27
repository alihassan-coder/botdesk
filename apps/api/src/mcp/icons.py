"""A server's own icon (MCP 2025-11-25: the `icons` in its handshake's `serverInfo`), kept as a small
data: URI, so the web shows it without anyone's browser ever calling the server's site.

- **Only from the server's own site:** the same host, or the same parent domain (mcp.notion.com may
  use notion.com). Any other address is skipped: the spec asks clients to check where icons come from.
- **Through the MCP guard** (`_guard.py`): https only (unless the network allows http, in tests), no
  private addresses, no redirects, at most `MAX_ICON_BYTES`.
- **Images only:** PNG, JPEG, WebP, GIF or SVG, by the type the server answers with. The web draws
  it in an <img>, where an SVG's scripts never run.
- A data: URI the server sends inline is checked the same way, without a fetch.
- **Never fails:** no icon is fine. The web falls back to the brand mark or a letter.
"""

import base64
import binascii
import ipaddress
import logging

import httpx2

from src.mcp._guard import GuardedTransport
from src.mcp.client import McpIcon, McpNetwork

logger = logging.getLogger(__name__)

MAX_ICON_BYTES = 64 * 1024
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"})
FETCH_SECONDS = 5.0
MAX_TRIES = 3  # icons fetched before giving up


async def fetch_icon(icons: list[McpIcon], server_url: str, network: McpNetwork) -> str | None:
    """The best of the server's icons as a data: URI, or None (none named, none allowed, none loaded)."""
    for icon in ranked(icons)[:MAX_TRIES]:
        try:
            found = inline(icon.src) if icon.src.startswith("data:") else await _fetch(icon.src, server_url, network)
        except Exception as error:  # an icon is never worth failing anything for
            logger.info("Skipped an MCP server icon: %s", type(error).__name__)
            continue
        if found:
            return found
    return None


def ranked(icons: list[McpIcon]) -> list[McpIcon]:
    """Best first: one drawn for any background (or a light one, the app's default), a vector, then
    the raster closest to 128 px (the web shows it at 32 to 40 px, so 64 to 128 is plenty for sharp screens)."""

    def score(icon: McpIcon) -> tuple[int, int, int]:
        theme = 0 if icon.theme in (None, "light") else 1
        vector = 0 if (icon.mime_type == "image/svg+xml" or "any" in icon.sizes) else 1
        return theme, vector, min((_size_distance(size) for size in icon.sizes), default=1000)

    return sorted((icon for icon in icons if _allowed_type(icon.mime_type)), key=score)


def same_site(icon_url: str, server_url: str) -> bool:
    """The icon is on the server's own site: the same host, or the same parent domain."""
    icon_host, server_host = httpx2.URL(icon_url).host.lower(), httpx2.URL(server_url).host.lower()
    if not icon_host or not server_host:
        return False
    if icon_host == server_host:
        return True
    if _is_ip(icon_host) or _is_ip(server_host):
        return False
    return _site(icon_host) == _site(server_host)


def inline(uri: str) -> str | None:
    """A data: URI the server sent, if it's a small image: rewritten as base64 data: URI."""
    header, comma, payload = uri.partition(",")
    if not comma or not header.startswith("data:"):
        return None
    parts = header.removeprefix("data:").split(";")
    mime, is_base64 = parts[0].lower(), "base64" in parts[1:]
    if mime not in IMAGE_TYPES:
        return None
    try:
        body = base64.b64decode(payload, validate=True) if is_base64 else payload.encode()
    except (binascii.Error, ValueError):
        return None
    return _data_uri(mime, body)


async def _fetch(src: str, server_url: str, network: McpNetwork) -> str | None:
    url = httpx2.URL(src)
    if url.scheme not in (("https", "http") if network.allow_http else ("https",)) or not same_site(src, server_url):
        return None
    transport = GuardedTransport(
        server_url=url,
        allow_private=network.allow_private,
        allow_http=network.allow_http,
        resolve=network.resolve,
        max_bytes=MAX_ICON_BYTES,
    )
    async with httpx2.AsyncClient(
        transport=transport, timeout=FETCH_SECONDS, follow_redirects=False, trust_env=False
    ) as http:
        response = await http.get(url, headers={"Accept": ", ".join(sorted(IMAGE_TYPES))})
    mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if response.status_code != 200 or mime not in IMAGE_TYPES:
        return None
    return _data_uri(mime, response.content)


def _data_uri(mime: str, body: bytes) -> str | None:
    if not body or len(body) > MAX_ICON_BYTES:
        return None
    return f"data:{mime};base64,{base64.b64encode(body).decode()}"


def _allowed_type(mime: str | None) -> bool:
    return mime is None or mime.lower() in IMAGE_TYPES  # no type named: the answer's type decides


def _size_distance(size: str) -> int:
    width, _, _ = size.lower().partition("x")
    return abs(int(width) - 128) if width.isdigit() else 1000


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _site(host: str) -> str:
    """The registrable part of a host, by a simple rule: the last two labels, or three when the
    second-to-last is a short country suffix part (example.co.uk)."""
    labels = host.rstrip(".").split(".")
    keep = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and len(labels[-2]) <= 3 else 2
    return ".".join(labels[-keep:])

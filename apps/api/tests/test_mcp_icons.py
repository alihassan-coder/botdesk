"""A server's own icon (MCP 2025-11-25 `serverInfo.icons`), kept as a data: URI (`mcp/icons.py`):
only from the server's own site, only small images, never failing anything."""

import base64
from urllib.parse import quote

import pytest

from src.mcp.client import McpIcon
from src.mcp.icons import MAX_ICON_BYTES, fetch_icon, inline, ranked, same_site
from tests import test_mcp_client
from tests.test_mcp_client import PNG, PNG_URI, TEST_NETWORK, LiveServer

live_server = test_mcp_client.live_server  # the client tests' MCP server, with /icon.png, /big.png, /page


def icon(src: str, *, mime: str | None = None, sizes: tuple[str, ...] = (), theme: str | None = None) -> McpIcon:
    return McpIcon(src=src, mime_type=mime, sizes=sizes, theme=theme)


async def test_fetches_an_icon_on_the_servers_own_site(live_server: LiveServer) -> None:
    found = await fetch_icon([icon(live_server.url(path="/icon.png"))], live_server.url(), TEST_NETWORK)
    assert found == PNG_URI


async def test_skips_an_icon_on_another_site(live_server: LiveServer) -> None:
    other = icon(live_server.url(host="other.test", path="/icon.png"))
    assert await fetch_icon([other], live_server.url(), TEST_NETWORK) is None


async def test_skips_what_isnt_a_small_image_and_tries_the_next(live_server: LiveServer) -> None:
    url = live_server.url
    assert await fetch_icon([icon(url(path="/big.png"))], url(), TEST_NETWORK) is None  # over 64 KB
    assert await fetch_icon([icon(url(path="/page"))], url(), TEST_NETWORK) is None  # text/html
    assert await fetch_icon([icon(url(path="/missing.png"))], url(), TEST_NETWORK) is None  # 404
    assert await fetch_icon([icon(url(path="/gzipped.png"))], url(), TEST_NETWORK) is None  # compressed
    tries = [icon(url(path="/page"), sizes=("128x128",)), icon(url(path="/icon.png"), sizes=("16x16",))]
    assert await fetch_icon(tries, url(), TEST_NETWORK) == PNG_URI


async def test_takes_an_inline_icon_without_a_fetch() -> None:
    assert await fetch_icon([icon(PNG_URI)], "https://mcp.example.com/mcp", TEST_NETWORK) == PNG_URI


def test_inline_icons_are_small_images_only() -> None:
    assert inline(PNG_URI) == PNG_URI
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    expected = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
    assert inline("data:image/svg+xml," + svg.decode()) == expected
    assert inline("data:image/svg+xml," + quote(svg.decode())) == expected  # percent-encoded
    assert inline("data:text/html;base64," + base64.b64encode(b"<script>x</script>").decode()) is None
    assert inline("data:image/png;base64,not base64!") is None
    big = base64.b64encode(PNG + b"0" * MAX_ICON_BYTES).decode()
    assert inline(f"data:image/png;base64,{big}") is None


@pytest.mark.parametrize(
    ("icon_url", "server_url", "same"),
    [
        ("https://mcp.notion.com/icon.png", "https://mcp.notion.com/mcp", True),
        ("https://notion.com/favicon.png", "https://mcp.notion.com/mcp", True),  # its parent domain
        ("https://www.notion.com/favicon.png", "https://mcp.notion.com/mcp", True),  # or www. of it
        ("https://cdn.notion.com/x.png", "https://mcp.notion.com/mcp", False),  # a sibling: not taken
        ("https://other.vercel.app/i.png", "https://evil.vercel.app/mcp", False),  # another tenant's site
        ("https://github.com/favicon.ico", "https://api.githubcopilot.com/mcp/", False),
        ("https://cdn.evil.example/x.png", "https://mcp.notion.com/mcp", False),
        ("https://example.co.uk/i.png", "https://mcp.example.co.uk/mcp", True),
        ("https://other.co.uk/i.png", "https://mcp.example.co.uk/mcp", False),  # co.uk isn't a site
        ("https://10.0.0.5/i.png", "https://10.0.0.6/mcp", False),
    ],
)
def test_same_site(icon_url: str, server_url: str, same: bool) -> None:
    assert same_site(icon_url, server_url) is same


def test_ranks_any_background_then_vector_then_closest_to_128px() -> None:
    dark = icon("https://a.test/dark.svg", mime="image/svg+xml", theme="dark")
    small = icon("https://a.test/16.png", mime="image/png", sizes=("16x16",))
    good = icon("https://a.test/128.png", mime="image/png", sizes=("128x128",))
    vector = icon("https://a.test/logo.svg", mime="image/svg+xml")
    other = icon("https://a.test/logo.bmp", mime="image/bmp")  # a type BotDesk doesn't show
    assert ranked([dark, small, good, vector, other]) == [vector, good, small, dark]

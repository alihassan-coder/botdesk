"""The Browser tools in a real Local browser (ADR 0017 §4), on a small page served from this test.

Needs Chrome (or Playwright's Chromium): skipped where neither is installed. Private addresses
are allowed here because the test page is on 127.0.0.1; the refusal itself is tested last.
"""

import logging
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from botdesk_plugin_sdk import NotDone, ToolContext

from src.browser.local import NOT_INSTALLED, BrowserUnavailable, LocalBrowsers, LocalBrowserSettings
from src.services.browser_tools import BrowserTools
from tests.conftest import TEST_SETTINGS

HOME = """<!doctype html><title>Acme</title>
<h1>Acme</h1><p>Welcome to Acme.</p>
<a href="/pricing.html">Pricing</a>
<form action="/search.html" method="get"><input type="search" name="q" aria-label="Search"></form>
<form action="/order" method="post"><input name="qty" aria-label="Quantity"><button>Buy now</button></form>
<input type="password" aria-label="Password">"""
PRICING = "<!doctype html><title>Pricing</title><p>Free forever.</p>"
SEARCH = "<!doctype html><title>Search</title><p>Results</p>"


@pytest.fixture
def site(tmp_path: Path) -> Iterator[str]:
    for name, html in (("index.html", HOME), ("pricing.html", PRICING), ("search.html", SEARCH)):
        (tmp_path / name).write_text(html, encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _browsers(tmp_path: Path, *, allow_private: bool) -> LocalBrowsers:
    return LocalBrowsers(
        LocalBrowserSettings(
            profiles_dir=tmp_path / "profiles",
            channel="chrome",
            allow_private=allow_private,
            idle_minutes=5,
            max_sessions=2,
        )
    )


def _ctx() -> ToolContext:
    return ToolContext(
        org_id=uuid.uuid4(),
        bot_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        tool_call_id="call-1",
        idempotency_key="key",
        logger=logging.getLogger("test"),
    )


@pytest.fixture
async def tools(tmp_path: Path) -> AsyncIterator[BrowserTools]:
    browsers = _browsers(tmp_path, allow_private=True)
    # Screenshots need the database; these tests don't take any.
    yield BrowserTools(browsers, None, TEST_SETTINGS, None)  # type: ignore[arg-type]
    await browsers.close()


async def _open_or_skip(tools: BrowserTools, ctx: ToolContext, url: str) -> dict[str, object]:
    try:
        return await tools.open(ctx, url=url)
    except BrowserUnavailable as error:
        if str(error) == NOT_INSTALLED:
            pytest.skip("No Chrome or Chromium on this machine")
        raise


async def test_a_bot_reads_a_page_and_follows_links_and_searches(tools: BrowserTools, site: str) -> None:
    ctx = _ctx()
    page = await _open_or_skip(tools, ctx, f"{site}/index.html")
    assert page["title"] == "Acme"
    assert "Welcome to Acme." in str(page["text"])
    assert page["elements"] == [
        f'[1] link "Pricing" → {site}/pricing.html',
        '[2] search box "Search"',
        '[3] text box "Quantity"',
        '[4] button "Buy now"',
        '[5] password field "Password"',
    ]

    pricing = await tools.follow(ctx, ref=1)
    assert pricing["title"] == "Pricing"

    await tools.back(ctx)
    results = await tools.search(ctx, ref=2, text="plans")
    assert str(results["url"]).endswith("/search.html?q=plans")


async def test_reading_tools_refuse_what_would_change_something(tools: BrowserTools, site: str) -> None:
    ctx = _ctx()
    await _open_or_skip(tools, ctx, f"{site}/index.html")
    with pytest.raises(NotDone, match="is a button, not a link"):
        await tools.follow(ctx, ref=4)
    with pytest.raises(NotDone, match="not a search box"):
        await tools.search(ctx, ref=3, text="2")


async def test_clicks_must_match_what_people_approved_and_passwords_are_never_typed(
    tools: BrowserTools, site: str
) -> None:
    ctx = _ctx()
    await _open_or_skip(tools, ctx, f"{site}/index.html")
    with pytest.raises(NotDone, match='is the button "Buy now", not the Cancel button'):
        await tools.click(ctx, ref=4, what="the Cancel button")
    with pytest.raises(NotDone, match="password field"):
        await tools.type(ctx, ref=5, text="hunter2", field="Password", submit=False)

    typed = await tools.type(ctx, ref=3, text="2", field="Quantity", submit=False)
    assert typed["title"] == "Acme"


async def test_the_local_browser_refuses_the_servers_own_network(tmp_path: Path, site: str) -> None:
    browsers = _browsers(tmp_path, allow_private=False)
    tools = BrowserTools(browsers, None, TEST_SETTINGS, None)  # type: ignore[arg-type]
    try:
        with pytest.raises(NotDone, match="private network"):
            await _open_or_skip(tools, _ctx(), f"{site}/index.html")
    finally:
        await browsers.close()

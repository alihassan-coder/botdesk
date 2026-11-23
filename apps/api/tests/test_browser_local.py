"""The Browser tools in a real Local browser (ADR 0017 §4), through the app's own registry as a run
calls them, on a small page served from this test.

Needs Chrome (or Playwright's Chromium): skipped where neither is installed. Private addresses
are allowed here because the test page is on 127.0.0.1; the refusal itself is tested last.
"""

import logging
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from botdesk_plugin_sdk import NotDone, ToolContext
from fastapi import FastAPI

from src.browser.browsers import NOT_INSTALLED, BrowserUnavailable
from src.core.config import Settings
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

HOME = """<!doctype html><title>Acme</title>
<h1>Acme</h1><p>Welcome to Acme.</p>
<a href="/pricing.html">Pricing</a>
<form action="/search.html" method="get"><input type="search" name="q" aria-label="Search"></form>
<form action="/order" method="post"><input name="qty" aria-label="Quantity"><button>Buy now</button></form>
<input type="password" aria-label="Password">
<form action="/subscribe" method="get"><input name="email" aria-label="Newsletter">
<button formmethod="post">Subscribe</button></form>"""
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


@dataclass
class Browsing:
    """A bot in a run of its own, calling the Browser tools."""

    app: FastAPI
    ctx: ToolContext

    async def call(self, tool: str, **args: Any) -> dict[str, Any]:
        registered = self.app.state.runs.registry.get(f"browser.{tool}")
        assert registered is not None
        result: dict[str, Any] = await registered.spec.handler(registered.spec.args_model(**args), self.ctx)
        return result

    async def open_or_skip(self, url: str) -> dict[str, Any]:
        try:
            return await self.call("open", url=url)
        except BrowserUnavailable as error:
            if str(error) == NOT_INSTALLED:
                pytest.skip("No Chrome or Chromium on this machine")
            raise


async def _browsing(settings: Settings) -> AsyncIterator[Browsing]:
    async with api_client(settings, FakeProviders()) as (app, client):
        me = await sign_up(client)
        org_id = me["organizations"][0]["id"]
        org = f"/api/v1/orgs/{org_id}"
        bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
        thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
        run_id = (await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Hi"})).json()["runIds"][0]
        ctx = ToolContext(
            org_id=uuid.UUID(org_id),
            bot_id=uuid.UUID(bot["id"]),
            run_id=uuid.UUID(run_id),
            tool_call_id="call-1",
            idempotency_key=f"{run_id}:call-1",
            logger=logging.getLogger("test"),
        )
        yield Browsing(app, ctx)


@pytest.fixture
async def scout() -> AsyncIterator[Browsing]:
    async for browsing in _browsing(TEST_SETTINGS):
        yield browsing


async def test_a_bot_reads_a_page_and_follows_links_and_searches(scout: Browsing, site: str) -> None:
    page = await scout.open_or_skip(f"{site}/index.html")
    assert page["title"] == "Acme"
    assert "Welcome to Acme." in str(page["text"])
    assert page["elements"] == [
        f'[1] link "Pricing" → {site}/pricing.html',
        '[2] search box "Search"',
        '[3] text box "Quantity"',
        '[4] button "Buy now"',
        '[5] password field "Password"',
        '[6] text box "Newsletter"',
        '[7] button "Subscribe"',
    ]

    pricing = await scout.call("follow", ref=1)
    assert pricing["title"] == "Pricing"

    await scout.call("back")
    results = await scout.call("search", ref=2, text="plans")
    assert str(results["url"]).endswith("/search.html?q=plans")

    shot = await scout.call("screenshot", path="checks/search.png")
    assert (shot["saved"], shot["size"] > 0) == ("botdesk/scout/checks/search.png", True)


async def test_reading_tools_refuse_what_would_change_something(scout: Browsing, site: str) -> None:
    await scout.open_or_skip(f"{site}/index.html")
    with pytest.raises(NotDone, match="is a button, not a link"):
        await scout.call("follow", ref=4)
    with pytest.raises(NotDone, match="not a search box"):
        await scout.call("search", ref=3, text="2")
    # A GET form whose button posts: Enter would post, so it isn't a search.
    with pytest.raises(NotDone, match="not a search box"):
        await scout.call("search", ref=6, text="ali@acme.dev")


async def test_clicks_must_match_what_people_approved_and_passwords_are_never_typed(scout: Browsing, site: str) -> None:
    await scout.open_or_skip(f"{site}/index.html")
    with pytest.raises(NotDone, match='is the button "Buy now", not the Cancel button'):
        await scout.call("click", ref=4, what="the Cancel button")
    with pytest.raises(NotDone, match="password field"):
        await scout.call("type", ref=5, text="hunter2", field="Password", submit=False)

    typed = await scout.call("type", ref=3, text="2", field="Quantity", submit=False)
    assert typed["title"] == "Acme"


async def test_reading_before_opening_says_to_open_first(scout: Browsing) -> None:
    with pytest.raises(NotDone, match="Open one first"):
        await scout.call("read")


async def test_the_local_browser_refuses_the_servers_own_network(site: str) -> None:
    guarded = TEST_SETTINGS.model_copy(update={"allow_private_browser_urls": False})
    async for scout in _browsing(guarded):
        with pytest.raises(NotDone, match="private network"):
            await scout.open_or_skip(f"{site}/index.html")

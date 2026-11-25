"""The Brave Search plugin against a fake Brave API (no network): results as plain text, refusals
said plainly, and only Brave's host reachable."""

import pytest
from botdesk_plugin_sdk import NotDone, validate_manifest
from botdesk_plugin_sdk.testing import FakeHttp, call_tool, make_context

from botdesk_brave_search import API, brave_search_plugin

ANSWER = {
    "web": {
        "results": [
            {
                "title": "BotDesk &amp; friends",
                "url": "https://botdesk.dev/",
                "description": "Open-source <strong>AI</strong> bots for teams.",
                "age": "2 days ago",
            },
            {"title": "Second", "url": "https://example.com/2", "description": "More."},
            {"title": "No address"},
        ]
    }
}


def test_the_manifest_is_valid_and_the_key_goes_in_braves_header() -> None:
    plugin = validate_manifest(brave_search_plugin())
    assert plugin.auth is not None and plugin.egress == ("api.search.brave.com",)
    assert [(t.name, t.risk, t.untrusted_output) for t in plugin.tools] == [("search", "read", True)]


async def test_a_search_returns_plain_results() -> None:
    plugin = brave_search_plugin()
    http = FakeHttp(plugin)
    http.route("GET", API, json=ANSWER)

    result = await call_tool(
        plugin, "search", {"query": "botdesk", "count": 2, "freshness": "pw"}, make_context(http=http)
    )
    assert result == {
        "query": "botdesk",
        "results": [
            {
                "title": "BotDesk & friends",
                "url": "https://botdesk.dev/",
                "summary": "Open-source AI bots for teams.",
                "age": "2 days ago",
            },
            {"title": "Second", "url": "https://example.com/2", "summary": "More."},
        ],
    }
    assert http.requests[0].params == {"q": "botdesk", "count": "2", "freshness": "pw"}


@pytest.mark.parametrize(("status", "says"), [(401, "refused the key"), (429, "limit"), (500, "answered 500")])
async def test_refusals_say_what_to_do(status: int, says: str) -> None:
    plugin = brave_search_plugin()
    http = FakeHttp(plugin)
    http.route("GET", API, status=status, json={"error": "x"})
    with pytest.raises(NotDone, match=says):
        await call_tool(plugin, "search", {"query": "x"}, make_context(http=http))


async def test_no_results_says_so() -> None:
    plugin = brave_search_plugin()
    http = FakeHttp(plugin)
    http.route("GET", API, json={"web": {"results": []}})
    result = await call_tool(plugin, "search", {"query": "zzzz"}, make_context(http=http))
    assert result == {"query": "zzzz", "results": [], "note": "No results."}

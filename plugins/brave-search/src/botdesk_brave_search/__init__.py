"""BRAVE SEARCH PLUGIN (`botdesk-plugin-brave-search`, plugin id `brave-search`): bots search the
web with the organization's own Brave Search API key (its free plan covers a few thousand
searches a month: https://brave.com/search/api/).

| Tool | Risk | Does |
|---|---|---|
| `brave-search.search` | read | a web search: titles, addresses and short summaries |

Results are text from the web, so they are marked untrusted: reading them taints the run (risky
actions after it ask a person). Open a result with the Browser plugin (`browser.open`).
"""

import html
import re

from botdesk_plugin_sdk import ApiKeyAuth, NotDone, PluginManifest, ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field

API = "https://api.search.brave.com/res/v1/web/search"
MAX_RESULTS = 10

_TAGS = re.compile(r"<[^>]+>")


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="What to search the web for.")
    count: int = Field(default=5, ge=1, le=MAX_RESULTS, description="How many results, 1 to 10.")
    freshness: str = Field(
        default="",
        pattern=r"^(|pd|pw|pm|py)$",
        description="Only recent pages: pd (past day), pw (week), pm (month), py (year). Empty: any time.",
    )


def _plain(text: object) -> str:
    """Brave marks matches with <strong>; the model gets plain text."""
    return html.unescape(_TAGS.sub("", str(text or ""))).strip()


def brave_search_plugin() -> PluginManifest:
    async def search(args: SearchArgs, ctx: ToolContext) -> ToolResult:
        params = {
            "q": args.query,
            "count": str(args.count),
            **({"freshness": args.freshness} if args.freshness else {}),
        }
        response = await ctx.http.request("GET", API, params=params, headers={"Accept": "application/json"})
        if response.status_code in (401, 403, 422):
            raise NotDone("Brave Search refused the key. Check it in Connect apps.")
        if response.status_code == 429:
            raise NotDone("Brave Search's limit for this key is reached. Try again later, or raise the plan.")
        if not response.ok:
            raise NotDone(f"Brave Search couldn't search just now (it answered {response.status_code}).")
        web = response.json().get("web") or {}
        results = [
            {
                "title": _plain(item.get("title")),
                "url": str(item.get("url", "")),
                "summary": _plain(item.get("description")),
                **({"age": _plain(item["age"])} if item.get("age") else {}),
            }
            for item in (web.get("results") or [])[: args.count]
            if isinstance(item, dict) and item.get("url")
        ]
        return {"query": args.query, "results": results, **({} if results else {"note": "No results."})}

    return PluginManifest(
        id="brave-search",
        name="Brave Search",
        version="0.1.0",
        description="Search the web with your own Brave Search API key.",
        tools=(
            ToolSpec(
                name="search",
                title="Search the web",
                description=(
                    "Search the web. You get titles, addresses and short summaries; open a page with "
                    "browser.open to read it."
                ),
                args_model=SearchArgs,
                risk="read",
                handler=search,
                idempotent=True,
                untrusted_output=True,  # text from web pages
                summarize=lambda args: f'Search the web for "{args.query}"',
            ),
        ),
        auth=ApiKeyAuth(header="X-Subscription-Token"),
        egress=("api.search.brave.com",),
    )

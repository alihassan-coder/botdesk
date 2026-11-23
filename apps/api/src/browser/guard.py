"""The Local browser's address rules (ADR 0017 §6). It runs on the BotDesk server, so a page must
not reach the server's own network: every request a page makes is checked, not only the first
address, and anything that isn't a web page (file:, chrome:) is refused.

The same check as model and MCP servers (`core/url_guard.py`): every address a host resolves
to must be public, unless `ALLOW_PRIVATE_BROWSER_URLS`. Chromium resolves the name again itself,
so a host that changes its answer between the two can slip through; the check still stops
pages, links and redirects that point at private addresses, which is the common way in.
"""

from urllib.parse import urlsplit

from src.core.url_guard import Resolver, UnsafeUrl, resolve_host, safe_addresses

# What a page may load without a network check (inline data, the page's own blobs).
_LOCAL_SCHEMES = ("data", "blob", "about")
_WEB_SCHEMES = ("http", "https")

NOT_WEB = "Only web pages (http:// or https://) can be opened."
PRIVATE = "That address is on a private network, which this server's browser doesn't open."


class AddressGuard:
    """Remembers each host's verdict for the session, so a page's 100 requests cost one lookup per host."""

    def __init__(self, *, allow_private: bool, resolve: Resolver = resolve_host) -> None:
        self.allow_private = allow_private
        self._resolve = resolve
        self._verdicts: dict[str, bool] = {}

    async def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme in _LOCAL_SCHEMES:
            return True
        if parts.scheme not in _WEB_SCHEMES or not parts.hostname:
            return False
        if self.allow_private:
            return True
        host = parts.hostname
        if host not in self._verdicts:
            try:
                await safe_addresses(host, allow_private=False, resolve=self._resolve)
                self._verdicts[host] = True
            except UnsafeUrl:
                self._verdicts[host] = False
        return self._verdicts[host]

    async def why_not(self, url: str) -> str | None:
        """For `browser.open`: why this address can't be opened, or None."""
        if urlsplit(url).scheme not in _WEB_SCHEMES:
            return NOT_WEB
        return None if await self.allows(url) else PRIVATE

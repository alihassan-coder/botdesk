"""Claude's chat model: LangChain's `ChatAnthropic` with BotDesk's HTTP rules.

Kept apart from `anthropic.py` because the Anthropic SDK takes seconds to import: it loads
the first time a run talks to Claude, not when the API starts.
"""

import asyncio
from functools import cached_property

import anthropic
from langchain_anthropic import ChatAnthropic

from src.model_providers.base import CHAT_TIMEOUT

# The Anthropic SDK runs on httpx2 (and refuses httpx objects), so its timeout is its own type.
_SDK_TIMEOUT = anthropic.Timeout(**CHAT_TIMEOUT.as_dict())


class _NoRedirectAsyncClient(anthropic.DefaultAsyncHttpxClient):
    """The SDK's client, closed when garbage-collected (like the SDK's own wrapper)."""

    def __del__(self) -> None:
        try:
            if not self.is_closed:
                asyncio.get_running_loop().create_task(self.aclose())
        except Exception:  # noqa: S110 - no running loop: nothing to close on
            pass


class SafeChatAnthropic(ChatAnthropic):
    """`ChatAnthropic` whose HTTP clients never follow redirects and always time out.

    The Anthropic SDK's clients follow redirects by default, and `ChatAnthropic` takes no HTTP
    client of its own, so these two properties (which build the SDK clients) are replaced.
    api.anthropic.com is a fixed public address, so this is for consistency with the other
    providers: no model call anywhere in BotDesk follows a redirect."""

    @cached_property
    def _client(self) -> anthropic.Client:
        params = {**self._client_params, "timeout": _SDK_TIMEOUT}
        http = anthropic.DefaultHttpxClient(base_url=params["base_url"], timeout=_SDK_TIMEOUT, follow_redirects=False)
        return anthropic.Client(**params, http_client=http)

    @cached_property
    def _async_client(self) -> anthropic.AsyncClient:
        params = {**self._client_params, "timeout": _SDK_TIMEOUT}
        http = _NoRedirectAsyncClient(base_url=params["base_url"], timeout=_SDK_TIMEOUT, follow_redirects=False)
        return anthropic.AsyncClient(**params, http_client=http)

"""Anthropic, through its own API (not an OpenAI-compatible one), so Claude keeps its native features.

Models: `GET https://api.anthropic.com/v1/models` with `x-api-key` and `anthropic-version`.
Newest first; each has `display_name` and `max_input_tokens` (the context window).
Deprecated and retired models are left out, since they're closed to new bots.
"""

import asyncio
from functools import cached_property
from typing import Any

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.model_providers.base import CHAT_TIMEOUT, ModelInfo, get_json

API_URL = "https://api.anthropic.com/v1/models"
API_VERSION = "2023-06-01"


def _model_info(raw: dict[str, Any]) -> ModelInfo | None:
    if raw.get("lifecycle", "active") != "active" or not raw.get("id"):
        return None
    context = raw.get("max_input_tokens")
    return ModelInfo(
        model=str(raw["id"]),
        name=str(raw.get("display_name") or raw["id"]),
        context_window=context if isinstance(context, int) and context > 0 else None,
    )


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


class AnthropicAdapter:
    async def list_models(self, http: httpx.AsyncClient, api_key: str, base_url: str | None) -> list[ModelInfo]:
        body = await get_json(
            http,
            API_URL,
            api_key=api_key,
            headers={"x-api-key": api_key, "anthropic-version": API_VERSION},
            params={"limit": "1000"},
        )
        rows = body.get("data", []) if isinstance(body, dict) else []
        return [info for raw in rows if isinstance(raw, dict) and (info := _model_info(raw))]

    def chat_model(
        self, model: str, api_key: str, base_url: str | None, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> BaseChatModel:
        """`base_url` and `transport` are unused: Anthropic is only ever api.anthropic.com."""
        return SafeChatAnthropic(model=model, anthropic_api_key=SecretStr(api_key), max_retries=2)

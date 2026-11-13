"""Anthropic, through its own API (not an OpenAI-compatible one), so Claude keeps its native features.

Models: `GET https://api.anthropic.com/v1/models` with `x-api-key` and `anthropic-version`.
Newest first; each has `display_name` and `max_input_tokens` (the context window).
Deprecated and retired models are left out, since they're closed to new bots.
"""

from typing import Any

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.model_providers.base import ModelInfo, get_json

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

    def chat_model(self, model: str, api_key: str, base_url: str | None) -> BaseChatModel:
        return ChatAnthropic(model=model, anthropic_api_key=SecretStr(api_key), max_retries=2)

"""Providers that speak OpenAI's API: OpenAI itself, Google Gemini, OpenRouter, Groq, and custom
servers (Ollama, LM Studio, vLLM). One adapter with a base URL, plus a small per-provider rule for
which models to keep and how to read their details.

Models come from `GET {base}/models` with `Authorization: Bearer <key>`. Chat goes through
LangChain's `ChatOpenAI` pointed at the same base URL, so no extra packages are needed.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.model_providers.base import ModelInfo, Pricing, ProviderError, get_json

# Local servers like Ollama take no key, but the OpenAI client insists on one.
NO_KEY = "not-needed"

ModelReader = Callable[[dict[str, Any]], ModelInfo | None]


def _plain(raw: dict[str, Any]) -> ModelInfo | None:
    """Most servers only give an id."""
    model = str(raw.get("id") or "")
    return ModelInfo(model=model, name=model) if model else None


_NOT_CHAT = ("embedding", "tts", "whisper", "dall-e", "moderation", "audio", "realtime", "transcribe", "image")


def _openai(raw: dict[str, Any]) -> ModelInfo | None:
    """OpenAI lists every model it has; keep the chat families (gpt-*, o1/o3/o4…, chatgpt-*)."""
    info = _plain(raw)
    if info is None or any(word in info.model for word in _NOT_CHAT):
        return None
    return info if re.match(r"^(gpt-|chatgpt-|o\d)", info.model) else None


_GEMINI_NOT_CHAT = ("embedding", "tts", "audio", "live", "image", "imagen", "veo", "aqa")


def _gemini(raw: dict[str, Any]) -> ModelInfo | None:
    """Google's OpenAI-compatible list names models "models/gemini-…"; chat wants the bare id."""
    model = str(raw.get("id") or "").removeprefix("models/")
    if not model.startswith(("gemini", "gemma")) or any(word in model for word in _GEMINI_NOT_CHAT):
        return None
    return ModelInfo(model=model, name=str(raw.get("display_name") or model))


def _per_million(price: Any) -> float | None:
    """OpenRouter prices are strings in dollars per token; -1 means "it varies"."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None
    return round(value * 1_000_000, 4) if value >= 0 else None


def _openrouter(raw: dict[str, Any]) -> ModelInfo | None:
    """OpenRouter gives a name, context length and prices; keep them."""
    info = _plain(raw)
    if info is None:
        return None
    pricing = raw.get("pricing") or {}
    prompt, completion = _per_million(pricing.get("prompt")), _per_million(pricing.get("completion"))
    context = raw.get("context_length")
    return ModelInfo(
        model=info.model,
        name=str(raw.get("name") or info.model),
        context_window=context if isinstance(context, int) and context > 0 else None,
        pricing=Pricing(prompt, completion) if prompt is not None and completion is not None else None,
    )


_GROQ_NOT_CHAT = ("whisper", "tts", "orpheus", "guard", "playai")


def _groq(raw: dict[str, Any]) -> ModelInfo | None:
    """Groq also serves speech and safety models; keep the chat ones that are switched on."""
    info = _plain(raw)
    if info is None or raw.get("active") is False or any(word in info.model for word in _GROQ_NOT_CHAT):
        return None
    context = raw.get("context_window")
    return ModelInfo(info.model, info.name, context if isinstance(context, int) and context > 0 else None)


@dataclass(frozen=True)
class OpenAICompatibleAdapter:
    """`base_url` is fixed for the built-in providers; custom servers pass theirs in each call."""

    base_url: str | None
    read_model: ModelReader = _plain
    sort_by_name: bool = True

    def _base(self, base_url: str | None) -> str:
        base = (self.base_url or base_url or "").rstrip("/")
        if not base:
            raise ProviderError("it has no base URL")
        return base

    async def list_models(self, http: httpx.AsyncClient, api_key: str, base_url: str | None) -> list[ModelInfo]:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        body = await get_json(http, f"{self._base(base_url)}/models", api_key=api_key, headers=headers)
        rows = body.get("data", []) if isinstance(body, dict) else body if isinstance(body, list) else []
        models = [info for raw in rows if isinstance(raw, dict) and (info := self.read_model(raw))]
        return sorted(models, key=lambda m: m.name.lower()) if self.sort_by_name else models

    def chat_model(self, model: str, api_key: str, base_url: str | None) -> BaseChatModel:
        return ChatOpenAI(
            model_name=model,
            openai_api_key=SecretStr(api_key or NO_KEY),
            openai_api_base=self._base(base_url),
            max_retries=2,
        )


OPENAI = OpenAICompatibleAdapter("https://api.openai.com/v1", _openai)
GEMINI = OpenAICompatibleAdapter("https://generativelanguage.googleapis.com/v1beta/openai", _gemini)
OPENROUTER = OpenAICompatibleAdapter("https://openrouter.ai/api/v1", _openrouter)
GROQ = OpenAICompatibleAdapter("https://api.groq.com/openai/v1", _groq)
CUSTOM = OpenAICompatibleAdapter(None)

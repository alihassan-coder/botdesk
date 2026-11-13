"""The model providers BotDesk supports, and how to talk to each one.

A provider id is a built-in kind ("anthropic", "openai", "gemini", "openrouter", "groq") or
"custom-<credential id>" for an OpenAI-compatible server an organization added. Model ids are
"<provider id>:<the provider's model id>", e.g. "groq:llama-3.3-70b-versatile" or
"custom-6f1c…:llama3.2:latest" (only the first colon separates the two).
"""

import uuid
from dataclasses import dataclass
from typing import Literal, get_args

from src.core.config import Settings
from src.model_providers.anthropic import AnthropicAdapter
from src.model_providers.base import ModelInfo, Pricing, ProviderAdapter, ProviderError, scrub
from src.model_providers.openai_compatible import CUSTOM, GEMINI, GROQ, OPENAI, OPENROUTER

__all__ = [
    "BUILT_IN",
    "CUSTOM_PREFIX",
    "ModelInfo",
    "Pricing",
    "ProviderAdapter",
    "ProviderError",
    "ProviderKind",
    "ProviderSpec",
    "adapter_for",
    "custom_id_of",
    "env_key",
    "scrub",
    "spec_for",
]

ProviderKind = Literal["anthropic", "openai", "gemini", "openrouter", "groq", "custom"]
CUSTOM_PREFIX = "custom-"


@dataclass(frozen=True)
class ProviderSpec:
    kind: ProviderKind
    name: str
    hint: str  # one line for the provider's card in Settings → Models & keys


BUILT_IN: dict[str, ProviderSpec] = {
    spec.kind: spec
    for spec in (
        ProviderSpec("anthropic", "Anthropic", "Claude models. Get a key at console.anthropic.com."),
        ProviderSpec("openai", "OpenAI", "GPT and o-series models. Get a key at platform.openai.com."),
        ProviderSpec("gemini", "Google Gemini", "Gemini models. Get a key at aistudio.google.com."),
        ProviderSpec("openrouter", "OpenRouter", "Hundreds of models behind one key, with prices."),
        ProviderSpec("groq", "Groq", "Fast open models, and it has a free tier. Get a key at console.groq.com."),
    )
}
CUSTOM_SPEC = ProviderSpec("custom", "Custom", "Any OpenAI-compatible server: Ollama, LM Studio, vLLM.")
assert set(BUILT_IN) | {"custom"} == set(get_args(ProviderKind))

_ADAPTERS: dict[ProviderKind, ProviderAdapter] = {
    "anthropic": AnthropicAdapter(),
    "openai": OPENAI,
    "gemini": GEMINI,
    "openrouter": OPENROUTER,
    "groq": GROQ,
    "custom": CUSTOM,
}


def adapter_for(kind: ProviderKind) -> ProviderAdapter:
    return _ADAPTERS[kind]


def spec_for(kind: ProviderKind) -> ProviderSpec:
    return BUILT_IN.get(kind, CUSTOM_SPEC)


def custom_id_of(provider_id: str) -> uuid.UUID | None:
    """ "custom-<uuid>" → the credential's id; anything else → None."""
    if not provider_id.startswith(CUSTOM_PREFIX):
        return None
    try:
        return uuid.UUID(provider_id.removeprefix(CUSTOM_PREFIX))
    except ValueError:
        return None


def env_key(settings: Settings, kind: str) -> str:
    """The instance-wide key from the environment (self-hosting), or ""."""
    keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "openrouter": settings.openrouter_api_key,
        "groq": settings.groq_api_key,
    }
    key = keys.get(kind)
    return key.get_secret_value() if key else ""

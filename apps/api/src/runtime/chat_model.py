"""Pick the chat model for a bot. Any LangChain provider works through `init_chat_model`.

With no API key for the provider, the bot gets a stand-in model: it streams a short canned
reply, so the whole flow (runs, streaming, saving) works offline and in tests.
"""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from src.core.config import Settings

STAND_IN_REPLY = (
    "Hi! I'm a stand-in reply: BotDesk has no API key for {provider} yet, so I can't think for real. "
    "Add ANTHROPIC_API_KEY or OPENAI_API_KEY to apps/api/.env and restart the API."
)


def stand_in_model(provider: str) -> BaseChatModel:
    return GenericFakeChatModel(messages=iter([STAND_IN_REPLY.format(provider=provider or "this model")]))


def chat_model_for(model_id: str, settings: Settings) -> BaseChatModel:
    """`model_id` is "provider:model", e.g. "anthropic:claude-sonnet-4-5". Empty = the default."""
    model_id = model_id or settings.default_model_id
    provider = model_id.partition(":")[0]
    keys = {"anthropic": settings.anthropic_api_key, "openai": settings.openai_api_key}
    api_key = keys.get(provider, "")
    if not api_key:
        return stand_in_model(provider)
    return init_chat_model(model_id, api_key=api_key)

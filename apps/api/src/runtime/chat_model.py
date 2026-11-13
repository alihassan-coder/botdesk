"""Pick the chat model for a bot: `ModelResolver` turns a bot's "provider:model" into a LangChain
chat model, using (in this order) the organization's key for that provider, the server's
environment key, or a stand-in model. Keys are decrypted only here, right before the run uses them.

With no key for the provider, the bot gets the stand-in model, so the whole flow (runs,
streaming, tools, approvals) works offline and in tests. The stand-in is deterministic:

- a message containing `/tool demo.create_note title="Plan" body=Ship` makes it call that
  tool (arguments as `key=value`, quoted when they have spaces, or one JSON object);
- after a tool result, it reports what the tool returned;
- anything else gets a canned reply.
"""

import json
import shlex
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.errors import AppError
from src.core.secrets import SecretBox
from src.core.url_guard import GuardedTransport, check_base_url
from src.model_providers import ProviderError, adapter_for, scrub
from src.services import provider_service

STAND_IN_REPLY = (
    "Hi! I'm a stand-in reply: BotDesk has no API key for {provider} yet, so I can't think for real. "
    "An owner or admin can add one in Settings → Models & keys, then pick a model for me. "
    "You can still try tools: send `/tool demo.send_email to=sara@acme.dev subject=Hi`."
)
TOOL_COMMAND = "/tool"


def parse_tool_command(text: str) -> tuple[str, dict[str, Any]] | None:
    """`... /tool demo.create_note title="Q3 plan" pinned=true` → ("demo.create_note", {...}).
    Values that read as JSON (numbers, true, null) become those; everything else is a string."""
    _, found, rest = text.partition(TOOL_COMMAND)
    if not found or not rest[:1].isspace():
        return None
    name, _, raw_args = rest.strip().partition(" ")
    if not name:
        return None
    raw_args = raw_args.strip()
    if raw_args.startswith("{"):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            parsed = None
        return name, parsed if isinstance(parsed, dict) else {}
    try:
        words = shlex.split(raw_args)
    except ValueError:  # an unclosed quote
        words = raw_args.split()
    args: dict[str, Any] = {}
    for word in words:
        key, equals, value = word.partition("=")
        if equals and key:
            args[key] = _value_of(value)
    return name, args


def _value_of(text: str) -> Any:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return text
    return value if isinstance(value, int | float | bool) or value is None else text


class StandInModel(BaseChatModel):
    """A fake model that can call tools on command (see the module docstring)."""

    provider: str = "this model"

    @property
    def _llm_type(self) -> str:
        return "botdesk-stand-in"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """It calls whatever `/tool` names; the tool pipeline rejects tools that don't exist."""
        return self

    def _respond(self, messages: list[BaseMessage]) -> tuple[str, dict[str, Any] | None]:
        """The reply text, and the tool call to make (if any)."""
        last = messages[-1] if messages else None
        if isinstance(last, ToolMessage):
            return f"Finished {last.name or 'the tool'}: {last.text}", None
        if isinstance(last, HumanMessage) and (command := parse_tool_command(last.text)):
            name, args = command
            call = {"name": name.replace(".", "__", 1), "args": args, "id": f"standin_{uuid.uuid4().hex[:16]}"}
            return f"Using {name}.", call
        return STAND_IN_REPLY.format(provider=self.provider), None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text, call = self._respond(messages)
        message = AIMessage(content=text, tool_calls=[{**call, "type": "tool_call"}] if call else [])
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _chunks(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
        text, call = self._respond(messages)
        words = text.split(" ")
        for index, word in enumerate(words):
            yield ChatGenerationChunk(message=AIMessageChunk(content=word if index == 0 else " " + word))
        if call:
            chunk = tool_call_chunk(name=call["name"], args=json.dumps(call["args"]), id=call["id"], index=0)
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[chunk]))

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        yield from self._chunks(messages)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._chunks(messages):
            yield chunk


def stand_in_model(provider: str) -> BaseChatModel:
    return StandInModel(provider=provider or "this model")


class ModelUnavailable(Exception):
    """The bot's model can't be used (its key can't be read, or its server's address isn't allowed).
    The message is safe to show as the run's error."""


class ModelResolver:
    """The chat model for one run: org key > environment key > stand-in."""

    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], secrets: SecretBox) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.secrets = secrets

    async def __call__(self, org_id: uuid.UUID, model_id: str) -> BaseChatModel:
        """`model_id` is "provider:model" (e.g. "groq:llama-3.3-70b-versatile"). Empty = DEFAULT_MODEL_ID."""
        provider_id, _, model = (model_id or self.settings.default_model_id).partition(":")
        try:
            async with self.sessionmaker() as db:
                connection = await provider_service.connection_for(db, org_id, provider_id, self.settings, self.secrets)
            if connection is None:
                return stand_in_model(provider_id)
            base_url = connection.base_url
            transport = None
            if connection.kind == "custom" and base_url:
                allow_private = self.settings.allow_private_model_urls
                base_url = await check_base_url(base_url, allow_private=allow_private)
                # The check above gives a clear error before the run starts; the transport
                # checks again on every connection and connects to the checked address.
                transport = GuardedTransport(allow_private=allow_private)
        except ProviderError as error:
            raise ModelUnavailable(f"{provider_id}: {error}") from error
        except AppError as error:
            raise ModelUnavailable(error.message) from error
        return adapter_for(connection.kind).chat_model(model, connection.api_key, base_url, transport=transport)


# Request headers that carry a provider key: OpenAI-style bearer tokens, Anthropic, Azure-style.
_KEY_HEADERS = ("authorization", "x-api-key", "api-key")


def keys_in(error: BaseException) -> list[str]:
    """The keys the failed request sent, read from the error itself.

    The provider SDKs attach the request to their errors, and the request carries the key in a
    header. Scrubbing by pattern alone misses keys of a format we don't know (a custom server's
    key can be anything), so the exact key is taken out too. Follows `__cause__`/`__context__`,
    since LangChain re-raises SDK errors as its own."""
    found: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        headers = getattr(getattr(current, "request", None), "headers", None)
        if headers is not None:
            for name in _KEY_HEADERS:
                value = str(headers.get(name) or "")
                value = value.removeprefix("Bearer ").removeprefix("bearer ").strip()
                if value:
                    found.append(value)
        current = current.__cause__ or current.__context__
    return found


def describe_model_error(error: Exception, *secrets: str) -> str:
    """A model call failed mid-run: say why in words people can act on. Never includes a key:
    the key the request carried (and any in `secrets`) is removed exactly, whatever its format,
    and anything else that looks like a key is removed by pattern."""
    status = getattr(error, "status_code", None)
    lowered = str(error).lower()
    if status in (401, 403) or "invalid api key" in lowered or "incorrect api key" in lowered:
        return "The model provider refused the API key. An owner or admin can replace it in Settings → Models & keys."
    if "tool" in lowered and any(word in lowered for word in ("support", "not available", "not enabled")):
        return "This model can't use tools. Pick another model in the bot's settings."
    if status == 404 or "model_not_found" in lowered or "does not exist" in lowered:
        return "The provider doesn't offer this model any more. Pick another one in the bot's settings."
    if status == 429:
        return "The model provider says we're over its rate limit or quota. Try again in a little while."
    return f"The model couldn't reply: {scrub(str(error), *secrets, *keys_in(error))}"

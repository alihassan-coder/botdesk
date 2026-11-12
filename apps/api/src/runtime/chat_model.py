"""Pick the chat model for a bot. Any LangChain provider works through `init_chat_model`.

With no API key for the provider, the bot gets a stand-in model, so the whole flow (runs,
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

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from src.core.config import Settings

STAND_IN_REPLY = (
    "Hi! I'm a stand-in reply: BotDesk has no API key for {provider} yet, so I can't think for real. "
    "Add ANTHROPIC_API_KEY or OPENAI_API_KEY to apps/api/.env and restart the API. "
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


def chat_model_for(model_id: str, settings: Settings) -> BaseChatModel:
    """`model_id` is "provider:model", e.g. "anthropic:claude-sonnet-4-5". Empty = the default."""
    model_id = model_id or settings.default_model_id
    provider = model_id.partition(":")[0]
    keys = {"anthropic": settings.anthropic_api_key, "openai": settings.openai_api_key}
    api_key = keys.get(provider, "")
    if not api_key:
        return stand_in_model(provider)
    return init_chat_model(model_id, api_key=api_key)

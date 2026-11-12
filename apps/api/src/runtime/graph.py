"""A run as a LangGraph graph (agents-and-plugins.md §4), without tools for now:

    load_context → recall → call_model → save_reply → remember

The checkpointer saves the state after every node, keyed by the run id. Each node is safe
to run twice (§4.1): if a run is ever resumed, a node may start again from its first line.
"""

import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.runtime.limits import RunLimits, limit_reached
from src.runtime.memory import MemoryScope, MemoryService
from src.runtime.prompt import HistoryLine, build_prompt
from src.runtime.reporter import RunReporter
from src.runtime.token_batcher import BackgroundSender, TokenBatcher
from src.services import run_service, thread_service

logger = logging.getLogger(__name__)


class RunError(Exception):
    """A run can't go on. The message is shown to people as the run's error."""


class RunStopped(Exception):
    """Someone pressed Stop."""


class RunState(TypedDict, total=False):
    bot_name: str
    instructions: str
    model_id: str
    tainted: bool
    member_id: str | None
    history: list[dict[str, Any]]  # {"fromThisBot": bool, "text": str}, oldest first
    memories: list[str]
    reply_message_id: str
    reply: str


@dataclass(frozen=True)
class RunDeps:
    """Everything the nodes use that isn't state. Passed in per run, never saved in checkpoints."""

    run_id: uuid.UUID
    org_id: uuid.UUID
    bot_id: uuid.UUID
    limits: RunLimits
    started_at: float  # time.monotonic() when the run started
    sessionmaker: async_sessionmaker[AsyncSession]
    reporter: RunReporter
    memory: MemoryService
    model_for: Callable[[str], BaseChatModel]
    in_background: Callable[[Coroutine[Any, Any, None]], None]


def _memory_scope(state: RunState, deps: RunDeps) -> MemoryScope:
    member = state.get("member_id")
    return MemoryScope(org_id=deps.org_id, bot_id=deps.bot_id, member_id=uuid.UUID(member) if member else None)


def _last_human_text(state: RunState) -> str:
    """The message the bot is answering: the newest one not written by this bot."""
    return next((line["text"] for line in reversed(state["history"]) if not line["fromThisBot"]), "")


async def load_context(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    async with runtime.context.sessionmaker() as db:
        context = await run_service.run_context(db, runtime.context.run_id)
    return {
        "bot_name": context.bot_name,
        "instructions": context.instructions,
        "model_id": context.model_id,
        "tainted": context.tainted,
        "member_id": str(context.member_id) if context.member_id else None,
        "history": [{"fromThisBot": mine, "text": text} for mine, text in context.history],
    }


async def recall(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """The top memories for the message being answered. A memory failure never fails a run."""
    deps = runtime.context
    try:
        memories = await deps.memory.recall(_memory_scope(state, deps), _last_human_text(state))
    except Exception:
        logger.exception("Memory recall failed for run %s", deps.run_id)
        memories = []
    return {"memories": memories}


async def call_model(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    deps = runtime.context
    async with deps.sessionmaker() as db:
        step = await run_service.start_step(db, deps.run_id)
    if step.stop_requested:
        raise RunStopped
    elapsed = time.monotonic() - deps.started_at
    if reason := limit_reached(deps.limits, steps_used=step.steps_used, elapsed_seconds=elapsed):
        raise RunError(reason)

    prompt = build_prompt(
        bot_name=state["bot_name"],
        instructions=state["instructions"],
        memories=state.get("memories", []),
        history=[HistoryLine(from_this_bot=line["fromThisBot"], text=line["text"]) for line in state["history"]],
    )
    # The reply's id is chosen now, so the streamed pieces and the saved message share it.
    message_id = str(uuid.uuid4())
    reply = await _stream_reply(deps, deps.model_for(state["model_id"]), prompt, message_id)
    return {"reply": reply, "reply_message_id": message_id}


async def _stream_reply(deps: RunDeps, model: BaseChatModel, prompt: list[Any], message_id: str) -> str:
    """Send the reply to the chat in small batches as it arrives, and return all of it."""

    async def save_delta(text: str) -> None:
        await deps.reporter.send("message_delta", {"messageId": message_id, "botId": str(deps.bot_id), "text": text})

    batcher = TokenBatcher()
    pieces: list[str] = []
    async with BackgroundSender(save_delta) as sender:
        try:
            async for chunk in model.astream(prompt):
                if token := str(chunk.text):
                    pieces.append(token)
                    if batch := batcher.add(token, now=time.monotonic()):
                        sender.send(batch)
        except Exception as error:
            raise RunError(f"The model couldn't reply: {error}") from error
        if rest := batcher.flush():
            sender.send(rest)
    return "".join(pieces)


async def save_reply(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    deps = runtime.context
    async with deps.sessionmaker() as db:
        message = await run_service.save_reply(
            db, run_id=deps.run_id, message_id=uuid.UUID(state["reply_message_id"]), text=state["reply"]
        )
        message_json = thread_service.message_out(message).model_dump(mode="json", by_alias=True)
        deps.reporter.add(db, "message_saved", {"message": message_json})
        await db.commit()
    deps.reporter.announce()
    return {}


async def remember(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Saving memories costs a model call, so it runs in the background and the reply isn't
    held up. Runs that read outside text (tainted) don't save memories (§9)."""
    deps = runtime.context
    if state.get("tainted"):
        return {}
    conversation = [
        {"role": "user", "content": _last_human_text(state)},
        {"role": "assistant", "content": state["reply"]},
    ]
    deps.in_background(deps.memory.remember(_memory_scope(state, deps), conversation))
    return {}


def build_graph(checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph[RunState, RunDeps, RunState, RunState]:
    graph = StateGraph(RunState, context_schema=RunDeps)
    graph.add_node("load_context", load_context)
    graph.add_node("recall", recall)
    graph.add_node("call_model", call_model)
    graph.add_node("save_reply", save_reply)
    graph.add_node("remember", remember)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "recall")
    graph.add_edge("recall", "call_model")
    graph.add_edge("call_model", "save_reply")
    graph.add_edge("save_reply", "remember")
    graph.add_edge("remember", END)
    return graph.compile(checkpointer=checkpointer)

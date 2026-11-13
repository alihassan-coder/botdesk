"""A run as a LangGraph graph (agents-and-plugins.md §4):

    load_context → recall → call_model ─┬─ no tool calls ─→ save_reply → remember
                                        └─ tool calls ─→ prepare_call ─┬─ auto ──→ execute_tool ─┐
                                                                       ├─ ask ───→ approval_gate ┤
                                                                       └─ deny ──────────────────┤
                         call_model ←─ (no calls left) ─ finish_call ←──────────────────────────┘
                                       (calls left) → prepare_call

Tool calls are handled one at a time (ADR 0004 §7). The checkpointer saves the state after
every node, keyed by the run id. Each node is safe to run twice (§4.1): when a paused run
resumes, `approval_gate` starts again from its first line, which is why it does nothing but
pause. Side effects happen only in `execute_tool`, after the decision is saved.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, TypedDict, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
    message_chunk_to_message,
    message_to_dict,
    messages_from_dict,
)
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import utcnow
from src.models.bot import Bot, SecurityLevel
from src.plugins.registry import ToolRegistry
from src.runtime import tool_pipeline
from src.runtime.chat_model import ModelPrice, ModelUnavailable, describe_model_error
from src.runtime.limits import RunLimits, limit_reached
from src.runtime.memory import MemoryScope, MemoryService
from src.runtime.policy import LEVELS
from src.runtime.prompt import HistoryLine, build_prompt
from src.runtime.reporter import RunReporter
from src.runtime.token_batcher import BackgroundSender, TokenBatcher
from src.runtime.tool_pipeline import ToolCallRequest, finished_event
from src.services import pricing, run_service, thread_service, tool_execution_service, usage_service
from src.services.tool_execution_service import RunRef

logger = logging.getLogger(__name__)

STEP_SEPARATOR = "\n\n"  # between the text of two model steps in one reply


class RunError(Exception):
    """A run can't go on. The message is shown to people as the run's error."""


class BudgetReached(RunError):
    """The bot or its organization is out of budget this month. The run fails with `code` "budget",
    so the web can show the message with a way to raise the budget."""

    code = "budget"


class RunStopped(Exception):
    """Someone pressed Stop."""


class CallState(TypedDict, total=False):
    """The tool call going through the pipeline now."""

    toolCallId: str
    tool: str
    executionId: str
    decision: str  # auto | ask | deny | invalid, then approved | denied after the gate
    approvalId: str | None
    refusal: str | None  # what the model is told when the call doesn't run
    result: str | None  # what the model is told when it ran


class RunState(TypedDict, total=False):
    bot_name: str
    instructions: str
    model_id: str
    security_level: str
    tainted: bool
    member_id: str | None
    history: list[dict[str, Any]]  # {"fromThisBot": bool, "text": str}, oldest first
    memories: list[str]
    reply_message_id: str
    reply: str  # the text of every model step so far, joined
    turns: list[dict[str, Any]]  # this run's tool round trips, as LangChain message dicts
    pending_calls: list[dict[str, Any]]  # tool calls not handled yet: {"id", "name", "args"}
    call: CallState
    # Approvals asked for in this run. Kept for checkpoints already saved; the reply's cards
    # now come from the tool calls recorded in the database (`reply_cards`).
    approval_ids: list[str]


@dataclass(frozen=True)
class RunDeps:
    """Everything the nodes use that isn't state. Passed in per run, never saved in checkpoints."""

    run_id: uuid.UUID
    org_id: uuid.UUID
    bot_id: uuid.UUID
    thread_id: uuid.UUID
    limits: RunLimits
    started_at: float  # time.monotonic() when this stretch of the run started
    sessionmaker: async_sessionmaker[AsyncSession]
    reporter: RunReporter
    memory: MemoryService
    model_for: Callable[[str], Awaitable[BaseChatModel]]  # model id → chat model, with this org's keys
    price_for: Callable[[str], Awaitable[ModelPrice]]  # model id → its price, for budgets and usage
    in_background: Callable[[Coroutine[Any, Any, None]], None]
    registry: ToolRegistry
    tool_timeout_seconds: float
    approval_expiry: timedelta

    @property
    def run_ref(self) -> RunRef:
        return RunRef(run_id=self.run_id, org_id=self.org_id, thread_id=self.thread_id, bot_id=self.bot_id)


def _memory_scope(state: RunState, deps: RunDeps) -> MemoryScope:
    member = state.get("member_id")
    return MemoryScope(org_id=deps.org_id, bot_id=deps.bot_id, member_id=uuid.UUID(member) if member else None)


async def _bot_memory_on(deps: RunDeps) -> bool:
    """The bot's own memory switch (Edit bot). Read fresh, so turning it off applies at once."""
    async with deps.sessionmaker() as db:
        bot = await db.get(Bot, deps.bot_id)
    return bot is not None and bot.memory_enabled


def _last_human_text(state: RunState) -> str:
    """The message the bot is answering: the newest one not written by this bot."""
    return next((line["text"] for line in reversed(state["history"]) if not line["fromThisBot"]), "")


def _security_level(state: RunState) -> SecurityLevel:
    """The bot's level. Anything unexpected falls back to the strictest one (fail closed)."""
    level = state.get("security_level", "")
    return level if level in LEVELS else "read-only"


async def load_context(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    async with runtime.context.sessionmaker() as db:
        context = await run_service.run_context(db, runtime.context.run_id)
    return {
        "bot_name": context.bot_name,
        "instructions": context.instructions,
        "model_id": context.model_id,
        "security_level": context.security_level,
        "tainted": context.tainted,
        "member_id": str(context.member_id) if context.member_id else None,
        "history": [{"fromThisBot": mine, "text": text} for mine, text in context.history],
        "turns": [],
        "pending_calls": [],
        "approval_ids": [],
    }


async def recall(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """The top memories for the message being answered. A memory failure never fails a run."""
    deps = runtime.context
    if not await _bot_memory_on(deps):
        return {"memories": []}
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
    turns = state.get("turns", [])
    messages = [*prompt, *messages_from_dict(turns)]
    price = await deps.price_for(state["model_id"])
    await _check_budget(deps, price, messages)
    # The reply's id is chosen at the first step, so every streamed piece and the saved message share it.
    message_id = state.get("reply_message_id") or str(uuid.uuid4())
    earlier = state.get("reply", "")
    try:
        chat_model = await deps.model_for(state["model_id"])
    except ModelUnavailable as error:
        raise RunError(str(error)) from error
    model = _with_tools(chat_model, deps.registry)
    answer = await _stream_reply(deps, model, messages, message_id, separator=STEP_SEPARATOR if earlier else "")
    await _record_usage(deps, price, answer)
    text = answer.text
    calls = [{"id": call["id"], "name": call["name"], "args": call["args"]} for call in answer.tool_calls]
    return {
        "reply": earlier + STEP_SEPARATOR + text if earlier and text else earlier or text,
        "reply_message_id": message_id,
        "turns": [*turns, message_to_dict(answer)] if calls else turns,
        "pending_calls": calls,
    }


async def _check_budget(deps: RunDeps, price: ModelPrice, messages: list[BaseMessage]) -> None:
    """Before each model call (§4.2): stop if this month's spend plus a small estimate of this call
    would pass the bot's or the organization's budget."""
    estimate = pricing.estimate_usd(price.pricing, sum(len(str(message.content)) for message in messages))
    async with deps.sessionmaker() as db:
        reason = await usage_service.budget_stop(
            db, org_id=deps.org_id, bot_id=deps.bot_id, estimate_usd=estimate, now=utcnow()
        )
    if reason:
        raise BudgetReached(reason)


async def _record_usage(deps: RunDeps, price: ModelPrice, answer: AIMessage) -> None:
    """After each model call: one short insert with its tokens and cost. Models that don't report
    tokens (the stand-in, some custom servers) record nothing."""
    usage = answer.usage_metadata
    if not usage:
        return
    input_tokens, output_tokens = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    try:
        async with deps.sessionmaker() as db:
            usage_service.record(
                db,
                org_id=deps.org_id,
                bot_id=deps.bot_id,
                run_id=deps.run_id,
                provider=price.provider,
                model_id=price.model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=pricing.cost_usd(price.pricing, input_tokens, output_tokens),
            )
            await db.commit()
    except Exception:  # the reply matters more than its bookkeeping
        logger.exception("Couldn't record usage for run %s", deps.run_id)


def _with_tools(model: BaseChatModel, registry: ToolRegistry) -> Runnable[Any, Any]:
    """The model, told about the tools it may call. Models that can't call tools answer without them."""
    tools = [tool.for_model() for tool in registry.tools()]
    if not tools:
        return model
    try:
        return model.bind_tools(tools)
    except NotImplementedError:
        return model


async def _stream_reply(
    deps: RunDeps, model: Runnable[Any, Any], prompt: list[BaseMessage], message_id: str, *, separator: str
) -> AIMessage:
    """Send the reply's text to the chat in small batches as it arrives, and return the whole
    answer (text and tool calls). `separator` goes before the first piece, when there is one."""

    async def save_delta(text: str) -> None:
        await deps.reporter.send("message_delta", {"messageId": message_id, "botId": str(deps.bot_id), "text": text})

    batcher = TokenBatcher()
    answer: AIMessageChunk | None = None
    async with BackgroundSender(save_delta) as sender:
        try:
            async for chunk in model.astream(prompt):
                answer = chunk if answer is None else answer + chunk
                if token := str(chunk.text):
                    if separator:
                        token, separator = separator + token, ""
                    if batch := batcher.add(token, now=time.monotonic()):
                        sender.send(batch)
        except Exception as error:
            raise RunError(describe_model_error(error)) from error
        if rest := batcher.flush():
            sender.send(rest)
    if answer is None:
        return AIMessage(content="")
    return cast(AIMessage, message_chunk_to_message(answer))


def after_model(state: RunState) -> Literal["prepare_call", "save_reply"]:
    return "prepare_call" if state.get("pending_calls") else "save_reply"


async def prepare_call(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Validate, classify, ask the policy, and save the decision. No tool runs here."""
    deps = runtime.context
    first, *rest = state["pending_calls"]
    tainted = state.get("tainted", False)
    request = ToolCallRequest(id=first["id"], name=first["name"], args=dict(first.get("args") or {}))
    prepared = tool_pipeline.prepare(deps.registry, request, level=_security_level(state), tainted=tainted)
    async with deps.sessionmaker() as db:
        recorded = await tool_pipeline.record(
            db, deps.run_ref, prepared, tainted=tainted, approval_expiry=deps.approval_expiry
        )
        execution = recorded.execution
        if recorded.created and execution.decision in ("deny", "invalid"):
            status = "denied" if execution.decision == "deny" else "failed"
            event = finished_event(execution.id, execution.tool_name, error=execution.error, status=status)
            deps.reporter.add(db, "tool_finished", event)
        await db.commit()
    deps.reporter.announce()
    call: CallState = {
        "toolCallId": request.id,
        "tool": execution.tool_name,
        "executionId": str(execution.id),
        "decision": execution.decision,
        "approvalId": str(recorded.approval.id) if recorded.approval else None,
        "refusal": execution.error,
    }
    return {"pending_calls": rest, "call": call}


def after_prepare(state: RunState) -> Literal["execute_tool", "approval_gate", "finish_call"]:
    decision = state["call"]["decision"]
    if decision == "auto":
        return "execute_tool"
    if decision == "ask":
        return "approval_gate"
    return "finish_call"


def approval_gate(state: RunState) -> RunState:
    """Pause until a person decides. RULE: nothing else happens here. On resume this node runs
    again from the top, and `interrupt` then returns the answer instead of pausing."""
    call = state["call"]
    answer = interrupt({"approvalId": call["approvalId"]})
    approved = bool(answer.get("approved"))
    return {"call": {**call, "decision": "approved" if approved else "denied", "refusal": answer.get("message")}}


def after_gate(state: RunState) -> Literal["execute_tool", "finish_call"]:
    return "execute_tool" if state["call"]["decision"] == "approved" else "finish_call"


async def execute_tool(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Run the tool, at most once (the `tool_executions` record makes sure)."""
    deps = runtime.context
    call = state["call"]
    outcome = await tool_pipeline.execute(
        tool_pipeline.ExecuteDeps(
            sessionmaker=deps.sessionmaker,
            registry=deps.registry,
            reporter=deps.reporter,
            run=deps.run_ref,
            timeout_seconds=deps.tool_timeout_seconds,
        ),
        uuid.UUID(call["executionId"]),
    )
    update: RunState = {"call": {**call, "result": outcome.text}}
    if outcome.tainted:
        update["tainted"] = True
    return update


def finish_call(state: RunState) -> RunState:
    """Give the model the tool's answer (or why it didn't run). Every call gets one: providers
    reject a conversation where a tool call has no result."""
    call = state["call"]
    text = call.get("result") or call.get("refusal") or "Not done."
    answer = ToolMessage(content=text, tool_call_id=call["toolCallId"], name=call["tool"])
    approvals = state.get("approval_ids", [])
    if (approval_id := call.get("approvalId")) and approval_id not in approvals:
        approvals = [*approvals, approval_id]
    return {"turns": [*state.get("turns", []), message_to_dict(answer)], "call": {}, "approval_ids": approvals}


def after_call(state: RunState) -> Literal["prepare_call", "call_model"]:
    return "prepare_call" if state.get("pending_calls") else "call_model"


async def save_reply(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    deps = runtime.context
    async with deps.sessionmaker() as db:
        cards = await tool_execution_service.reply_cards(db, deps.run_id)
        message = await run_service.save_reply(
            db,
            run_id=deps.run_id,
            message_id=uuid.UUID(state["reply_message_id"]),
            text=state.get("reply", ""),
            extra_parts=cards,
        )
        message_json = thread_service.message_out(message).model_dump(mode="json", by_alias=True)
        deps.reporter.add(db, "message_saved", {"message": message_json})
        await db.commit()
    deps.reporter.announce()
    return {}


async def remember(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Saving memories costs a model call, so it runs in the background and the reply isn't
    held up. Runs that read outside text (tainted) don't save memories (§9), and neither do
    bots with memory turned off."""
    deps = runtime.context
    if state.get("tainted") or not await _bot_memory_on(deps):
        return {}
    conversation = [
        {"role": "user", "content": _last_human_text(state)},
        {"role": "assistant", "content": state.get("reply", "")},
    ]
    deps.in_background(deps.memory.remember(_memory_scope(state, deps), conversation))
    return {}


def build_graph(checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph[RunState, RunDeps, RunState, RunState]:
    """Paused runs meet new code (ADR 0004 §8): add nodes, never rename or remove them."""
    graph = StateGraph(RunState, context_schema=RunDeps)
    graph.add_node("load_context", load_context)
    graph.add_node("recall", recall)
    graph.add_node("call_model", call_model)
    graph.add_node("prepare_call", prepare_call)
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("finish_call", finish_call)
    graph.add_node("save_reply", save_reply)
    graph.add_node("remember", remember)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "recall")
    graph.add_edge("recall", "call_model")
    graph.add_conditional_edges("call_model", after_model)
    graph.add_conditional_edges("prepare_call", after_prepare)
    graph.add_conditional_edges("approval_gate", after_gate)
    graph.add_edge("execute_tool", "finish_call")
    graph.add_conditional_edges("finish_call", after_call)
    graph.add_edge("save_reply", "remember")
    graph.add_edge("remember", END)
    return graph.compile(checkpointer=checkpointer)

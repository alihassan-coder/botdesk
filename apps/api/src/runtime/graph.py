"""A run as a LangGraph graph (agents-and-plugins.md §4, handoffs ADR 0014):

    load_context → recall → call_model ─┬─ no tool calls ─→ save_reply → remember
                                        └─ tool calls ─→ prepare_call ─┬─ team.handoff ─→ hand_off ─┐
                                                                       ├─ auto ──→ execute_tool ────┤
                                                                       ├─ ask ───→ approval_gate ───┤
                                                                       └─ deny ─────────────────────┤
                                                      finish_call ←─────────────────────────────────┘
                     (calls left) → prepare_call
                     (none left, tasks handed off) → save_progress → wait_for_tasks → call_model
                     (none left) → call_model

Tool calls are handled one at a time (ADR 0004 §7). A step that handed off tasks ends with the
run paused in `wait_for_tasks` (an `interrupt`, like `approval_gate`) until every task has ended;
then the model reads their results and goes on, writing a new message. The checkpointer saves the state after
every node, keyed by the run id. Each node is safe to run twice (§4.1): when a paused run
resumes, `approval_gate` starts again from its first line, which is why it does nothing but
pause. Side effects happen only in `execute_tool`, after the decision is saved.
"""

import json
import logging
import math
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
    HumanMessage,
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

from src.core.config import Settings
from src.core.database import utcnow
from src.models.bot import Bot, SecurityLevel
from src.models.run import Run
from src.models.task import Task
from src.plugins.registry import ToolRegistry
from src.plugins.team import HANDOFF_TOOL, HandoffArgs, is_core_tool
from src.runtime import tool_pipeline, toolset
from src.runtime.chat_model import (
    ModelPrice,
    ModelUnavailable,
    StandInModel,
    cap_output,
    describe_model_error,
    output_cap,
)
from src.runtime.limits import RunLimits, limit_reached
from src.runtime.memory import MemoryScope, MemoryService
from src.runtime.policy import LEVELS
from src.runtime.prompt import HistoryLine, TaskBrief, Teammate, build_prompt, results_text
from src.runtime.reporter import RunReporter
from src.runtime.token_batcher import BackgroundSender, TokenBatcher
from src.runtime.tool_access import ToolAccessProvider
from src.runtime.tool_pipeline import ToolCallRequest, finished_event
from src.services import pricing, run_service, task_service, tool_execution_service, usage_service
from src.services.mcp_server_service import McpRuntime
from src.services.task_service import Refused
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
    group: bool  # a group chat: messages are labelled with who wrote them (missing in old checkpoints: a DM)
    guest: bool  # pulled into someone's DM by an @mention (ADR 0009; missing in old checkpoints: no)
    hop: int  # 0 when a person's message started the run (missing in old checkpoints: 0)
    memory_on: bool  # the bot's memory switch when the run started (missing in old checkpoints)
    # Oldest first, ending with the trigger: {"fromThisBot", "text", "authorType", "author"}
    # (checkpoints saved before speaker labels have only the first two).
    history: list[dict[str, Any]]
    memories: list[str]
    reply_message_id: str
    reply: str  # the text of every model step so far, joined
    turns: list[dict[str, Any]]  # this run's tool round trips, as LangChain message dicts
    pending_calls: list[dict[str, Any]]  # tool calls not handled yet: {"id", "name", "args"}
    call: CallState
    # Approvals asked for in this run. Kept for checkpoints already saved; the reply's cards
    # now come from the tool calls recorded in the database (`reply_cards`).
    approval_ids: list[str]
    # Handoffs (ADR 0014); all missing in older checkpoints.
    handoff_task_ids: list[str]  # tasks handed off in this stretch, not waited for yet
    shown_execution_ids: list[str]  # tool calls whose cards are in an earlier message of this run
    # A child run's task: {"taskId", "fromBotName", "fromBotHandle", "requesterName"}.
    task: dict[str, Any] | None
    teammates: list[dict[str, Any]]  # {"name", "handle", "role"}: the org's other bots, by name
    more_teammates: int  # how many more bots the organization has than `teammates` lists


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
    # Work that must finish even if the run is stopped or the API shuts down (usage records):
    # it runs as its own tracked task, and the run waits for it without being able to cancel it.
    unstoppable: Callable[[Coroutine[Any, Any, None]], Awaitable[None]]
    registry: ToolRegistry  # every loaded tool; a run gets only its toolset's (`_toolset`)
    tool_timeout_seconds: float
    approval_expiry: timedelta
    settings: Settings  # the hop limit and run limits for runs a reply's @mentions start
    # Defers the runs' jobs in the given transaction (`RunManager.start`), before it commits.
    start_runs: Callable[[AsyncSession, list[Run]], Awaitable[None]]
    # Tools' `ctx.http` and `ctx.connection` (ADR 0010). None: tools get no web access.
    tool_access: ToolAccessProvider | None = None
    # Talking to the organization's MCP servers (ADR 0012). None: MCP tools aren't offered.
    mcp: McpRuntime | None = None

    @property
    def run_ref(self) -> RunRef:
        return RunRef(run_id=self.run_id, org_id=self.org_id, thread_id=self.thread_id, bot_id=self.bot_id)


async def _toolset(deps: RunDeps) -> toolset.Toolset:
    """The tools this run may use now, from the bot's bindings. Read fresh in every node that
    uses tools, so a tool unbound (or an account disconnected) mid-run is refused on resume."""
    async with deps.sessionmaker() as db:
        return await toolset.load(db, deps.registry, deps.run_id, deps.mcp)


def _memory_scope(state: RunState, deps: RunDeps) -> MemoryScope:
    member = state.get("member_id")
    return MemoryScope(org_id=deps.org_id, bot_id=deps.bot_id, member_id=uuid.UUID(member) if member else None)


async def _bot_memory_on(deps: RunDeps) -> bool:
    """The bot's own memory switch (Edit bot). Read fresh, so turning it off applies at once."""
    async with deps.sessionmaker() as db:
        bot = await db.get(Bot, deps.bot_id)
    return bot is not None and bot.memory_enabled


def _last_human_text(state: RunState) -> str:
    """The message the bot is answering: its trigger, the newest message from a person in its
    history (which ends at the trigger). Another bot's message is never the question."""
    return next(
        (
            line["text"]
            for line in reversed(state["history"])
            if not line["fromThisBot"] and line.get("authorType", "user") != "bot"
        ),
        "",
    )


def _history_lines(state: RunState) -> list[HistoryLine]:
    return [
        HistoryLine(
            from_this_bot=line["fromThisBot"],
            text=line["text"],
            author_type=line.get("authorType", "user"),
            author=line.get("author", ""),
        )
        for line in state["history"]
    ]


def _security_level(state: RunState) -> SecurityLevel:
    """The bot's level. Anything unexpected falls back to the strictest one (fail closed)."""
    level = state.get("security_level", "")
    return level if level in LEVELS else "read-only"


async def load_context(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    async with runtime.context.sessionmaker() as db:
        context = await run_service.run_context(db, runtime.context.run_id)
        await db.commit()  # taint carried over from the history is saved on the run
    return {
        "bot_name": context.bot_name,
        "instructions": context.instructions,
        "model_id": context.model_id,
        "security_level": context.security_level,
        "tainted": context.tainted,
        "member_id": str(context.member_id) if context.member_id else None,
        "group": context.group,
        "guest": context.guest,
        "hop": context.hop,
        "memory_on": context.memory_enabled,
        "task": _task_state(context.task) if context.task else None,
        "teammates": [{"name": m.name, "handle": m.handle, "role": m.role} for m in context.teammates],
        "more_teammates": context.more_teammates,
        "history": [
            {
                "fromThisBot": line.from_this_bot,
                "text": line.text,
                "authorType": line.author_type,
                "author": line.author,
            }
            for line in context.history
        ],
        "turns": [],
        "pending_calls": [],
        "approval_ids": [],
    }


def _task_state(task: TaskBrief) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "fromBotName": task.from_bot_name,
        "fromBotHandle": task.from_bot_handle,
        "requesterName": task.requester_name,
    }


def _task_brief(state: RunState) -> TaskBrief | None:
    task = state.get("task")
    if not task:
        return None
    return TaskBrief(
        task_id=str(task.get("taskId", "")),
        task="",
        context=None,
        from_bot_name=str(task.get("fromBotName", "")),
        from_bot_handle=str(task.get("fromBotHandle", "")),
        requester_name=task.get("requesterName"),
    )


def _teammates(state: RunState) -> list[Teammate]:
    return [
        Teammate(name=str(m.get("name", "")), handle=str(m.get("handle", "")), role=str(m.get("role") or ""))
        for m in state.get("teammates", [])
    ]


async def recall(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """The top memories for the message being answered. A memory failure never fails a run."""
    deps = runtime.context
    if not state.get("memory_on", True):  # read with the run's context, a moment ago
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

    tools_of_run = await _toolset(deps)
    prompt = build_prompt(
        bot_name=state["bot_name"],
        instructions=state["instructions"],
        memories=state.get("memories", []),
        history=_history_lines(state),
        group=state.get("group", False),
        guest=state.get("guest", False),
        asked_by_bot=state.get("hop", 0) > 0,
        can_hand_off=tools_of_run.get(HANDOFF_TOOL) is not None,
        teammates=_teammates(state),
        more_teammates=state.get("more_teammates", 0),
        task=_task_brief(state),
    )
    turns = state.get("turns", [])
    messages = [*prompt, *messages_from_dict(turns)]
    prompt_chars = sum(len(str(message.content)) for message in messages)
    price = await deps.price_for(state["model_id"])
    remaining_usd = await _check_budget(deps, price, prompt_chars)
    # The reply's id is chosen at the first step, so every streamed piece and the saved message share it.
    message_id = state.get("reply_message_id") or str(uuid.uuid4())
    earlier = state.get("reply", "")
    try:
        chat_model = await deps.model_for(state["model_id"])
    except ModelUnavailable as error:
        raise RunError(str(error)) from error
    # Each call may pass the budget by at most this many output tokens (budgets are soft, §4.2).
    cap = output_cap(remaining_usd, price.pricing, prompt_chars)
    model = cap_output(_with_tools(chat_model, tools_of_run), chat_model, cap)
    streamed = Streamed()
    try:
        answer = await _stream_reply(
            deps, model, messages, message_id, streamed, separator=STEP_SEPARATOR if earlier else ""
        )
    finally:
        # Recorded however the call ended: tokens a failed or stopped call used are billed too.
        tokens = usage_of(streamed, prompt_chars)
        if tokens and not isinstance(chat_model, StandInModel):  # the stand-in costs nothing
            await deps.unstoppable(_record_usage(deps, price, tokens))
    text = answer.text
    calls = [{"id": call["id"], "name": call["name"], "args": call["args"]} for call in answer.tool_calls]
    return {
        "reply": earlier + STEP_SEPARATOR + text if earlier and text else earlier or text,
        "reply_message_id": message_id,
        "turns": [*turns, message_to_dict(answer)] if calls else turns,
        "pending_calls": calls,
    }


async def _check_budget(deps: RunDeps, price: ModelPrice, prompt_chars: int) -> float | None:
    """Before each model call (§4.2): stop if this month's spend plus a small estimate of this call
    would pass the bot's or the organization's budget. Returns what's left (None = no limit)."""
    estimate = pricing.estimate_usd(price.pricing, prompt_chars)
    async with deps.sessionmaker() as db:
        check = await usage_service.check_budget(
            db, org_id=deps.org_id, bot_id=deps.bot_id, estimate_usd=estimate, now=utcnow()
        )
    if check.stop:
        raise BudgetReached(check.stop)
    return check.remaining_usd


@dataclass
class Streamed:
    """What one model call has sent back so far. The caller holds it, so a call that fails or is
    stopped partway still shows what it used."""

    answer: AIMessageChunk | None = None
    output_chars: int = 0  # reply text and tool call arguments streamed so far
    complete: bool = False  # the stream ended normally

    def add(self, chunk: AIMessageChunk) -> None:
        self.answer = chunk if self.answer is None else self.answer + chunk
        args = sum(len(call.get("args") or "") for call in chunk.tool_call_chunks)
        self.output_chars += len(chunk.text) + args


@dataclass(frozen=True)
class TokensUsed:
    input_tokens: int
    output_tokens: int
    estimated: bool = False  # guessed from characters, not reported by the provider


def usage_of(streamed: Streamed, prompt_chars: int) -> TokensUsed | None:
    """The tokens to record for one call, or None to record nothing.

    - A finished call records what the provider reported (a model that reports nothing records nothing).
    - A call that failed or was stopped records what was reported so far. Providers often report
      output tokens only at the end, so its output counts at least the streamed characters / 4.
    - With nothing reported, a call that streamed something records an estimate: the prompt's
      characters / 4 in, the streamed characters / 4 out. One that streamed nothing records nothing.
    """
    usage = streamed.answer.usage_metadata if streamed.answer is not None else None
    reported = (int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))) if usage else None
    if streamed.complete:
        return TokensUsed(*reported) if reported else None
    guessed_output = math.ceil(streamed.output_chars / pricing.CHARS_PER_TOKEN)
    if reported:
        input_tokens, output_tokens = reported
        if guessed_output > output_tokens:
            return TokensUsed(input_tokens, guessed_output, estimated=True)
        return TokensUsed(input_tokens, output_tokens)
    if not streamed.output_chars:
        return None
    return TokensUsed(prompt_chars // pricing.CHARS_PER_TOKEN, guessed_output, estimated=True)


async def _record_usage(deps: RunDeps, price: ModelPrice, tokens: TokensUsed) -> None:
    """After each model call: one short insert with its tokens and cost."""
    try:
        async with deps.sessionmaker() as db:
            usage_service.record(
                db,
                org_id=deps.org_id,
                bot_id=deps.bot_id,
                run_id=deps.run_id,
                provider=price.provider,
                model_id=price.model_id,
                input_tokens=tokens.input_tokens,
                output_tokens=tokens.output_tokens,
                cost_usd=pricing.cost_usd(price.pricing, tokens.input_tokens, tokens.output_tokens),
                estimated=tokens.estimated,
            )
            await db.commit()
    except Exception:  # the reply matters more than its bookkeeping
        logger.exception("Couldn't record usage for run %s", deps.run_id)


def _with_tools(model: BaseChatModel, tools_of_run: toolset.Toolset) -> Runnable[Any, Any]:
    """The model, told about the tools it may call. Models that can't call tools answer without them."""
    tools = [tool.for_model() for tool in tools_of_run.tools()]
    if not tools:
        return model
    try:
        return model.bind_tools(tools)
    except NotImplementedError:
        return model


async def _stream_reply(
    deps: RunDeps,
    model: Runnable[Any, Any],
    prompt: list[BaseMessage],
    message_id: str,
    streamed: Streamed,
    *,
    separator: str,
) -> AIMessage:
    """Send the reply's text to the chat in small batches as it arrives, and return the whole
    answer (text and tool calls). `separator` goes before the first piece, when there is one.
    The answer builds up in `streamed`, which the caller reads even when this fails."""

    async def save_delta(text: str) -> None:
        await deps.reporter.send("message_delta", {"messageId": message_id, "botId": str(deps.bot_id), "text": text})

    batcher = TokenBatcher()
    async with BackgroundSender(save_delta) as sender:
        try:
            async for chunk in model.astream(prompt):
                streamed.add(chunk)
                if token := str(chunk.text):
                    if separator:
                        token, separator = separator + token, ""
                    if batch := batcher.add(token, now=time.monotonic()):
                        sender.send(batch)
        except Exception as error:
            raise RunError(describe_model_error(error)) from error
        streamed.complete = True
        if rest := batcher.flush():
            sender.send(rest)
    if streamed.answer is None:
        return AIMessage(content="")
    return cast(AIMessage, message_chunk_to_message(streamed.answer))


def after_model(state: RunState) -> Literal["prepare_call", "save_reply"]:
    return "prepare_call" if state.get("pending_calls") else "save_reply"


async def prepare_call(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Validate, classify, ask the policy, and save the decision. No tool runs here."""
    deps = runtime.context
    first, *rest = state["pending_calls"]
    tainted = state.get("tainted", False)
    request = ToolCallRequest(id=first["id"], name=first["name"], args=dict(first.get("args") or {}))
    tools = await _toolset(deps)
    prepared = tool_pipeline.prepare(
        tools, request, level=_security_level(state), tainted=tainted, connections=tools.connections
    )
    async with deps.sessionmaker() as db:
        recorded = await tool_pipeline.record(
            db, deps.run_ref, prepared, tainted=tainted, approval_expiry=deps.approval_expiry
        )
        execution = recorded.execution
        # Core tools (`team.handoff`) send no tool events: the handoff card is what people see.
        if recorded.created and execution.decision in ("deny", "invalid") and not is_core_tool(execution.tool_name):
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


def after_prepare(state: RunState) -> Literal["hand_off", "execute_tool", "approval_gate", "finish_call"]:
    decision = state["call"]["decision"]
    if decision == "auto":
        return "hand_off" if state["call"].get("tool") == HANDOFF_TOOL else "execute_tool"
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


def after_gate(state: RunState) -> Literal["hand_off", "execute_tool", "finish_call"]:
    if state["call"]["decision"] != "approved":
        return "finish_call"
    return "hand_off" if state["call"].get("tool") == HANDOFF_TOOL else "execute_tool"


async def hand_off(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """`team.handoff`: the task, its child run and the child's job, the handoff message (or its new
    card) and the call's `succeeded` record, all in one transaction (ADR 0014 §4). A refused
    handoff marks the call `failed` and makes nothing. Safe to run twice: a call already recorded
    `succeeded` returns its result, and the task's idempotency key finds the task."""
    deps = runtime.context
    call = state["call"]
    execution_id = uuid.UUID(call["executionId"])
    async with deps.sessionmaker() as db:
        row = await tool_execution_service.get(db, execution_id)
        if row is None:
            raise RuntimeError(f"Tool execution {execution_id} is missing")
        if row.status in ("failed", "denied"):
            return {"call": {**call, "result": f"The tool failed: {row.error or 'not done.'}"}}
        if row.status == "succeeded":
            result = row.result or {}
        else:
            outcome = await task_service.hand_off(
                db,
                parent_run_id=deps.run_id,
                tool_call_id=row.tool_call_id,
                args=HandoffArgs.model_validate(row.args),
                message_id=uuid.UUID(state["reply_message_id"]),
                reply_text=state.get("reply", ""),
                exclude_execution_ids=state.get("shown_execution_ids", []),
                level=_security_level(state),
                tainted=state.get("tainted", False),
                settings=deps.settings,
            )
            if isinstance(outcome, Refused):
                await tool_execution_service.settle(db, execution_id, error=outcome.message)
                await db.commit()
                return {"call": {**call, "result": f"The tool failed: {outcome.message}"}}
            if outcome.created and outcome.child is not None:
                await deps.start_runs(db, [outcome.child])
            result = handoff_result(outcome.task)
            await tool_execution_service.settle(db, execution_id, result=result)
            await db.commit()
    deps.reporter.announce()
    task_ids = state.get("handoff_task_ids", [])
    task_id = str(result.get("taskId", ""))
    return {
        "call": {**call, "result": json.dumps(result, ensure_ascii=False)},
        "handoff_task_ids": task_ids if not task_id or task_id in task_ids else [*task_ids, task_id],
    }


def handoff_result(task: Task) -> dict[str, Any]:
    """What the model reads when a handoff is made (or, run again, what became of it)."""
    name, handle = task.to_bot_name or "your teammate", task.to_bot_handle or "teammate"
    if task.status == "failed":
        return {"taskId": str(task.id), "bot": f"@{handle}", "status": task.status, "note": task.error or "It failed."}
    return {
        "taskId": str(task.id),
        "bot": f"@{handle}",
        "status": task.status,
        "note": (
            f"Handed off to {name} (@{handle}). Their result will come back to you when they finish; "
            "you don't need to wait or check."
        ),
    }


async def execute_tool(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Run the tool, at most once (the `tool_executions` record makes sure)."""
    deps = runtime.context
    call = state["call"]
    tools = await _toolset(deps)
    outcome = await tool_pipeline.execute(
        tool_pipeline.ExecuteDeps(
            sessionmaker=deps.sessionmaker,
            tools=tools,
            reporter=deps.reporter,
            run=deps.run_ref,
            timeout_seconds=deps.tool_timeout_seconds,
            access=deps.tool_access,
            connection_ids=tools.connection_ids,
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


def after_call(state: RunState) -> Literal["prepare_call", "save_progress", "call_model"]:
    if state.get("pending_calls"):
        return "prepare_call"
    return "save_progress" if state.get("handoff_task_ids") else "call_model"


async def save_progress(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Before pausing for tasks: (re)write the handoff message with every card of this step (a
    call after the first handoff may have added one). Writing it twice is harmless."""
    deps = runtime.context
    shown = state.get("shown_execution_ids", [])
    async with deps.sessionmaker() as db:
        await task_service.save_segment(
            db,
            run_id=deps.run_id,
            message_id=uuid.UUID(state["reply_message_id"]),
            reply_text=state.get("reply", ""),
            exclude_execution_ids=shown,
        )
        now_shown = await tool_execution_service.execution_ids(db, deps.run_id)
        await db.commit()
    deps.reporter.announce()
    return {"shown_execution_ids": [*shown, *(id_ for id_ in now_shown if id_ not in shown)]}


def wait_for_tasks(state: RunState) -> RunState:
    """Pause until every task handed off in this step has ended. RULE: nothing else happens here
    (like `approval_gate`). The answer is `task_service.resume_answer`: the results, read next as
    other bots' output, and whether any child read outside text."""
    answer = interrupt({"taskIds": state.get("handoff_task_ids", [])})
    results = HumanMessage(content=results_text(list(answer.get("tasks", []))))
    return {
        "turns": [*state.get("turns", []), message_to_dict(results)],
        "handoff_task_ids": [],
        "reply": "",  # the next step writes a new message
        "reply_message_id": "",
        "tainted": state.get("tainted", False) or bool(answer.get("tainted")),
    }


async def save_reply(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Save the reply (with its event) and, in the same transaction, a queued run for each bot it
    @mentions (ADR 0009) with their jobs, or the "chain stopped" notice past the hop limit. Those
    runs wait for this run to finish (one run at a time per chat)."""
    deps = runtime.context
    async with deps.sessionmaker() as db:
        cards = await tool_execution_service.reply_cards(
            db, deps.run_id, exclude_execution_ids=state.get("shown_execution_ids", [])
        )
        saved = await run_service.save_reply(
            db,
            run_id=deps.run_id,
            message_id=uuid.UUID(state["reply_message_id"]),
            text=state.get("reply", ""),
            settings=deps.settings,
            extra_parts=cards,
        )
        await deps.start_runs(db, saved.runs)
        await db.commit()
    deps.reporter.announce()
    return {}


async def remember(state: RunState, runtime: Runtime[RunDeps]) -> RunState:
    """Saving memories costs a model call, so it runs in the background and the reply isn't
    held up. Runs that read outside text (tainted) don't save memories (§9), and neither do
    bots with memory turned off, or runs another bot's message started (hop > 0, ADR 0009):
    memories come from talking with people, not from one bot's output steering another's."""
    deps = runtime.context
    if state.get("tainted") or state.get("hop", 0) > 0 or not state.get("memory_on", True):
        return {}
    # On when the run started: read the switch again, so turning it off applies at once.
    if not await _bot_memory_on(deps):
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
    graph.add_node("hand_off", hand_off)
    graph.add_node("save_progress", save_progress)
    graph.add_node("wait_for_tasks", wait_for_tasks)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "recall")
    graph.add_edge("recall", "call_model")
    graph.add_conditional_edges("call_model", after_model)
    graph.add_conditional_edges("prepare_call", after_prepare)
    graph.add_conditional_edges("approval_gate", after_gate)
    graph.add_edge("execute_tool", "finish_call")
    graph.add_edge("hand_off", "finish_call")
    graph.add_edge("save_progress", "wait_for_tasks")
    graph.add_edge("wait_for_tasks", "call_model")
    graph.add_conditional_edges("finish_call", after_call)
    graph.add_edge("save_reply", "remember")
    graph.add_edge("remember", END)
    return graph.compile(checkpointer=checkpointer)

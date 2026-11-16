"""The provider check for handoffs (ADR 0014): when a parent resumes, the tasks' results reach the
model as a user message straight after the step's tool results. Both kinds of provider adapter
must turn that order into a request their API accepts:

- Anthropic: tool results are user content blocks, so the results message joins the same user
  turn, after the `tool_result` blocks (the API wants those first), and roles still alternate.
- OpenAI-compatible: `assistant` (tool calls) → one `tool` message per call → `user`, which the
  Chat Completions API accepts.

Built offline: the request payload each LangChain class would send, never a network call."""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.model_providers import ProviderKind, adapter_for
from src.runtime.prompt import results_text

RESULTS = results_text(
    [
        {"task": "Draft openers", "botName": "Sales", "botHandle": "sales", "status": "done", "result": "Hi!"},
        {"task": "Pull numbers", "botName": "Research", "botHandle": "research", "status": "failed", "error": "No."},
    ]
)


def _conversation() -> list[BaseMessage]:
    """What the parent's model reads on the step after it resumed."""
    calls = [
        {"name": "team__handoff", "args": {"bot": "@sales", "task": "Draft openers"}, "id": "toolu_1"},
        {"name": "team__handoff", "args": {"bot": "@research", "task": "Pull numbers"}, "id": "toolu_2"},
    ]
    return [
        SystemMessage(content="You are Chief, a bot on a team in BotDesk."),
        HumanMessage(content="Plan tonight's outreach"),
        AIMessage(content="I'll ask Sales and Research.", tool_calls=[{**c, "type": "tool_call"} for c in calls]),
        ToolMessage(content='{"taskId": "1", "status": "queued"}', tool_call_id="toolu_1", name="team__handoff"),
        ToolMessage(content='{"taskId": "2", "status": "queued"}', tool_call_id="toolu_2", name="team__handoff"),
        HumanMessage(content=RESULTS),
    ]


def _payload(kind: ProviderKind, model: str) -> dict[str, Any]:
    chat = adapter_for(kind).chat_model(model, "sk-test", None)
    payload: dict[str, Any] = chat._get_request_payload(_conversation())  # type: ignore[attr-defined]
    return payload


def test_anthropic_puts_the_results_after_the_tool_results_in_one_user_turn() -> None:
    messages = _payload("anthropic", "claude-sonnet-4-5")["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    last = messages[-1]["content"]
    assert [block["type"] for block in last] == ["tool_result", "tool_result", "text"]
    assert [block.get("tool_use_id") for block in last[:2]] == ["toolu_1", "toolu_2"]
    assert last[2]["text"].startswith("<task-results>")


def test_openai_compatible_sends_tool_messages_then_the_results_as_a_user_message() -> None:
    messages = _payload("openai", "gpt-4o")["messages"]

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "tool", "user"]
    assert [m["tool_call_id"] for m in messages[3:5]] == ["toolu_1", "toolu_2"]
    assert [call["id"] for call in messages[2]["tool_calls"]] == ["toolu_1", "toolu_2"]
    assert messages[-1]["content"].startswith("<task-results>")

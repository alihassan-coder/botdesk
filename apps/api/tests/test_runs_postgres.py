"""Bots reply: runs on real Postgres, with a stand-in or scripted model (no network to a provider)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from src.runtime.memory import MemoryScope
from tests.conftest import Postgres, sign_up


class ScriptedModel(BaseChatModel):
    """A chat model that streams the tokens it's given (slowly, if asked), or fails."""

    tokens: list[str] = Field(default_factory=lambda: ["Hello", " there", "!"])
    delay: float = 0.0
    error: str | None = None
    prompts: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="".join(self.tokens)))])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.prompts.append(messages)
        if self.error:
            raise RuntimeError(self.error)
        for token in self.tokens:
            await asyncio.sleep(self.delay)
            yield ChatGenerationChunk(message=AIMessageChunk(content=token))


def use_model(pg: Postgres, model: BaseChatModel) -> None:
    async def model_for(_org_id: uuid.UUID, _model_id: str) -> BaseChatModel:
        return model

    pg.runs.model_for = model_for


async def _bot_chat(client: httpx.AsyncClient) -> tuple[str, str]:
    """Sign up, hire a bot, open its chat. Returns (org path, thread path)."""
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Scout", "instructions": "Be brief."})).json()
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    return org, f"{org}/threads/{thread['id']}"


async def _send(client: httpx.AsyncClient, thread: str, text: str) -> str:
    """Send a message and return the id of the run it started."""
    sent = await client.post(f"{thread}/messages", json={"text": text})
    assert sent.status_code == 201, sent.text
    run_ids: list[str] = sent.json()["runIds"]
    assert len(run_ids) == 1
    return run_ids[0]


def _parse_sse(body: str) -> Iterator[dict[str, Any]]:
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if fields:
            yield {"id": int(fields["id"]), "event": fields["event"], "data": json.loads(fields["data"])}


async def _events(client: httpx.AsyncClient, thread: str, last_event_id: int = 0) -> list[dict[str, Any]]:
    response = await client.get(
        f"{thread}/events", params={"follow": False}, headers={"Last-Event-ID": str(last_event_id)}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return list(_parse_sse(response.text))


async def _wait_for_status(client: httpx.AsyncClient, org: str, run_id: str, status: str) -> None:
    for _ in range(200):
        if (await client.get(f"{org}/runs/{run_id}")).json()["status"] == status:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"run never became {status}")


async def test_posting_a_message_queues_exactly_one_run(pg: Postgres) -> None:
    pg.runs.enabled = False  # look at the run before anything picks it up
    org, thread = await _bot_chat(pg.client)

    run_id = await _send(pg.client, thread, "Hi Scout")

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "queued"
    assert run["stepsUsed"] == 0
    assert run["maxSteps"] == 25


async def test_the_bot_replies_with_the_stand_in_model_when_there_is_no_api_key(pg: Postgres) -> None:
    org, thread = await _bot_chat(pg.client)

    run_id = await _send(pg.client, thread, "Hi Scout")
    await pg.runs.wait_until_idle()

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "succeeded"
    assert run["stepsUsed"] == 1
    messages = (await pg.client.get(f"{thread}/messages")).json()
    assert [m["author"]["type"] for m in messages] == ["user", "bot"]
    assert messages[1]["parts"][0]["text"].startswith("Hi! I'm a stand-in reply")
    assert messages[1]["id"] == run["replyMessageId"]
    chats = (await pg.client.get(f"{org}/threads")).json()
    assert chats[0]["lastMessagePreview"].startswith("Hi! I'm a stand-in reply")


async def test_the_reply_streams_as_events_that_replay_after_last_event_id(pg: Postgres) -> None:
    use_model(pg, ScriptedModel(tokens=["Hello", " there", "!"], delay=0.06))
    _org, thread = await _bot_chat(pg.client)

    run_id = await _send(pg.client, thread, "Hi Scout")
    await pg.runs.wait_until_idle()

    events = await _events(pg.client, thread)
    kinds = [event["event"] for event in events]
    assert kinds[:2] == ["message_saved", "run_started"]
    assert kinds[-2:] == ["message_saved", "run_finished"]
    deltas = [event["data"] for event in events if event["event"] == "message_delta"]
    assert "".join(delta["data"]["text"] for delta in deltas) == "Hello there!"
    reply = events[-2]["data"]["data"]["message"]
    assert {delta["data"]["messageId"] for delta in deltas} == {reply["id"]}
    assert reply["parts"] == [{"type": "text", "text": "Hello there!"}]
    assert events[-1]["data"] == {
        "id": events[-1]["id"],
        "kind": "run_finished",
        "runId": run_id,
        "threadId": thread.rsplit("/", 1)[1],
        "createdAt": events[-1]["data"]["createdAt"],
        "data": {"status": "succeeded"},
    }

    # A browser that saw up to the second event gets exactly the rest.
    replayed = await _events(pg.client, thread, last_event_id=events[1]["id"])
    assert [event["id"] for event in replayed] == [event["id"] for event in events[2:]]


async def test_a_new_stream_without_last_event_id_starts_from_now(pg: Postgres) -> None:
    _org, thread = await _bot_chat(pg.client)
    await _send(pg.client, thread, "Hi")
    await pg.runs.wait_until_idle()

    response = await pg.client.get(f"{thread}/events", params={"follow": False})
    assert list(_parse_sse(response.text)) == []


async def test_runs_in_one_chat_take_turns(pg: Postgres) -> None:
    use_model(pg, ScriptedModel(tokens=["a", "b", "c"], delay=0.05))
    org, thread = await _bot_chat(pg.client)

    first = await _send(pg.client, thread, "One")
    second = await _send(pg.client, thread, "Two")
    await pg.runs.wait_until_idle()

    one = (await pg.client.get(f"{org}/runs/{first}")).json()
    two = (await pg.client.get(f"{org}/runs/{second}")).json()
    assert one["status"] == two["status"] == "succeeded"
    assert two["startedAt"] >= one["finishedAt"]
    # The second run saw the first reply.
    messages = (await pg.client.get(f"{thread}/messages")).json()
    assert [m["author"]["type"] for m in messages] == ["user", "user", "bot", "bot"]


async def test_the_database_allows_one_running_run_per_chat(pg: Postgres) -> None:
    """The guard that holds even across API processes: a second run can't start while one runs."""
    from src.services import run_service

    pg.runs.enabled = False
    _org, thread = await _bot_chat(pg.client)
    first = uuid.UUID(await _send(pg.client, thread, "One"))
    second = uuid.UUID(await _send(pg.client, thread, "Two"))

    async with pg.runs.sessionmaker() as db:
        assert not await run_service.claim_run(db, second, bot_cap=2)  # not its turn
        assert await run_service.claim_run(db, first, bot_cap=2)
        assert not await run_service.claim_run(db, first, bot_cap=2)  # already running
        assert not await run_service.claim_run(db, second, bot_cap=2)  # the chat is busy


async def test_stop_cancels_a_running_run(pg: Postgres) -> None:
    use_model(pg, ScriptedModel(tokens=["slow"] * 100, delay=0.05))
    org, thread = await _bot_chat(pg.client)
    run_id = await _send(pg.client, thread, "Write a novel")
    await _wait_for_status(pg.client, org, run_id, "running")

    stopped = await pg.client.post(f"{org}/runs/{run_id}/cancel")
    await pg.runs.wait_until_idle()

    assert stopped.status_code == 200
    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "cancelled"
    assert run["replyMessageId"] is None
    events = await _events(pg.client, thread)
    assert events[-1]["event"] == "run_finished"
    assert events[-1]["data"]["data"] == {"status": "cancelled"}


async def test_stop_cancels_a_queued_run_at_once(pg: Postgres) -> None:
    pg.runs.enabled = False
    org, thread = await _bot_chat(pg.client)
    run_id = await _send(pg.client, thread, "Hi")

    run = (await pg.client.post(f"{org}/runs/{run_id}/cancel")).json()

    assert run["status"] == "cancelled"
    assert run["finishedAt"] is not None


async def test_a_failing_model_fails_the_run_with_a_readable_error(pg: Postgres) -> None:
    use_model(pg, ScriptedModel(error="the provider is down"))
    org, thread = await _bot_chat(pg.client)

    run_id = await _send(pg.client, thread, "Hi")
    await pg.runs.wait_until_idle()

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "failed"
    assert run["error"] == "The model couldn't reply: the provider is down"
    events = await _events(pg.client, thread)
    assert events[-1]["event"] == "run_failed"
    assert events[-1]["data"]["data"] == {"status": "failed", "error": run["error"]}
    assert len((await pg.client.get(f"{thread}/messages")).json()) == 1  # no half reply saved


async def test_a_run_stops_at_its_step_limit(pg: Postgres) -> None:
    pg.runs.settings = pg.runs.settings.model_copy(update={"run_max_steps": 0})
    org, thread = await _bot_chat(pg.client)

    run_id = await _send(pg.client, thread, "Hi")
    await pg.runs.wait_until_idle()

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "failed"
    assert run["error"] == "This run reached its limit of 0 model steps."


async def test_runs_left_by_a_restart_fail_with_a_clear_message(pg: Postgres) -> None:
    pg.runs.enabled = False
    org, thread = await _bot_chat(pg.client)
    run_id = await _send(pg.client, thread, "Hi")

    await pg.runs.recover_after_restart()

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "failed"
    assert run["error"] == "Interrupted by a restart. Send your message again."


class FakeMemory:
    def __init__(self) -> None:
        self.recalled: list[tuple[MemoryScope, str]] = []
        self.remembered: list[tuple[MemoryScope, list[dict[str, str]]]] = []

    async def recall(self, scope: MemoryScope, query: str) -> list[str]:
        self.recalled.append((scope, query))
        return ["Ali likes short answers"]

    async def remember(self, scope: MemoryScope, conversation: list[dict[str, str]]) -> None:
        self.remembered.append((scope, conversation))


async def test_the_bot_recalls_memories_before_answering_and_saves_new_ones_after(pg: Postgres) -> None:
    memory, model = FakeMemory(), ScriptedModel(tokens=["Sure."])
    pg.runs.memory = memory
    use_model(pg, model)
    _org, thread = await _bot_chat(pg.client)
    me = (await pg.client.get("/api/v1/auth/me")).json()

    await _send(pg.client, thread, "Summarise my week")
    await pg.runs.wait_until_idle()

    scope, query = memory.recalled[0]
    assert query == "Summarise my week"
    assert str(scope.member_id) == me["user"]["id"]  # a DM: the member's own memories
    assert "Things you remember:\n- Ali likes short answers" in str(model.prompts[0][0].content)
    assert memory.remembered == [
        (scope, [{"role": "user", "content": "Summarise my week"}, {"role": "assistant", "content": "Sure."}])
    ]

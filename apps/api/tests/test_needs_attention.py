"""Answering a run that needs attention (ADR 0004 §2), on SQLite where runs really run.

A send that failed after it may have gone out leaves its `tool_executions` row `started`, and the
run waits for a person. "It was done" / "It wasn't done" finishes that row, and the run carries on
from its checkpoint: the model reads the answer, and the call itself never runs again.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from botdesk_plugin_sdk import NoArgs, PluginManifest, ToolContext, ToolSpec
from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from sqlalchemy import select, update

from src.models import Connection, Run, RunEvent, ToolExecution
from src.runtime.chat_model import StandInModel
from src.runtime.runner import RunManager
from tests.conftest import PASSWORD, TEST_SETTINGS, FakeProviders, api_client, sign_up


@dataclass
class Outbox:
    sent: int = 0
    lost_answers: int = 1  # the first sends go out, then their answer is lost


def flaky_plugin(outbox: Outbox) -> PluginManifest:
    async def send(_args: NoArgs, _ctx: ToolContext) -> dict[str, Any]:
        outbox.sent += 1
        if outbox.sent <= outbox.lost_answers:
            raise RuntimeError("the answer was lost")
        return {"sent": True}

    tool = ToolSpec(
        name="send", title="Send", description="Send it.", args_model=NoArgs, risk="external-send", handler=send
    )
    return PluginManifest(id="flaky", name="Flaky", version="1", description="test", tools=(tool,))


class SendingModel(StandInModel):
    """Calls `flaky.send` until it has `tries` answers, then says what the last answer was."""

    tries: int = 1

    def _respond(self, messages: list[BaseMessage]) -> tuple[str, dict[str, Any] | None]:
        answers = [message for message in messages if isinstance(message, ToolMessage)]
        if len(answers) < self.tries:
            return "", {"name": "flaky__send", "args": {}, "id": f"call_{len(answers)}"}
        return f"Last answer: {answers[-1].text}", None


@dataclass
class Chat:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    thread: str
    outbox: Outbox
    model: SendingModel

    @property
    def runs(self) -> RunManager:
        runs: RunManager = self.app.state.runs
        return runs

    async def send(self, text: str = "Send the launch email") -> str:
        sent = await self.client.post(f"{self.thread}/messages", json={"text": text})
        assert sent.status_code == 201, sent.text
        await self.runs.wait_until_idle()
        run_id: str = sent.json()["runIds"][0]
        return run_id

    async def run(self, run_id: str) -> dict[str, Any]:
        body: dict[str, Any] = (await self.client.get(f"{self.org}/runs/{run_id}")).json()
        return body

    async def resolve(self, run_id: str, outcome: str) -> httpx.Response:
        response = await self.client.post(f"{self.org}/runs/{run_id}/resolve", json={"outcome": outcome})
        await self.runs.wait_until_idle()
        return response

    async def executions(self) -> list[ToolExecution]:
        async with self.runs.sessionmaker() as db:
            return list(await db.scalars(select(ToolExecution).order_by(ToolExecution.created_at)))

    async def events(self, run_id: str) -> list[RunEvent]:
        async with self.runs.sessionmaker() as db:
            query = select(RunEvent).where(RunEvent.run_id == uuid.UUID(run_id)).order_by(RunEvent.id)
            return list(await db.scalars(query))

    async def reply(self) -> str:
        text: str = (await self.client.get(f"{self.thread}/messages")).json()[-1]["parts"][-1]["text"]
        return text

    async def approve_the_pending_one(self) -> str:
        (pending,) = (await self.client.get(f"{self.org}/approvals")).json()
        decided = await self.client.post(f"{self.org}/approvals/{pending['id']}/decide", json={"decision": "approve"})
        assert decided.status_code == 200, decided.text
        await self.runs.wait_until_idle()
        approval_id: str = pending["id"]
        return approval_id


async def _chat(app: FastAPI, client: httpx.AsyncClient, level: str) -> Chat:
    outbox, model = Outbox(), SendingModel()

    async def model_for(_org: uuid.UUID, _model: str, _requester: uuid.UUID | None = None) -> BaseChatModel:
        return model

    app.state.runs.enabled = True
    app.state.runs.model_for = model_for
    app.state.runs.registry.register(flaky_plugin(outbox))
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    # A new bot gets every loaded plugin that needs no account, so Flaky too.
    bot = (await client.post(f"{org}/bots", json={"name": "Scout", "securityLevel": level})).json()
    dm = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    return Chat(app, client, org, f"{org}/threads/{dm['id']}", outbox, model)


@pytest.fixture
async def chat(providers: FakeProviders) -> AsyncIterator[Chat]:
    """Ali's DM with an autonomous Scout, which sends without asking."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        yield await _chat(app, client, "autonomous")


@pytest.fixture
async def careful_chat(providers: FakeProviders) -> AsyncIterator[Chat]:
    """The same with Scout at Ask before acting: every send waits for an approval."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        yield await _chat(app, client, "ask-before-acting")


async def _stuck(chat: Chat) -> str:
    """Scout's send went out but its answer was lost: the run waits for a person."""
    run_id = await chat.send()
    run = await chat.run(run_id)
    assert run["status"] == "needs_attention" and "may have been done" in run["error"], run
    assert chat.outbox.sent == 1
    return run_id


async def test_it_was_done_finishes_the_call_and_the_run_carries_on_without_sending_again(chat: Chat) -> None:
    run_id = await _stuck(chat)

    answered = await chat.resolve(run_id, "done")

    assert answered.status_code == 200, answered.text
    assert chat.outbox.sent == 1  # never sent again
    run = await chat.run(run_id)
    assert (run["status"], run["error"]) == ("succeeded", None)
    (execution,) = await chat.executions()
    assert (execution.status, execution.error) == ("succeeded", None)
    assert execution.result == {"note": "A person checked: it was done."}
    # The model read the answer and went on.
    assert await chat.reply() == 'Last answer: {"note": "A person checked: it was done."}'
    events = await chat.events(run_id)
    finished = [event.payload["status"] for event in events if event.kind == "tool_finished"]
    assert finished == ["unknown", "succeeded"]
    paused = [event.kind for event in events].index("run_needs_attention")
    after = events[paused + 1 :]
    assert [event.kind for event in after[:2]] == ["tool_finished", "run_resumed"]
    assert after[1].payload == {"botId": run["botId"], "after": "attention"}
    assert after[-1].kind == "run_finished"
    # The reply keeps the call's line, done.
    message = (await chat.client.get(f"{chat.thread}/messages")).json()[-1]
    assert [part["status"] for part in message["parts"] if part["type"] == "tool-call"] == ["succeeded"]


async def test_it_wasnt_done_fails_the_call_and_a_new_try_asks_again(careful_chat: Chat) -> None:
    chat = careful_chat
    chat.model.tries = 2  # told it wasn't done, Scout tries again
    run_id = await chat.send()
    first_approval = await chat.approve_the_pending_one()
    assert (await chat.run(run_id))["status"] == "needs_attention"

    answered = await chat.resolve(run_id, "not_done")

    assert answered.status_code == 200, answered.text
    assert chat.outbox.sent == 1  # the call itself never ran again
    first, retry = await chat.executions()
    assert (first.status, first.error, first.result) == ("failed", "A person checked: it wasn't done.", None)
    # The model tried again, as a new call, and under Ask before acting that asks again.
    assert (retry.tool_call_id, retry.status) == ("call_1", "waiting_approval")
    assert (await chat.run(run_id))["status"] == "waiting_approval"
    answered_line = [event.payload for event in await chat.events(run_id) if event.kind == "tool_finished"][-1]
    assert (answered_line["status"], answered_line["error"]) == ("failed", "A person checked: it wasn't done.")

    assert await chat.approve_the_pending_one() != first_approval
    assert chat.outbox.sent == 2
    assert (await chat.run(run_id))["status"] == "succeeded"
    assert await chat.reply() == 'Last answer: {"sent": true}'


async def test_an_answer_counts_only_while_the_run_waits_for_one(chat: Chat) -> None:
    run_id = await _stuck(chat)

    assert (await chat.resolve(run_id, "maybe")).status_code == 422
    assert (await chat.resolve(run_id, "done")).status_code == 200
    again = await chat.resolve(run_id, "not_done")  # the first answer won; the run went on

    assert again.status_code == 409
    assert again.json() == {"detail": "This run isn't waiting for anyone to check on it."}
    (execution,) = await chat.executions()
    assert execution.status == "succeeded"
    assert chat.outbox.sent == 1


async def test_a_stopped_run_takes_no_answer(chat: Chat) -> None:
    run_id = await _stuck(chat)
    assert (await chat.client.post(f"{chat.org}/runs/{run_id}/cancel")).json()["status"] == "cancelled"

    late = await chat.resolve(run_id, "done")

    assert late.status_code == 409
    (execution,) = await chat.executions()
    assert execution.status == "started"  # nobody said; it stays as it was


async def test_people_outside_the_chat_cannot_answer(chat: Chat) -> None:
    run_id = await _stuck(chat)
    chat.client.cookies.clear()
    await sign_up(chat.client, name="Mallory", email="mallory@evil.dev")

    assert (await chat.resolve(run_id, "done")).status_code == 404
    (execution,) = await chat.executions()
    assert execution.status == "started"


async def test_a_call_through_a_members_own_account_is_answered_only_by_that_member(chat: Chat) -> None:
    """The same rule as approvals: only the member whose account it used can say what happened."""
    run_id = await _stuck(chat)
    chat.client.cookies.clear()
    sara = await sign_up(chat.client, name="Sara", email="sara@acme.dev")
    signed_in = await chat.client.post("/api/v1/auth/sign-in", json={"email": "ali@acme.dev", "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    async with chat.runs.sessionmaker() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        assert run is not None
        saras = Connection(
            org_id=run.org_id,
            connector_id="flaky",
            owner_kind="member",
            owner_user_id=uuid.UUID(sara["user"]["id"]),
            auth_type="api_key",
            account_label="sara@acme.dev",
            account_ref="sara",
        )
        db.add(saras)
        await db.flush()
        await db.execute(update(ToolExecution).values(connection_id=saras.id))
        await db.commit()

    refused = await chat.resolve(run_id, "done")

    assert refused.status_code == 403
    assert refused.json() == {"detail": "Only the member whose account this uses can decide it."}
    assert (await chat.executions())[0].status == "started"
    assert (await chat.run(run_id))["status"] == "needs_attention"

"""Tools and approvals end to end on real Postgres: the run pauses with LangGraph `interrupt()`,
its checkpoint waits in Postgres, and a decision resumes it with `Command(resume=...)`.
The model is the stand-in (driven by `/tool ...` messages) or a scripted one.
"""

import asyncio
from typing import Any

import httpx
from langchain_core.messages import BaseMessage, ToolMessage
from sqlalchemy import select

from src.models import ToolExecution
from src.runtime.chat_model import StandInModel
from tests.conftest import Postgres, sign_up
from tests.test_runs_postgres import FakeMemory, _events, _send, _wait_for_status, use_model

SEND = "/tool demo.send_email to=sara@acme.dev subject=Launch"


class ScriptedToolModel(StandInModel):
    """Calls the tools in `script` one per step, then answers."""

    script: list[tuple[str, dict[str, Any]]]

    def _respond(self, messages: list[BaseMessage]) -> tuple[str, dict[str, Any] | None]:
        done = sum(isinstance(message, ToolMessage) for message in messages)
        if done < len(self.script):
            name, args = self.script[done]
            return "", {"name": name.replace(".", "__"), "args": args, "id": f"call_{done}"}
        return "All done.", None


async def _chat(client: httpx.AsyncClient, level: str = "ask-before-acting") -> tuple[str, str]:
    """Sign up, hire a bot at this security level, open its chat. Returns (org path, thread path)."""
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Scout", "securityLevel": level})).json()
    thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    return org, f"{org}/threads/{thread['id']}"


async def _executions(pg: Postgres) -> list[ToolExecution]:
    async with pg.runs.sessionmaker() as db:
        return list(await db.scalars(select(ToolExecution).order_by(ToolExecution.created_at)))


async def _pending(client: httpx.AsyncClient, org: str) -> list[dict[str, Any]]:
    approvals: list[dict[str, Any]] = (await client.get(f"{org}/approvals")).json()
    return approvals


async def _paused_on_approval(pg: Postgres, thread: str, text: str) -> tuple[str, dict[str, Any]]:
    run_id = await _send(pg.client, thread, text)
    await pg.runs.wait_until_idle()
    org = thread.split("/threads/")[0]
    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "waiting_approval", run
    (approval,) = await _pending(pg.client, org)
    return run_id, approval


async def test_a_read_tool_runs_without_asking(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)

    run_id = await _send(pg.client, thread, "/tool demo.current_time")
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    (execution,) = await _executions(pg)
    assert (execution.tool_name, execution.status, execution.decision) == ("demo.current_time", "succeeded", "auto")
    kinds = [event["event"] for event in await _events(pg.client, thread)]
    assert kinds.index("tool_started") < kinds.index("tool_finished") < kinds.index("run_finished")
    reply = (await pg.client.get(f"{thread}/messages")).json()[-1]["parts"][-1]["text"]
    assert reply.startswith("Using demo.current_time.\n\nFinished demo.current_time:")


async def test_a_risky_tool_pauses_the_run_and_approving_resumes_it(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)

    run_id, approval = await _paused_on_approval(pg, thread, SEND)

    assert approval["tool"] == "demo.send_email"
    assert approval["runId"] == run_id
    (execution,) = await _executions(pg)
    assert execution.status == "waiting_approval"
    events = await _events(pg.client, thread)
    assert events[-1]["event"] == "approval_requested"
    assert events[-1]["data"]["data"]["approval"]["id"] == approval["id"]

    decided = await pg.client.post(f"{org}/approvals/{approval['id']}/decide", json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    (execution,) = await _executions(pg)
    assert execution.status == "succeeded"
    assert execution.result is not None and execution.result["to"] == "sara@acme.dev"
    replayed = await _events(pg.client, thread, last_event_id=events[-1]["id"])
    after = [event["event"] for event in replayed if event["event"] != "message_delta"]
    assert after == [
        "approval_decided",
        "run_resumed",
        "tool_started",
        "tool_finished",
        "message_saved",
        "run_finished",
    ]
    reply = (await pg.client.get(f"{thread}/messages")).json()[-1]
    assert reply["parts"][0] == {"type": "approval", "approvalId": approval["id"]}
    # The tool line is saved too, so a reloaded chat still says "Used Send email · done".
    assert reply["parts"][1] == {
        "type": "tool-call",
        "toolExecutionId": str(execution.id),
        "tool": "demo.send_email",
        "status": "succeeded",
    }
    assert "Finished demo.send_email" in reply["parts"][-1]["text"]


async def test_a_chat_opened_later_sees_the_paused_run_and_follows_on_from_there(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)
    run_id, approval = await _paused_on_approval(pg, thread, SEND)

    active = (await pg.client.get(f"{thread}/runs", params={"active": True})).json()

    (run,) = active["runs"]
    assert (run["id"], run["status"], run["error"]) == (run_id, "waiting_approval", None)
    events = await _events(pg.client, thread)
    assert active["lastEventId"] == events[-1]["id"]  # the approval_requested event
    # Following from `replayFrom` instead rebuilds the paused run: its start, words and card.
    first_of_run = next(event for event in events if event["data"]["runId"] == run_id)
    assert first_of_run["event"] == "run_started"
    assert active["replayFrom"] == first_of_run["id"] - 1
    replay = await _events(pg.client, thread, last_event_id=active["replayFrom"])
    assert [event["id"] for event in replay] == [event["id"] for event in events if event["id"] > active["replayFrom"]]
    await pg.client.post(f"{org}/approvals/{approval['id']}/decide", json={"decision": "approve"})
    await pg.runs.wait_until_idle()
    followed = await _events(pg.client, thread, last_event_id=active["lastEventId"])
    assert followed[0]["event"] == "approval_decided"
    assert followed[-1]["event"] == "run_finished"
    assert (await pg.client.get(f"{thread}/runs", params={"active": True})).json()["runs"] == []


async def test_denying_resumes_the_run_without_running_the_tool(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)
    run_id, approval = await _paused_on_approval(pg, thread, SEND)

    await pg.client.post(f"{org}/approvals/{approval['id']}/decide", json={"decision": "deny"})
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    (execution,) = await _executions(pg)
    assert execution.status == "denied"
    assert execution.started_at is None
    reply = (await pg.client.get(f"{thread}/messages")).json()[-1]["parts"][-1]["text"]
    assert "A person denied this action" in reply


async def test_edit_and_approve_runs_the_edited_arguments(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)
    _run_id, approval = await _paused_on_approval(pg, thread, SEND)

    edited = {"to": "omar@acme.dev", "subject": "Launch moved", "body": "Thursday now."}
    await pg.client.post(f"{org}/approvals/{approval['id']}/decide", json={"decision": "approve", "editedArgs": edited})
    await pg.runs.wait_until_idle()

    (execution,) = await _executions(pg)
    assert execution.status == "succeeded"
    assert execution.args == edited
    assert execution.result is not None and execution.result["to"] == "omar@acme.dev"


async def test_two_people_approving_at_once_run_the_tool_once(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)
    run_id, approval = await _paused_on_approval(pg, thread, SEND)
    decide = f"{org}/approvals/{approval['id']}/decide"

    responses = await asyncio.gather(
        pg.client.post(decide, json={"decision": "approve"}), pg.client.post(decide, json={"decision": "approve"})
    )
    await pg.runs.wait_until_idle()

    assert sorted(response.status_code for response in responses) == [200, 409]
    (execution,) = await _executions(pg)
    assert execution.status == "succeeded"
    kinds = [event["event"] for event in await _events(pg.client, thread)]
    assert kinds.count("tool_started") == 1
    assert kinds.count("run_resumed") == 1
    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"


async def test_outside_text_taints_the_run_so_even_an_autonomous_bot_asks(pg: Postgres) -> None:
    memory = FakeMemory()
    pg.runs.memory = memory
    use_model(
        pg,
        ScriptedToolModel(
            script=[
                ("demo.read_inbox", {}),
                ("demo.send_email", {"to": "payments@unknown-vendor.example", "subject": "Invoices"}),
            ]
        ),
    )
    org, thread = await _chat(pg.client, level="autonomous")

    run_id, approval = await _paused_on_approval(pg, thread, "Check my inbox")

    assert approval["tainted"] is True
    assert approval["reason"] == "level=Autonomous within limits · risk=external-send · tainted=yes → ask"
    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "waiting_approval"
    await pg.client.post(f"{org}/approvals/{approval['id']}/decide", json={"decision": "deny"})
    await pg.runs.wait_until_idle()
    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    assert memory.remembered == []  # a tainted run saves no memories


async def test_an_autonomous_bot_sends_without_asking_when_the_run_is_clean(pg: Postgres) -> None:
    org, thread = await _chat(pg.client, level="autonomous")

    run_id = await _send(pg.client, thread, SEND)
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    assert await _pending(pg.client, org) == []
    (execution,) = await _executions(pg)
    assert execution.status == "succeeded"


async def test_a_read_only_bot_is_refused_and_told_why(pg: Postgres) -> None:
    org, thread = await _chat(pg.client, level="read-only")

    run_id = await _send(pg.client, thread, SEND)
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
    (execution,) = await _executions(pg)
    assert (execution.status, execution.decision) == ("denied", "deny")
    finished = [e for e in await _events(pg.client, thread) if e["event"] == "tool_finished"]
    assert finished[0]["data"]["data"]["status"] == "denied"
    reply = (await pg.client.get(f"{thread}/messages")).json()[-1]["parts"][-1]["text"]
    assert "Not allowed: this bot's security level (Read only)" in reply


async def test_stop_cancels_a_paused_run_and_a_late_approval_does_nothing(pg: Postgres) -> None:
    org, thread = await _chat(pg.client)
    run_id, approval = await _paused_on_approval(pg, thread, SEND)

    stopped = (await pg.client.post(f"{org}/runs/{run_id}/cancel")).json()
    late = await pg.client.post(f"{org}/approvals/{approval['id']}/decide", json={"decision": "approve"})
    await pg.runs.wait_until_idle()

    assert stopped["status"] == "cancelled"
    assert late.status_code == 409
    (execution,) = await _executions(pg)
    assert execution.status == "denied"
    await _wait_for_status(pg.client, org, run_id, "cancelled")

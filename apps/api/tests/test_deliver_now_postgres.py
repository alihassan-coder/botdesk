"""Messages while a bot is working (ADR 0022), on real Postgres: "send now" reaches the working run
at its next step; "queue" waits its turn; only the run's own requester can steer it."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import Field
from sqlalchemy import select

from src.models import Run
from src.services.run_service import READ_WHILE_WORKING
from tests.conftest import Postgres
from tests.test_approvals_postgres import ScriptedToolModel, _chat
from tests.test_member_keys import _team
from tests.test_members import _sign_in
from tests.test_runs_postgres import _events, use_model


class RecordingToolModel(ScriptedToolModel):
    """The scripted tool model, keeping every prompt it was given."""

    seen: list[list[BaseMessage]] = Field(default_factory=list)

    def _respond(self, messages: list[BaseMessage]) -> tuple[str, dict[str, Any] | None]:
        self.seen.append(list(messages))
        return super()._respond(messages)


async def _post(pg: Postgres, thread: str, text: str, **extra: str) -> dict[str, Any]:
    sent = await pg.client.post(f"{thread}/messages", json={"text": text, **extra})
    assert sent.status_code == 201, sent.text
    body: dict[str, Any] = sent.json()
    return body


async def _runs(pg: Postgres) -> dict[str, Run]:
    async with pg.runs.sessionmaker() as db:
        return {str(run.id): run for run in await db.scalars(select(Run))}


async def _go(pg: Postgres) -> None:
    """Let the queued runs start, and wait until every run is done or paused."""
    pg.runs.enabled = True
    await pg.runs.pick_up_stuck_runs()
    await pg.runs.wait_until_idle()


async def test_a_message_sent_now_is_read_at_the_working_runs_next_step(pg: Postgres) -> None:
    model = RecordingToolModel(script=[("demo.current_time", {})])
    use_model(pg, model)
    pg.runs.enabled = False
    _org, thread = await _chat(pg.client)
    first = await _post(pg, thread, "What time is it?")
    later = await _post(pg, thread, "And say it in French", delivery="now")
    (first_run,), (later_run,) = first["runIds"], later["runIds"]
    assert (await _runs(pg))[later_run].deliver_now

    await _go(pg)

    runs = await _runs(pg)
    assert runs[first_run].status == "succeeded"
    assert (runs[later_run].status, runs[later_run].error) == ("cancelled", READ_WHILE_WORKING)
    # The working run's first step already had the new message, after the one it answers.
    prompt = model.seen[0]
    assert isinstance(prompt[-1], HumanMessage)
    assert "sent a new message while you were working" in str(prompt[-1].content)
    assert str(prompt[-1].content).endswith("And say it in French")
    # And it stays in the conversation for the steps after the tool call.
    assert any("And say it in French" in str(m.content) for m in model.seen[-1] if isinstance(m, HumanMessage))
    replies = [m for m in (await pg.client.get(f"{thread}/messages")).json() if m["author"]["type"] == "bot"]
    assert len(replies) == 1  # one answer for both messages
    events = await _events(pg.client, thread)
    assert {"messageId": later["id"]} in [e["data"]["data"] for e in events if e["event"] == "message_read"]
    assert any(e["event"] == "run_finished" and e["data"]["runId"] == later_run for e in events)


async def test_a_queued_message_waits_its_turn_and_gets_its_own_answer(pg: Postgres) -> None:
    use_model(pg, RecordingToolModel(script=[]))
    pg.runs.enabled = False
    _org, thread = await _chat(pg.client)
    first = await _post(pg, thread, "First")
    later = await _post(pg, thread, "Second", delivery="queue")

    await _go(pg)

    runs = await _runs(pg)
    assert runs[first["runIds"][0]].status == "succeeded"
    assert runs[later["runIds"][0]].status == "succeeded"
    assert not runs[later["runIds"][0]].deliver_now
    replies = [m for m in (await pg.client.get(f"{thread}/messages")).json() if m["author"]["type"] == "bot"]
    assert len(replies) == 2


async def test_another_members_message_never_steers_a_run_working_for_you(pg: Postgres) -> None:
    """In a group, Sara's "send now" doesn't reach the run working for Ali: it waits for its own run."""
    use_model(pg, RecordingToolModel(script=[]))
    pg.runs.enabled = False
    org, ali, sara = await _team(pg.client)  # Sara is signed in
    bot = (await pg.client.post(f"{org}/bots", json={"name": "Scout"})).json()
    people = [ali["user"]["id"], sara["user"]["id"]]
    group = (
        await pg.client.post(
            f"{org}/threads/groups", json={"title": "Launch", "botIds": [bot["id"]], "userIds": people}
        )
    ).json()
    thread = f"{org}/threads/{group['id']}"
    pg.client.cookies.clear()
    await _sign_in(pg.client, "ali@acme.dev")
    alis = await _post(pg, thread, "Plan the launch")
    pg.client.cookies.clear()
    await _sign_in(pg.client, "sara@acme.dev")
    saras = await _post(pg, thread, "Use the new date", delivery="now")

    await _go(pg)

    runs = await _runs(pg)
    assert runs[alis["runIds"][0]].status == "succeeded"
    assert runs[saras["runIds"][0]].status == "succeeded"  # answered by its own run, not taken

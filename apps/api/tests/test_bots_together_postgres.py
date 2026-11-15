"""Bots working together end to end on real Postgres (ADR 0009): a reply that @mentions a bot
starts its run after the reply's run ends, chains stop at the hop limit with a notice, taint
travels along a chain, and runs another bot started don't save memories."""

import itertools
import re
import uuid
from typing import Any

import httpx
from langchain_core.messages import BaseMessage
from pydantic import Field
from sqlalchemy import select

from src.models import Run
from src.runtime.chat_model import StandInModel
from tests.conftest import Postgres, sign_up
from tests.test_runs_postgres import FakeMemory, _events, use_model

CHAIN_STOPPED = "Stopped a chain of bot replies after 3 hops."


class ByBotModel(StandInModel):
    """Each bot says its next line from `lines` (found by the "You are <name>," in the prompt), then
    "Done."; anything else (a `/tool` command from a person) goes to the stand-in."""

    lines: dict[str, list[str]] = Field(default_factory=dict)
    prompts: dict[str, list[list[BaseMessage]]] = Field(default_factory=dict)

    def _respond(self, messages: list[BaseMessage]) -> tuple[str, dict[str, Any] | None]:
        text, call = super()._respond(messages)
        if call or text.startswith("Finished "):
            return text, call
        found = re.search(r"You are ([^,]+),", str(messages[0].content))
        name = found.group(1) if found else ""
        self.prompts.setdefault(name, []).append(messages)
        queue = self.lines.get(name, [])
        return (queue.pop(0) if queue else "Done."), None


async def _team(client: httpx.AsyncClient, *names: str) -> tuple[str, dict[str, str]]:
    """Sara's organization with these bots. Returns (org path, {name: bot id})."""
    me = await sign_up(client, name="Sara Khan", email="sara@acme.dev")
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bots = {name: (await client.post(f"{org}/bots", json={"name": name})).json()["id"] for name in names}
    return org, bots


async def _runs(pg: Postgres) -> list[Run]:
    async with pg.runs.sessionmaker() as db:
        return list(await db.scalars(select(Run).order_by(Run.created_at)))


async def test_a_chain_of_mentions_runs_one_bot_at_a_time_and_stops_at_the_hop_limit(pg: Postgres) -> None:
    model = ByBotModel(
        lines={
            "Chief": ["@scout research this", "@scout once more"],
            "Scout": ["@reader summarise it"],
            "Reader": ["@chief over to you"],
        }
    )
    use_model(pg, model)
    org, bots = await _team(pg.client, "Chief", "Scout", "Reader")
    group = (
        await pg.client.post(f"{org}/threads/groups", json={"title": "Launch", "botIds": list(bots.values())})
    ).json()
    thread = f"{org}/threads/{group['id']}"

    sent = await pg.client.post(f"{thread}/messages", json={"text": "Plan the launch"})  # to the lead, Chief
    await pg.runs.wait_until_idle()

    runs = await _runs(pg)
    names = {bot_id: name for name, bot_id in bots.items()}
    assert [(names[str(run.bot_id)], run.hop, run.status) for run in runs] == [
        ("Chief", 0, "succeeded"),
        ("Scout", 1, "succeeded"),
        ("Reader", 2, "succeeded"),
        ("Chief", 3, "succeeded"),
    ]
    assert str(runs[0].id) == sent.json()["runIds"][0]
    assert [run.parent_run_id for run in runs] == [None, runs[0].id, runs[1].id, runs[2].id]
    assert [run.trigger_message_id for run in runs[1:]] == [run.reply_message_id for run in runs[:-1]]
    # Never two at once: each started after the one before it finished.
    for before, after in itertools.pairwise(runs):
        assert before.finished_at is not None and after.started_at is not None
        assert after.started_at >= before.finished_at
    messages = (await pg.client.get(f"{thread}/messages")).json()
    assert [(m["author"]["type"], m["parts"][-1]["text"]) for m in messages] == [
        ("user", "Plan the launch"),
        ("bot", "@scout research this"),
        ("bot", "@reader summarise it"),
        ("bot", "@chief over to you"),
        ("bot", "@scout once more"),
        ("system", CHAIN_STOPPED),
    ]
    kinds = [(event["event"], event["data"]["runId"]) for event in await _events(pg.client, thread)]
    assert kinds.count(("run_started", str(runs[3].id))) == 1
    # Scout's run was hop 1: Reader saw Scout's message as another bot's output, not a request.
    reader_prompt = model.prompts["Reader"][0]
    assert str(reader_prompt[-1].content).startswith('<bot-message from="Scout (@scout)">')


async def test_taint_travels_along_a_chain(pg: Postgres) -> None:
    # Reader reads the inbox (outside text: tainted), then hands over to Auto, which hands to Scout.
    model = ByBotModel(lines={"Auto": ["@scout your turn"]})
    use_model(pg, model)
    org, bots = await _team(pg.client, "Reader", "Auto", "Scout")
    group = (
        await pg.client.post(f"{org}/threads/groups", json={"title": "Inbox", "botIds": list(bots.values())})
    ).json()
    thread = f"{org}/threads/{group['id']}"

    await pg.client.post(f"{thread}/messages", json={"text": "@reader /tool demo.read_inbox"})
    await pg.runs.wait_until_idle()
    (reader,) = await _runs(pg)
    assert (reader.status, reader.tainted) == ("succeeded", True)
    # The stand-in's reply after a tool doesn't mention anyone; ask Auto to pick it up.
    await pg.client.post(f"{thread}/messages", json={"text": "@auto what did Reader find?"})
    await pg.runs.wait_until_idle()

    _, auto, scout = await _runs(pg)
    assert (auto.hop, auto.tainted) == (0, True)  # its history holds Reader's tainted reply
    assert (scout.hop, scout.parent_run_id, scout.tainted) == (1, auto.id, True)


async def test_a_guest_answers_in_a_dm_and_only_runs_people_started_save_memories(pg: Postgres) -> None:
    memory = FakeMemory()
    pg.runs.memory = memory
    use_model(pg, ByBotModel(lines={"Writer": ["Draft ready. @chief please review"]}))
    org, bots = await _team(pg.client, "Chief", "Writer")
    dm = (await pg.client.post(f"{org}/threads/dm", json={"botId": bots["Chief"]})).json()
    thread = f"{org}/threads/{dm['id']}"
    me = (await pg.client.get("/api/v1/auth/me")).json()

    await pg.client.post(f"{thread}/messages", json={"text": "@writer draft the announcement"})
    await pg.runs.wait_until_idle()

    writer, chief = await _runs(pg)
    assert (str(writer.bot_id), writer.hop, writer.status) == (bots["Writer"], 0, "succeeded")
    assert (str(chief.bot_id), chief.hop, chief.parent_run_id) == (bots["Chief"], 1, writer.id)
    # Both read this member's memories with their own bot; only the guest's run (a person asked) saves.
    assert {(str(scope.bot_id), scope.member_id) for scope, _ in memory.recalled} == {
        (bots["Writer"], uuid.UUID(me["user"]["id"])),
        (bots["Chief"], uuid.UUID(me["user"]["id"])),
    }
    assert [str(scope.bot_id) for scope, _ in memory.remembered] == [bots["Writer"]]
    messages = (await pg.client.get(f"{thread}/messages")).json()
    assert [m["author"]["id"] for m in messages] == [me["user"]["id"], bots["Writer"], bots["Chief"]]

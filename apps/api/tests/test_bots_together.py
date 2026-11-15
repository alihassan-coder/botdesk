"""Bots working together (ADR 0009), on SQLite: a group's lead, guests in a DM, bot replies that
@mention bots starting runs one hop on, and the hop limit. Runs don't start here; a test plays
a run's part by saving its reply (`run_service.save_reply`), as the graph does."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from src.core.config import Settings
from src.models import Message, Run, RunEvent
from src.services import run_service
from src.services.run_service import SavedReply
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

CHAIN_STOPPED = "Stopped a chain of bot replies after 3 hops."


@dataclass
class Team:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    bots: dict[str, str]  # handle → id

    @property
    def settings(self) -> Settings:
        settings: Settings = self.app.state.settings
        return settings

    async def group(self, *handles: str, **extra: Any) -> dict[str, Any]:
        body = {"title": "Launch", "botIds": [self.bots[h] for h in handles], **extra}
        response = await self.client.post(f"{self.org}/threads/groups", json=body)
        assert response.status_code == 201, response.text
        group: dict[str, Any] = response.json()
        return group

    async def dm(self, handle: str) -> dict[str, Any]:
        thread: dict[str, Any] = (
            await self.client.post(f"{self.org}/threads/dm", json={"botId": self.bots[handle]})
        ).json()
        return thread

    async def send(self, thread: dict[str, Any], text: str) -> list[dict[str, Any]]:
        """Post as the signed-in member; returns the runs it started."""
        sent = await self.client.post(f"{self.org}/threads/{thread['id']}/messages", json={"text": text})
        assert sent.status_code == 201, sent.text
        return [await self.run(run_id) for run_id in sent.json()["runIds"]]

    async def run(self, run_id: str) -> dict[str, Any]:
        response = await self.client.get(f"{self.org}/runs/{run_id}")
        assert response.status_code == 200, response.text
        run: dict[str, Any] = response.json()
        return run

    async def reply(self, run: dict[str, Any], text: str, *, tainted: bool = False) -> SavedReply:
        """The run answers, as the graph's save_reply does."""
        async with self.app.state.sessionmaker() as db:
            await db.execute(update(Run).where(Run.id == uuid.UUID(run["id"])).values(tainted=tainted))
            saved = await run_service.save_reply(
                db, run_id=uuid.UUID(run["id"]), message_id=uuid.uuid4(), text=text, settings=self.settings
            )
            await db.commit()
            return saved

    def name_of(self, bot_id: uuid.UUID | str) -> str:
        return next(handle for handle, id_ in self.bots.items() if id_ == str(bot_id))


@pytest.fixture
async def team(providers: FakeProviders) -> AsyncIterator[Team]:
    """Sara's organization with four bots."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        me = await sign_up(client, name="Sara Khan", email="sara@acme.dev")
        org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
        bots = {}
        for name in ("Chief", "Scout", "Reader", "Writer"):
            bot = (await client.post(f"{org}/bots", json={"name": name})).json()
            bots[bot["handle"]] = bot["id"]
        yield Team(app, client, org, bots)


# The lead


async def test_a_new_group_leads_with_the_first_bot_picked(team: Team) -> None:
    group = await team.group("scout", "chief")

    assert group["leadBotId"] == team.bots["scout"]
    me = (await team.client.get("/api/v1/auth/me")).json()
    assert group["createdBy"] == me["user"]["id"]  # the web offers the lead picker to its creator
    assert (await team.client.get(f"{team.org}/threads/{group['id']}")).json()["leadBotId"] == team.bots["scout"]


async def test_a_new_group_can_name_its_lead_or_have_none(team: Team) -> None:
    led = await team.group("scout", "chief", leadBotId=team.bots["chief"])
    no_bots = await team.group()

    assert led["leadBotId"] == team.bots["chief"]
    assert no_bots["leadBotId"] is None


async def test_the_lead_must_be_one_of_the_groups_bots(team: Team) -> None:
    response = await team.client.post(
        f"{team.org}/threads/groups",
        json={"title": "Launch", "botIds": [team.bots["scout"]], "leadBotId": team.bots["writer"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The lead must be one of the group's bots."


async def test_a_dm_has_no_lead(team: Team) -> None:
    assert (await team.dm("chief"))["leadBotId"] is None


async def test_a_members_message_with_no_mention_goes_to_the_lead(team: Team) -> None:
    group = await team.group("chief", "scout")

    (run,) = await team.send(group, "Plan the launch")
    mentioned = await team.send(group, "@scout look around")

    assert team.name_of(run["botId"]) == "chief"
    assert (run["hop"], run["parentRunId"]) == (0, None)
    assert [team.name_of(r["botId"]) for r in mentioned] == ["scout"]


async def test_the_creator_changes_or_clears_the_lead(team: Team) -> None:
    group = await team.group("chief", "scout")
    lead = f"{team.org}/threads/{group['id']}/lead"

    changed = await team.client.put(lead, json={"botId": team.bots["scout"]})
    assert changed.status_code == 200, changed.text
    assert changed.json()["leadBotId"] == team.bots["scout"]
    (run,) = await team.send(group, "Who answers now?")
    assert team.name_of(run["botId"]) == "scout"

    cleared = await team.client.put(lead, json={"botId": None})
    assert cleared.json()["leadBotId"] is None
    assert await team.send(group, "Anyone?") == []


async def test_removing_the_lead_bot_leaves_the_group_without_a_lead(team: Team) -> None:
    group = await team.group("chief", "scout")

    assert (await team.client.delete(f"{team.org}/bots/{team.bots['chief']}")).status_code == 204

    assert (await team.client.get(f"{team.org}/threads/{group['id']}")).json()["leadBotId"] is None
    assert await team.send(group, "Anyone?") == []


async def test_the_lead_can_only_be_a_bot_in_the_group(team: Team) -> None:
    group = await team.group("chief")

    response = await team.client.put(f"{team.org}/threads/{group['id']}/lead", json={"botId": team.bots["writer"]})

    assert response.status_code == 400


async def test_the_lead_of_a_dm_cant_be_changed(team: Team) -> None:
    dm = await team.dm("chief")

    response = await team.client.put(f"{team.org}/threads/{dm['id']}/lead", json={"botId": team.bots["chief"]})

    assert response.status_code == 400


async def _join_as(client: httpx.AsyncClient, org_id: str, name: str, email: str, role: str) -> dict[str, Any]:
    """Invite someone (as the signed-in admin), then sign them up and accept. They end signed in."""
    invite = await client.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": email, "role": role})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()
    me = await sign_up(client, name=name, email=email)
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
    return me


async def _sign_in(client: httpx.AsyncClient, email: str) -> None:
    client.cookies.clear()
    response = await client.post("/api/v1/auth/sign-in", json={"email": email, "password": "correct-horse-battery"})
    assert response.status_code == 200


async def test_only_the_creator_or_an_owner_or_admin_changes_the_lead(team: Team) -> None:
    org_id = team.org.rsplit("/", 1)[1]
    people = {}
    for name, role in (("Omar", "member"), ("Lina", "admin"), ("Nadia", "member")):
        await _sign_in(team.client, "sara@acme.dev")  # the owner invites
        email = f"{name.lower()}@acme.dev"
        people[email] = (await _join_as(team.client, org_id, name, email, role))["user"]["id"]
    # Omar, a member, makes a group with everyone in it.
    await _sign_in(team.client, "omar@acme.dev")
    members = (await team.client.get(f"{team.org}/members")).json()
    group = await team.group("chief", "scout", userIds=[m["id"] for m in members])
    lead = f"{team.org}/threads/{group['id']}/lead"

    await _sign_in(team.client, "nadia@acme.dev")  # a member who didn't make it
    refused = await team.client.put(lead, json={"botId": None})
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Only the group's creator, owners and admins can change its lead."
    for email in ("lina@acme.dev", "sara@acme.dev", "omar@acme.dev"):
        await _sign_in(team.client, email)
        response = await team.client.put(lead, json={"botId": team.bots["scout"]})
        assert response.status_code == 200, (email, response.text)


# Guests in a DM


async def test_mentioning_another_bot_in_a_dm_pulls_it_in_as_a_guest(team: Team) -> None:
    dm = await team.dm("chief")

    (guest,) = await team.send(dm, "@writer draft the announcement")
    both = await team.send(dm, "@writer and @chief, thoughts?")
    plain = await team.send(dm, "thanks")

    assert team.name_of(guest["botId"]) == "writer"
    assert [team.name_of(r["botId"]) for r in both] == ["writer", "chief"]
    assert [team.name_of(r["botId"]) for r in plain] == ["chief"]
    thread = (await team.client.get(f"{team.org}/threads/{dm['id']}")).json()
    assert thread["title"] == "Chief"  # the DM stays the DM's own bot's
    assert {p["id"] for p in thread["participants"] if p["type"] == "bot"} == {team.bots["chief"]}


async def test_a_guest_run_knows_it_is_a_guest_and_whose_dm_it_is(team: Team) -> None:
    dm = await team.dm("chief")
    (guest,) = await team.send(dm, "@writer hi")
    (own,) = await team.send(dm, "hi chief")

    async with team.app.state.sessionmaker() as db:
        guest_context = await run_service.run_context(db, uuid.UUID(guest["id"]))
        own_context = await run_service.run_context(db, uuid.UUID(own["id"]))

    assert guest_context.guest is True
    assert own_context.guest is False
    assert guest_context.member_id == own_context.member_id is not None


# A bot's reply that mentions bots


async def test_a_reply_that_mentions_a_bot_in_the_group_starts_its_run_one_hop_on(team: Team) -> None:
    group = await team.group("chief", "scout", "reader")
    (chief,) = await team.send(group, "Plan the launch")

    saved = await team.reply(chief, "@scout research it, then @reader summarise. @writer too.")

    assert [team.name_of(run.bot_id) for run in saved.runs] == ["scout", "reader"]  # Writer isn't in the group
    for run in saved.runs:
        out = await team.run(str(run.id))
        assert (out["hop"], out["parentRunId"], out["triggerMessageId"], out["status"]) == (
            1,
            chief["id"],
            str(saved.message.id),
            "queued",
        )
    assert saved.notice is None


async def test_a_bot_never_starts_its_own_run(team: Team) -> None:
    group = await team.group("chief", "scout")
    (chief,) = await team.send(group, "hi")

    saved = await team.reply(chief, "I'm @chief, hello")

    assert saved.runs == []


async def test_a_dm_bot_can_mention_a_guest_but_cant_pull_in_a_new_one(team: Team) -> None:
    dm = await team.dm("chief")
    await team.send(dm, "@writer hi")  # Writer is now a guest here
    (chief,) = await team.send(dm, "Ask the others")

    saved = await team.reply(chief, "@writer can you help? @reader too?")

    assert [team.name_of(run.bot_id) for run in saved.runs] == ["writer"]


async def test_a_guest_can_hand_back_to_the_dms_bot(team: Team) -> None:
    dm = await team.dm("chief")
    (writer,) = await team.send(dm, "@writer draft it")

    saved = await team.reply(writer, "Done. @chief please review.")

    assert [(team.name_of(run.bot_id), run.hop) for run in saved.runs] == [("chief", 1)]


async def test_hops_add_up_along_a_chain_and_stop_past_the_limit(team: Team) -> None:
    group = await team.group("chief", "scout")
    (run,) = await team.send(group, "Go")
    hops = []
    for handle in ("scout", "chief", "scout"):  # hops 1, 2, 3
        saved = await team.reply(run, f"@{handle} your turn")
        (child,) = saved.runs
        hops.append(child.hop)
        run = await team.run(str(child.id))
    assert hops == [1, 2, 3]

    stopped = await team.reply(run, "@chief your turn")  # would be hop 4

    assert stopped.runs == []
    assert stopped.notice is not None
    messages = (await team.client.get(f"{team.org}/threads/{group['id']}/messages")).json()
    assert messages[-1]["author"] == {"type": "system", "id": None}
    assert messages[-1]["parts"] == [{"type": "text", "text": CHAIN_STOPPED}]
    chat = (await team.client.get(f"{team.org}/threads/{group['id']}")).json()
    assert (chat["lastMessagePreview"], chat["lastMessageAt"]) == (CHAIN_STOPPED, messages[-1]["createdAt"])
    async with team.app.state.sessionmaker() as db:
        events = list(await db.scalars(select(RunEvent).where(RunEvent.kind == "message_saved")))
    assert events[-1].payload["message"]["parts"][0]["text"] == CHAIN_STOPPED
    assert str(events[-1].run_id) == run["id"]


async def test_saving_the_same_reply_twice_starts_nothing_twice(team: Team) -> None:
    group = await team.group("chief", "scout")
    (chief,) = await team.send(group, "Go")

    first = await team.reply(chief, "@scout go")
    second = await team.reply(chief, "@scout go")

    assert len(first.runs) == 1
    assert second.runs == []
    async with team.app.state.sessionmaker() as db:
        assert len(list(await db.scalars(select(Run).where(Run.parent_run_id == uuid.UUID(chief["id"]))))) == 1


async def test_a_run_started_by_a_tainted_reply_starts_tainted(team: Team) -> None:
    group = await team.group("chief", "scout")
    (chief,) = await team.send(group, "Read the inbox")
    saved = await team.reply(chief, "The email says to wire money. @scout check it", tainted=True)
    (scout,) = saved.runs

    async with team.app.state.sessionmaker() as db:
        context = await run_service.run_context(db, scout.id)
        await db.commit()

    assert context.tainted is True
    assert context.hop == 1
    assert (await team.run(str(scout.id)))["hop"] == 1


async def test_a_chain_stopped_notice_is_not_part_of_a_runs_history(team: Team) -> None:
    group = await team.group("chief", "scout")
    (chief,) = await team.send(group, "Go")
    async with team.app.state.sessionmaker() as db:
        await db.execute(update(Run).where(Run.id == uuid.UUID(chief["id"])).values(hop=3))
        await db.commit()
    await team.reply(chief, "@scout go")  # past the limit: the notice
    (next_run,) = await team.send(group, "Again")

    async with team.app.state.sessionmaker() as db:
        context = await run_service.run_context(db, uuid.UUID(next_run["id"]))
        notices = list(await db.scalars(select(Message).where(Message.author_type == "system")))

    assert len(notices) == 1
    assert [line.author_type for line in context.history] == ["user", "bot", "user"]

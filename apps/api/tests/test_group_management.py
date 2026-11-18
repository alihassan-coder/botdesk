"""Managing a group: rename it, add and remove people and bots. Its creator, and the
organization's owners and admins who are in it, may (the same rule as changing the lead, ADR 0009)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from src.controllers import thread_controller
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up, sql_statements


@dataclass
class Org:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    bots: dict[str, str]  # name → id
    people: dict[str, str]  # email → user id

    async def sign_in(self, email: str) -> None:
        self.client.cookies.clear()
        response = await self.client.post(
            "/api/v1/auth/sign-in", json={"email": email, "password": "correct-horse-battery"}
        )
        assert response.status_code == 200

    async def group(self, *, bots: list[str], people: list[str]) -> dict[str, Any]:
        body = {
            "title": "Launch",
            "botIds": [self.bots[b] for b in bots],
            "userIds": [self.people[p] for p in people],
        }
        response = await self.client.post(f"{self.org}/threads/groups", json=body)
        assert response.status_code == 201, response.text
        group: dict[str, Any] = response.json()
        return group

    def path(self, group: dict[str, Any], rest: str = "") -> str:
        return f"{self.org}/threads/{group['id']}{rest}"

    async def add(
        self, group: dict[str, Any], *, bots: tuple[str, ...] = (), people: tuple[str, ...] = ()
    ) -> httpx.Response:
        body = {"botIds": [self.bots[b] for b in bots], "userIds": [self.people[p] for p in people]}
        return await self.client.post(self.path(group, "/participants"), json=body)

    async def remove(self, group: dict[str, Any], kind: str, participant_id: str) -> httpx.Response:
        return await self.client.delete(self.path(group, f"/participants/{kind}/{participant_id}"))


@pytest.fixture
async def acme(providers: FakeProviders) -> AsyncIterator[Org]:
    """Sara owns Acme; Lina is an admin; Omar and Nadia are members. Three bots."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        me = await sign_up(client, name="Sara", email="sara@acme.dev")
        org_id = me["organizations"][0]["id"]
        org = f"/api/v1/orgs/{org_id}"
        bots = {}
        for name in ("Chief", "Scout", "Writer"):
            bots[name] = (await client.post(f"{org}/bots", json={"name": name})).json()["id"]
        people = {"sara@acme.dev": me["user"]["id"]}
        for name, role in (("Lina", "admin"), ("Omar", "member"), ("Nadia", "member")):
            email = f"{name.lower()}@acme.dev"
            client.cookies.clear()
            await client.post(
                "/api/v1/auth/sign-in", json={"email": "sara@acme.dev", "password": "correct-horse-battery"}
            )
            invite = await client.post(f"{org}/invitations", json={"email": email, "role": role})
            token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
            client.cookies.clear()
            people[email] = (await sign_up(client, name=name, email=email))["user"]["id"]
            assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
        acme = Org(app, client, org, bots, people)
        await acme.sign_in("sara@acme.dev")
        yield acme


def _ids(group: dict[str, Any], kind: str) -> set[str]:
    return {p["id"] for p in group["participants"] if p["type"] == kind}


async def test_the_creator_renames_a_group(acme: Org) -> None:
    await acme.sign_in("omar@acme.dev")
    group = await acme.group(bots=["Chief"], people=["nadia@acme.dev"])
    response = await acme.client.patch(acme.path(group), json={"title": "  Launch week  "})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Launch week"
    assert (await acme.client.get(acme.path(group))).json()["title"] == "Launch week"


async def test_only_the_creator_or_an_owner_or_admin_manages_a_group(acme: Org) -> None:
    await acme.sign_in("omar@acme.dev")
    everyone = ["sara@acme.dev", "lina@acme.dev", "nadia@acme.dev"]
    group = await acme.group(bots=["Chief"], people=everyone)

    await acme.sign_in("nadia@acme.dev")  # a member who didn't make it
    refused = [
        await acme.client.patch(acme.path(group), json={"title": "Mine now"}),
        await acme.add(group, bots=("Scout",)),
        await acme.remove(group, "bot", acme.bots["Chief"]),
    ]
    assert [r.status_code for r in refused] == [403, 403, 403]
    assert refused[0].json()["detail"] == "Only the group's creator, owners and admins can change it."

    for email, title in (("lina@acme.dev", "By an admin"), ("sara@acme.dev", "By the owner")):
        await acme.sign_in(email)
        assert (await acme.client.patch(acme.path(group), json={"title": title})).status_code == 200


async def test_adding_people_and_bots_lets_them_in(acme: Org) -> None:
    group = await acme.group(bots=["Chief"], people=[])
    response = await acme.add(group, bots=("Scout", "Chief"), people=("omar@acme.dev",))
    assert response.status_code == 200, response.text
    assert _ids(response.json(), "bot") == {acme.bots["Chief"], acme.bots["Scout"]}
    assert acme.people["omar@acme.dev"] in _ids(response.json(), "user")

    await acme.sign_in("omar@acme.dev")
    assert (await acme.client.get(acme.path(group))).status_code == 200
    # Joining doesn't make the group's history unread.
    assert (await acme.client.get(acme.path(group))).json()["unread"] == 0


async def test_only_people_and_bots_of_the_organization_can_be_added(acme: Org) -> None:
    group = await acme.group(bots=["Chief"], people=[])
    stranger = "00000000-0000-0000-0000-000000000001"
    response = await acme.client.post(acme.path(group, "/participants"), json={"userIds": [stranger]})
    assert response.status_code == 404
    assert response.json()["detail"] == "Some of those people or bots aren't in this organization."


async def test_a_removed_person_can_no_longer_read_the_group(acme: Org) -> None:
    group = await acme.group(bots=["Chief"], people=["omar@acme.dev"])
    response = await acme.remove(group, "user", acme.people["omar@acme.dev"])
    assert response.status_code == 200, response.text
    assert acme.people["omar@acme.dev"] not in _ids(response.json(), "user")

    await acme.sign_in("omar@acme.dev")
    assert (await acme.client.get(acme.path(group))).status_code == 404
    assert (await acme.client.get(acme.path(group, "/messages"))).status_code == 404
    assert all(t["id"] != group["id"] for t in (await acme.client.get(f"{acme.org}/threads")).json())


async def test_removing_the_lead_bot_clears_the_lead(acme: Org) -> None:
    group = await acme.group(bots=["Chief", "Scout"], people=[])
    assert group["leadBotId"] == acme.bots["Chief"]
    response = await acme.remove(group, "bot", acme.bots["Chief"])
    assert response.status_code == 200, response.text
    assert response.json()["leadBotId"] is None
    assert _ids(response.json(), "bot") == {acme.bots["Scout"]}
    # Removing a bot that isn't in it is a 404.
    assert (await acme.remove(group, "bot", acme.bots["Writer"])).status_code == 404


async def test_the_last_person_cant_be_removed(acme: Org) -> None:
    group = await acme.group(bots=["Chief"], people=[])
    response = await acme.remove(group, "user", acme.people["sara@acme.dev"])
    assert response.status_code == 400
    assert response.json()["detail"] == "A group needs at least one person."


async def test_a_dm_cant_be_renamed_or_changed(acme: Org) -> None:
    dm = (await acme.client.post(f"{acme.org}/threads/dm", json={"botId": acme.bots["Chief"]})).json()
    responses = [
        await acme.client.patch(acme.path(dm), json={"title": "Renamed"}),
        await acme.add(dm, bots=("Scout",)),
        await acme.remove(dm, "bot", acme.bots["Chief"]),
    ]
    assert [r.status_code for r in responses] == [400, 400, 400]
    assert responses[0].json()["detail"] == "Only a group can be changed."


async def test_changes_reach_the_groups_live_stream(acme: Org) -> None:
    group = await acme.group(bots=["Chief"], people=["omar@acme.dev"])
    await acme.client.patch(acme.path(group), json={"title": "Renamed"})
    events = await acme.client.get(acme.path(group, "/events"), params={"after": 0, "follow": "false"})
    assert "event: thread_updated" in events.text
    assert '"title": "Renamed"' in events.text
    assert '"unread"' not in events.text  # a count is per person; the stream is shared


async def test_a_removed_persons_open_stream_stops(acme: Org) -> None:
    """Their browser may still have the group open: it hears the change that removed them (so it
    drops the group), then nothing more, and the stream ends."""
    group = await acme.group(bots=["Chief"], people=["omar@acme.dev"])
    await acme.remove(group, "user", acme.people["omar@acme.dev"])
    await acme.client.patch(acme.path(group), json={"title": "After Omar left"})

    async def follow() -> list[Any]:
        stream = thread_controller.follow_events(
            acme.app.state.runs,
            uuid.UUID(group["id"]),
            user_id=uuid.UUID(acme.people["omar@acme.dev"]),
            after_id=0,
            follow=True,
        )
        return [event async for event in stream]

    events = await asyncio.wait_for(follow(), timeout=5)
    assert [e.event for e in events] == ["thread_updated"]
    assert "After Omar left" not in str(events[0].data)


async def test_removing_a_bot_stops_its_replies_in_the_group(acme: Org) -> None:
    """A bot taken out of a group doesn't post there afterwards: its unfinished runs in that group
    stop. Other bots' runs, and its own work in other chats, carry on."""
    group = await acme.group(bots=["Chief", "Scout"], people=[])
    lead_run = (await acme.client.post(acme.path(group, "/messages"), json={"text": "Morning"})).json()["runIds"]
    scout_run = (await acme.client.post(acme.path(group, "/messages"), json={"text": "@scout hi"})).json()["runIds"]
    dm = (await acme.client.post(f"{acme.org}/threads/dm", json={"botId": acme.bots["Chief"]})).json()
    dm_run = (await acme.client.post(f"{acme.org}/threads/{dm['id']}/messages", json={"text": "Hi"})).json()["runIds"]

    assert (await acme.remove(group, "bot", acme.bots["Chief"])).status_code == 200

    async def status(run_id: str) -> str:
        run: dict[str, str] = (await acme.client.get(f"{acme.org}/runs/{run_id}")).json()
        return run["status"]

    assert [await status(r) for r in [*lead_run, *scout_run, *dm_run]] == ["cancelled", "queued", "queued"]


async def test_a_change_to_a_group_reads_the_group_once(acme: Org) -> None:
    """Saving a change and its live event shows the group once (people, last message, unread), not twice."""
    group = await acme.group(bots=["Chief"], people=[])
    async with sql_statements(acme.app) as seen:
        assert (await acme.client.patch(acme.path(group), json={"title": "Renamed"})).status_code == 200
    previews = [s for s in seen if "row_number()" in s]
    assert len(previews) == 1


async def test_a_deleted_bot_leaves_its_groups(acme: Org) -> None:
    group = await acme.group(bots=["Chief", "Scout"], people=[])
    assert (await acme.client.delete(f"{acme.org}/bots/{acme.bots['Scout']}")).status_code == 204
    assert _ids((await acme.client.get(acme.path(group))).json(), "bot") == {acme.bots["Chief"]}


async def test_someone_removed_from_the_organization_leaves_its_groups_and_their_streams_end(acme: Org) -> None:
    group = await acme.group(bots=["Chief"], people=["omar@acme.dev"])
    await acme.sign_in("omar@acme.dev")
    dm = (await acme.client.post(f"{acme.org}/threads/dm", json={"botId": acme.bots["Chief"]})).json()
    await acme.sign_in("sara@acme.dev")
    omar = acme.people["omar@acme.dev"]
    assert (await acme.client.delete(f"{acme.org}/members/{omar}")).status_code == 204

    assert omar not in _ids((await acme.client.get(acme.path(group))).json(), "user")

    async def follow(thread_id: str) -> list[Any]:
        stream = thread_controller.follow_events(
            acme.app.state.runs, uuid.UUID(thread_id), user_id=uuid.UUID(omar), after_id=0, follow=True
        )
        return [event async for event in stream]

    # A tab Omar left open stops hearing either chat.
    for thread_id in (group["id"], dm["id"]):
        assert await asyncio.wait_for(follow(thread_id), timeout=5) == []


async def test_deleting_a_bot_locks_its_groups_first_as_group_changes_do(acme: Org) -> None:
    """A group change locks the group's row, then changes who's in it. Deleting a bot changes the
    same rows (it leaves its groups; a group it leads loses its lead), so it locks its groups first,
    in id order, or the two could wait for each other (a deadlock on Postgres)."""
    await acme.group(bots=["Scout"], people=[])
    await acme.group(bots=["Chief", "Scout"], people=[])
    async with sql_statements(acme.app) as seen:
        assert (await acme.client.delete(f"{acme.org}/bots/{acme.bots['Scout']}")).status_code == 204
    lock = next(i for i, s in enumerate(seen) if s.startswith("SELECT threads.id FROM threads") and "ORDER BY" in s)
    leave = next(i for i, s in enumerate(seen) if s.startswith("DELETE FROM thread_participants"))
    assert lock < leave

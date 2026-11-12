"""Invitations, roles and leaving: how people come and go in an organization."""

from typing import Any

import httpx

from tests.conftest import sign_up

ORGS = "/api/v1/orgs"


async def _as(client: httpx.AsyncClient, name: str, email: str) -> dict[str, Any]:
    """Sign up someone new and make them the current user of the client."""
    client.cookies.clear()
    return await sign_up(client, name=name, email=email)


async def _invite(client: httpx.AsyncClient, org_id: str, email: str, role: str = "member") -> str:
    response = await client.post(f"{ORGS}/{org_id}/invitations", json={"email": email, "role": role})
    assert response.status_code == 201, response.text
    url: str = response.json()["inviteUrl"]
    return url.rsplit("/", 1)[1]


async def _team(client: httpx.AsyncClient) -> tuple[str, str, str]:
    """Ali owns Acme; Sara joins as a member. Returns (org_id, ali_id, sara_id); Sara is signed in."""
    ali = await _as(client, "Ali", "ali@acme.dev")
    org_id = ali["organizations"][0]["id"]
    token = await _invite(client, org_id, "sara@acme.dev")
    sara = await _as(client, "Sara", "sara@acme.dev")
    accepted = await client.post("/api/v1/invitations/accept", json={"token": token})
    assert accepted.status_code == 200, accepted.text
    return org_id, ali["user"]["id"], sara["user"]["id"]


async def _sign_in(client: httpx.AsyncClient, email: str) -> None:
    client.cookies.clear()
    response = await client.post("/api/v1/auth/sign-in", json={"email": email, "password": "correct-horse-battery"})
    assert response.status_code == 200


async def test_an_invite_link_lets_that_person_join(client: httpx.AsyncClient) -> None:
    org_id, _, _ = await _team(client)
    orgs = (await client.get(ORGS)).json()
    assert {(org["id"], org["role"]) for org in orgs} >= {(org_id, "member")}
    names = [m["name"] for m in (await client.get(f"{ORGS}/{org_id}/members")).json()]
    assert names == ["Ali", "Sara"]


async def test_an_invite_link_works_only_for_its_email_and_only_once(client: httpx.AsyncClient) -> None:
    ali = await _as(client, "Ali", "ali@acme.dev")
    token = await _invite(client, ali["organizations"][0]["id"], "sara@acme.dev")

    await _as(client, "Omar", "omar@acme.dev")
    wrong_person = await client.post("/api/v1/invitations/accept", json={"token": token})
    assert wrong_person.status_code == 403
    assert "sara@acme.dev" in wrong_person.json()["detail"]

    await _as(client, "Sara", "sara@acme.dev")
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 404


async def test_inviting_someone_already_in_is_refused(client: httpx.AsyncClient) -> None:
    ali = await _as(client, "Ali", "ali@acme.dev")
    response = await client.post(f"{ORGS}/{ali['organizations'][0]['id']}/invitations", json={"email": "ALI@acme.dev"})
    assert response.status_code == 409


async def test_pending_invites_can_be_listed_and_revoked(client: httpx.AsyncClient) -> None:
    ali = await _as(client, "Ali", "ali@acme.dev")
    org_id = ali["organizations"][0]["id"]
    await _invite(client, org_id, "sara@acme.dev", role="admin")
    await _invite(client, org_id, "sara@acme.dev", role="admin")  # re-invite replaces the old one

    pending = (await client.get(f"{ORGS}/{org_id}/invitations")).json()
    assert [(i["email"], i["role"]) for i in pending] == [("sara@acme.dev", "admin")]

    assert (await client.delete(f"{ORGS}/{org_id}/invitations/{pending[0]['id']}")).status_code == 204
    assert (await client.get(f"{ORGS}/{org_id}/invitations")).json() == []


async def test_members_cannot_invite_or_change_roles(client: httpx.AsyncClient) -> None:
    org_id, ali_id, _ = await _team(client)  # signed in as Sara, a member
    assert (await client.post(f"{ORGS}/{org_id}/invitations", json={"email": "x@acme.dev"})).status_code == 403
    assert (await client.patch(f"{ORGS}/{org_id}/members/{ali_id}", json={"role": "member"})).status_code == 403


async def test_the_owner_can_promote_and_only_owners_touch_owners(client: httpx.AsyncClient) -> None:
    org_id, ali_id, sara_id = await _team(client)
    await _sign_in(client, "ali@acme.dev")

    promoted = await client.patch(f"{ORGS}/{org_id}/members/{sara_id}", json={"role": "admin"})
    assert promoted.json()["role"] == "admin"

    await _sign_in(client, "sara@acme.dev")  # an admin now, but not an owner
    response = await client.patch(f"{ORGS}/{org_id}/members/{ali_id}", json={"role": "member"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Only owners can change who is an owner."


async def test_there_is_always_an_owner(client: httpx.AsyncClient) -> None:
    org_id, ali_id, _ = await _team(client)
    await _sign_in(client, "ali@acme.dev")

    demote = await client.patch(f"{ORGS}/{org_id}/members/{ali_id}", json={"role": "admin"})
    leave = await client.delete(f"{ORGS}/{org_id}/members/{ali_id}")
    for response in (demote, leave):
        assert response.status_code == 409
        assert "at least one owner" in response.json()["detail"]


async def test_members_can_leave_and_admins_can_remove(client: httpx.AsyncClient) -> None:
    org_id, _, sara_id = await _team(client)
    assert (await client.delete(f"{ORGS}/{org_id}/members/{sara_id}")).status_code == 204  # Sara leaves
    assert (await client.get(f"{ORGS}/{org_id}")).status_code == 404  # and can't see it any more

    await _sign_in(client, "ali@acme.dev")
    names = [m["name"] for m in (await client.get(f"{ORGS}/{org_id}/members")).json()]
    assert names == ["Ali"]

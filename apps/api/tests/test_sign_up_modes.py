"""SIGNUP_MODE: open (anyone), invite-only (with an invite link for that email) or closed (nobody new)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import update

from src.core.database import utcnow
from src.models import Invitation
from tests.conftest import PASSWORD, TEST_SETTINGS, FakeProviders, api_client, sign_up

AUTH = "/api/v1/auth"
BY_INVITATION = "Sign-up is by invitation. Ask your admin for an invite link."
CLOSED = "New accounts are turned off on this server. Ask your admin if you need one."


@asynccontextmanager
async def server(mode: str) -> AsyncIterator[tuple[Any, httpx.AsyncClient]]:
    """A fresh app with SIGNUP_MODE=mode (tests switch it on `app.state.settings` as they go)."""
    settings = TEST_SETTINGS.model_copy(update={"signup_mode": mode})
    async with api_client(settings, FakeProviders()) as (app, http):
        yield app, http


async def _owner_with_invite(app: Any, http: httpx.AsyncClient, email: str = "sara@acme.dev") -> tuple[str, str]:
    """Ali signs up while sign-up is open (the first owner, as the self-hosting guide says), invites
    `email` as an admin, signs out, and the server switches to invite-only. Returns (org_id, token)."""
    app.state.settings = app.state.settings.model_copy(update={"signup_mode": "open"})
    ali = await sign_up(http, "Ali", "ali@acme.dev")
    org_id: str = ali["organizations"][0]["id"]
    invite = await http.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": email, "role": "admin"})
    assert invite.status_code == 201, invite.text
    token: str = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    http.cookies.clear()
    app.state.settings = app.state.settings.model_copy(update={"signup_mode": "invite-only"})
    return org_id, token


def _new(email: str = "sara@acme.dev", invite_token: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"name": "Sara", "email": email, "password": PASSWORD}
    if invite_token is not None:
        body["inviteToken"] = invite_token
    return body


async def test_the_web_can_ask_which_mode_is_on() -> None:
    for mode in ("open", "invite-only", "closed"):
        async with server(mode) as (_, http):
            assert (await http.get(f"{AUTH}/options")).json() == {"signUpMode": mode}


async def test_open_sign_up_creates_your_own_organization(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    assert [(org["name"], org["role"]) for org in me["organizations"]] == [("Ali's team", "owner")]


async def test_open_sign_up_with_an_invite_joins_that_organization_instead(client: httpx.AsyncClient) -> None:
    ali = await sign_up(client, "Ali", "ali@acme.dev")
    org_id = ali["organizations"][0]["id"]
    invite = await client.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": "sara@acme.dev"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()

    response = await client.post(f"{AUTH}/sign-up", json=_new(invite_token=token))
    assert response.status_code == 201, response.text
    assert [(org["id"], org["role"]) for org in response.json()["organizations"]] == [(org_id, "member")]


async def test_invite_only_refuses_sign_up_without_an_invite() -> None:
    async with server("invite-only") as (_, http):
        response = await http.post(f"{AUTH}/sign-up", json=_new())
        assert (response.status_code, response.json()["detail"]) == (403, BY_INVITATION)


async def test_invite_only_signs_you_up_into_the_inviting_organization() -> None:
    async with server("invite-only") as (app, http):
        org_id, token = await _owner_with_invite(app, http)

        response = await http.post(f"{AUTH}/sign-up", json=_new(invite_token=token))
        assert response.status_code == 201, response.text
        assert [(org["id"], org["role"]) for org in response.json()["organizations"]] == [(org_id, "admin")]
        # Signed in, and the invite is used up.
        assert (await http.get(f"{AUTH}/me")).status_code == 200
        assert (await http.post("/api/v1/invitations/accept", json={"token": token})).status_code == 404


async def test_invite_only_refuses_an_invite_for_someone_else() -> None:
    async with server("invite-only") as (app, http):
        _, token = await _owner_with_invite(app, http)
        response = await http.post(f"{AUTH}/sign-up", json=_new(email="omar@acme.dev", invite_token=token))
        assert response.status_code == 403
        assert "sara@acme.dev" in response.json()["detail"]


async def test_invite_only_refuses_a_used_expired_or_made_up_invite() -> None:
    async with server("invite-only") as (app, http):
        _, token = await _owner_with_invite(app, http)
        assert (await http.post(f"{AUTH}/sign-up", json=_new(invite_token=token))).status_code == 201
        http.cookies.clear()

        # Used: Sara has her account; a second sign-up with her link is refused for the link, not the email.
        used = await http.post(f"{AUTH}/sign-up", json=_new(email="SARA@acme.dev", invite_token=token))
        assert used.status_code == 403

        made_up = await http.post(f"{AUTH}/sign-up", json=_new(email="omar@acme.dev", invite_token="nope"))
        assert (made_up.status_code, made_up.json()["detail"]) == (
            403,
            "This invite link isn't valid any more. Ask for a new one.",
        )


async def test_invite_only_refuses_an_expired_invite() -> None:
    async with server("invite-only") as (app, http):
        _, token = await _owner_with_invite(app, http)
        async with app.state.sessionmaker() as db:
            await db.execute(update(Invitation).values(expires_at=utcnow() - timedelta(minutes=1)))
            await db.commit()
        response = await http.post(f"{AUTH}/sign-up", json=_new(invite_token=token))
        assert response.status_code == 403


async def test_closed_refuses_every_sign_up_but_people_still_sign_in() -> None:
    async with server("closed") as (app, http):
        _, token = await _owner_with_invite(app, http)
        app.state.settings = app.state.settings.model_copy(update={"signup_mode": "closed"})

        for body in (_new(), _new(invite_token=token)):
            response = await http.post(f"{AUTH}/sign-up", json=body)
            assert (response.status_code, response.json()["detail"]) == (403, CLOSED)

        signed_in = await http.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": PASSWORD})
        assert signed_in.status_code == 200

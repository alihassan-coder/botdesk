"""Password reset: ask for a link by email, then use it once to set a new password."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.core.database import utcnow
from src.services import auth_service
from tests.conftest import PASSWORD, FakeEmailSender, sign_up

AUTH = "/api/v1/auth"
NEW_PASSWORD = "a-brand-new-password"


async def _request_reset(client: httpx.AsyncClient, outbox: FakeEmailSender, email: str = "ali@acme.dev") -> str:
    """Ask for a reset link and return the token from the emailed link."""
    response = await client.post(f"{AUTH}/forgot-password", json={"email": email})
    assert response.status_code == 202
    link = outbox.sent[-1].link
    assert link is not None
    return parse_qs(urlparse(link).query)["token"][0]


async def test_forgot_password_answers_the_same_but_emails_only_real_accounts(
    client: httpx.AsyncClient, outbox: FakeEmailSender
) -> None:
    await sign_up(client, name="Ali Hassan", email="ali@acme.dev")
    known = await client.post(f"{AUTH}/forgot-password", json={"email": "ALI@acme.dev"})
    unknown = await client.post(f"{AUTH}/forgot-password", json={"email": "nobody@acme.dev"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [(email.to_email, email.to_name) for email in outbox.sent] == [("ali@acme.dev", "Ali Hassan")]
    reset = outbox.sent[0]
    assert reset.subject == "Reset your BotDesk password"
    assert reset.link is not None and reset.link.startswith("http://localhost:3000/reset-password?token=")
    assert reset.link in reset.text


async def test_a_reset_link_sets_the_password_and_signs_out_everywhere(
    client: httpx.AsyncClient, outbox: FakeEmailSender
) -> None:
    await sign_up(client, email="ali@acme.dev")  # signed in: the cookie is a live session
    token = await _request_reset(client, outbox)

    response = await client.post(f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert response.status_code == 200, response.text

    assert (await client.get(f"{AUTH}/me")).status_code == 401  # the old session is gone
    old = await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": NEW_PASSWORD})
    assert new.status_code == 200


async def test_a_reset_link_works_only_once(client: httpx.AsyncClient, outbox: FakeEmailSender) -> None:
    await sign_up(client, email="ali@acme.dev")
    token = await _request_reset(client, outbox)
    first = await client.post(f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert first.status_code == 200

    again = await client.post(f"{AUTH}/reset-password", json={"token": token, "password": "yet-another-password"})
    assert again.status_code == 400
    assert again.json()["detail"] == auth_service.RESET_LINK_INVALID


async def test_asking_again_cancels_the_older_link(client: httpx.AsyncClient, outbox: FakeEmailSender) -> None:
    await sign_up(client, email="ali@acme.dev")
    older = await _request_reset(client, outbox)
    newer = await _request_reset(client, outbox)

    stale = await client.post(f"{AUTH}/reset-password", json={"token": older, "password": NEW_PASSWORD})
    assert stale.status_code == 400
    fresh = await client.post(f"{AUTH}/reset-password", json={"token": newer, "password": NEW_PASSWORD})
    assert fresh.status_code == 200


async def test_an_expired_reset_link_is_refused(
    client: httpx.AsyncClient, outbox: FakeEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sign_up(client, email="ali@acme.dev")
    token = await _request_reset(client, outbox)

    later = utcnow() + timedelta(minutes=61)  # links last PASSWORD_RESET_MINUTES (60)
    monkeypatch.setattr(auth_service, "utcnow", lambda: later)
    response = await client.post(f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json()["detail"] == auth_service.RESET_LINK_INVALID


async def test_a_made_up_reset_token_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{AUTH}/reset-password", json={"token": "made-up", "password": NEW_PASSWORD})
    assert response.status_code == 400


async def test_a_weak_new_password_is_refused_and_keeps_the_link(
    client: httpx.AsyncClient, outbox: FakeEmailSender
) -> None:
    await sign_up(client, email="ali@acme.dev")
    token = await _request_reset(client, outbox)

    weak = await client.post(f"{AUTH}/reset-password", json={"token": token, "password": "short"})
    assert weak.status_code == 422
    retry = await client.post(f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert retry.status_code == 200

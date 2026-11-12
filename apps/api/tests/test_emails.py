"""Emails: the templates, the Brevo sender, and invitations being emailed. No real network here."""

import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from src.emails import invitation_email, password_reset_email
from src.services import email_service
from src.services.email_service import BREVO_URL, BrevoEmailSender, EmailMessage
from tests.conftest import FakeEmailSender, sign_up


async def test_an_invitation_is_emailed_to_the_invitee(client: httpx.AsyncClient, outbox: FakeEmailSender) -> None:
    ali = await sign_up(client, name="Ali Hassan", email="ali@acme.dev")
    org_id = ali["organizations"][0]["id"]
    response = await client.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": "Sara@acme.dev"})
    assert response.status_code == 201
    invite_url = response.json()["inviteUrl"]  # still returned, as before

    [email] = outbox.sent
    assert email.to_email == "sara@acme.dev"
    assert email.link == invite_url
    assert email.subject == "Ali Hassan invited you to Ali's team on BotDesk"
    assert invite_url in email.html and invite_url in email.text
    assert "Ali&#x27;s team" in email.html  # names are escaped in HTML


def test_templates_escape_names_and_keep_subjects_on_one_line() -> None:
    subject, html, text = invitation_email(
        inviter_name="<script>alert(1)</script>", org_name="Evil\nBcc: x@y.z", url="https://app.test/invite/abc"
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "\n" not in subject
    assert "https://app.test/invite/abc" in text

    subject, html, text = password_reset_email(url="https://app.test/reset-password?token=a&b", minutes=60)
    assert subject == "Reset your BotDesk password"
    assert "token=a&amp;b" in html
    assert "If you didn't ask for this, ignore this email." in text
    assert "botdesk" in html and "#3B30FF" in html


async def test_the_brevo_sender_posts_the_right_request() -> None:
    seen: list[httpx.Request] = []

    def brevo(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"messageId": "<abc@smtp-relay.mailin.fr>"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(brevo)) as http:
        sender = BrevoEmailSender(
            http, api_key=SecretStr("test-key"), from_address="team@botdesk.dev", from_name="BotDesk"
        )
        await sender.send(
            EmailMessage(to_email="ali@acme.dev", to_name="Ali", subject="Hi", html="<p>Hi</p>", text="Hi")
        )

    [request] = seen
    assert str(request.url) == BREVO_URL
    assert request.method == "POST"
    assert request.headers["api-key"] == "test-key"
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "sender": {"name": "BotDesk", "email": "team@botdesk.dev"},
        "to": [{"email": "ali@acme.dev", "name": "Ali"}],
        "subject": "Hi",
        "htmlContent": "<p>Hi</p>",
        "textContent": "Hi",
    }


async def test_a_failed_send_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    def brevo_down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(brevo_down)) as http:
        sender = BrevoEmailSender(http, api_key=SecretStr("secret-key"), from_address="a@b.c", from_name="BotDesk")
        with caplog.at_level(logging.ERROR):
            await email_service.send_quietly(
                sender, EmailMessage(to_email="ali@acme.dev", subject="Hi", html="<p>Hi</p>", text="Hi")
            )

    assert "Couldn't send email" in caplog.text
    assert "secret-key" not in caplog.text

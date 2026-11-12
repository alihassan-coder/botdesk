"""Sending email. One small interface, `EmailSender.send(EmailMessage)`, with two senders:

- `BrevoEmailSender`: Brevo's transactional API, when `BREVO_API_KEY` is set.
- `ConsoleEmailSender`: logs the subject, recipient and link (dev without a key). Tests use a fake.

Controllers hand emails to FastAPI's `BackgroundTasks` through `send_quietly`, so a request never
waits on the provider, and a failed send is logged, never shown to the user.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import SecretStr

from src.core.config import Settings
from src.emails import Email

log = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    subject: str
    html: str
    text: str
    to_name: str | None = None
    link: str | None = None  # the email's one action link, for logs in dev

    @classmethod
    def build(
        cls, email: Email, *, to_email: str, to_name: str | None = None, link: str | None = None
    ) -> "EmailMessage":
        subject, html, text = email
        return cls(to_email=to_email, to_name=to_name, subject=subject, html=html, text=text, link=link)


class EmailError(Exception):
    """The provider refused or couldn't be reached."""


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """No provider: write the email to the log. Links carry tokens, so they're shown only outside production."""

    def __init__(self, *, show_links: bool) -> None:
        self.show_links = show_links

    async def send(self, message: EmailMessage) -> None:
        if self.show_links:
            log.warning(
                "Email not sent (no BREVO_API_KEY): %r to %s, link: %s", message.subject, message.to_email, message.link
            )
        else:
            log.warning("Email not sent (no BREVO_API_KEY): %r to %s", message.subject, message.to_email)


class BrevoEmailSender:
    def __init__(self, http: httpx.AsyncClient, *, api_key: SecretStr, from_address: str, from_name: str) -> None:
        self.http = http
        self.api_key = api_key
        self.from_address = from_address
        self.from_name = from_name

    def payload(self, message: EmailMessage) -> dict[str, object]:
        recipient: dict[str, str] = {"email": message.to_email}
        if message.to_name:
            recipient["name"] = message.to_name
        return {
            "sender": {"name": self.from_name, "email": self.from_address},
            "to": [recipient],
            "subject": message.subject,
            "htmlContent": message.html,
            "textContent": message.text,
        }

    async def send(self, message: EmailMessage) -> None:
        try:
            response = await self.http.post(
                BREVO_URL,
                headers={
                    "api-key": self.api_key.get_secret_value(),
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json=self.payload(message),
            )
        except httpx.HTTPError as error:
            raise EmailError(f"Brevo couldn't be reached: {type(error).__name__}") from error
        if response.status_code >= 400:
            raise EmailError(f"Brevo refused the email ({response.status_code}): {response.text[:300]}")
        message_id = response.json().get("messageId")
        log.info("Email sent via Brevo: %r to %s, messageId %s", message.subject, message.to_email, message_id)


def build_email_sender(settings: Settings, http: httpx.AsyncClient) -> EmailSender:
    if settings.sends_real_email and settings.brevo_api_key is not None:
        return BrevoEmailSender(
            http,
            api_key=settings.brevo_api_key,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
        )
    return ConsoleEmailSender(show_links=not settings.is_production)


async def send_quietly(sender: EmailSender, message: EmailMessage) -> None:
    """For background tasks: send, and log (never raise) a failure. The request has already answered."""
    try:
        await sender.send(message)
    except Exception:
        log.exception("Couldn't send email %r to %s", message.subject, message.to_email)

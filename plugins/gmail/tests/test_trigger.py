"""The `new_email` trigger's poll (slice 6.3, ADR 0011 §5) against Gmail API fixtures.

BotDesk calls the poll every minute with the cursor it saved last time (a Gmail `historyId`).
The first poll only remembers where the mailbox is now; later polls report new inbox mail, at
most 10 at a time, and say so when mail was missed or left out.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from botdesk_plugin_sdk import ConnectionInfo, TriggerPollResult, TriggerSpec, validate_manifest
from botdesk_plugin_sdk.testing import FakeHttp, make_context

from botdesk_gmail import GMAIL_API, GmailError, gmail_plugin

FIXTURES = Path(__file__).parent / "fixtures"
USERS_ME = f"{GMAIL_API}/gmail/v1/users/me"
HISTORY = f"{USERS_ME}/history"
PROFILE = f"{USERS_ME}/profile"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def trigger() -> TriggerSpec:
    (spec,) = gmail_plugin().triggers
    return spec


async def poll(http: FakeHttp, cursor: str | None) -> TriggerPollResult:
    connection = ConnectionInfo(
        id=uuid.uuid4(), connector_id="gmail", account_label="Ali@acme.dev", owner_kind="member", scopes=()
    )
    return await trigger().poll(make_context(http=http, connection=connection), cursor)


def mailbox() -> FakeHttp:
    http = FakeHttp(gmail_plugin())
    http.route("GET", PROFILE, json={"emailAddress": "ali@acme.dev", "historyId": "48400"})
    return http


def test_new_email_is_declared_polled_every_minute_with_untrusted_events() -> None:
    validate_manifest(gmail_plugin())
    spec = trigger()
    assert spec.name == "new_email"
    assert spec.interval_seconds == 60
    assert spec.untrusted_payload


async def test_the_first_poll_remembers_where_the_mailbox_is_and_reports_nothing() -> None:
    http = mailbox()
    result = await poll(http, None)
    assert result == TriggerPollResult(events=(), cursor="48400")
    assert [request.url for request in http.requests] == [PROFILE]  # no backfill of old mail


async def test_new_inbox_mail_is_one_event_each_skipping_own_promotions_drafts_and_repeats() -> None:
    http = mailbox()
    http.route("GET", HISTORY, json=fixture("history_new_mail"))
    http.route("GET", f"{USERS_ME}/messages/18f1a1", json=fixture("message_18f1a1_metadata"))

    result = await poll(http, "48300")

    history = http.requests[0]
    assert history.params == {
        "startHistoryId": "48300",
        "historyTypes": "messageAdded",
        "labelId": "INBOX",
        "maxResults": 500,
    }
    (event,) = result.events
    assert event.external_id == "18f1a1"
    assert event.summary == "New email from Sara Lee: Invoice 4471"
    assert event.payload == {
        "messageId": "18f1a1",
        "threadId": "18f1a0",
        "from": "Sara Lee <sara@acme.dev>",
        "subject": "Invoice 4471",
        "account": "Ali@acme.dev",
    }
    assert result.cursor == "48310"  # where the next poll starts
    assert result.notice is None
    # Own sent mail, promotions and drafts were never fetched.
    assert [r.url for r in http.requests[1:]] == [f"{USERS_ME}/messages/18f1a1"]


async def test_mail_from_the_mailbox_itself_starts_nothing() -> None:
    http = mailbox()
    http.route("GET", HISTORY, json=fixture("history_new_mail"))
    own = fixture("message_18f1a1_metadata")
    own["payload"]["headers"][0]["value"] = "Ali <ALI@acme.dev>"
    http.route("GET", f"{USERS_ME}/messages/18f1a1", json=own)
    assert (await poll(http, "48300")).events == ()


async def test_no_new_mail_moves_the_cursor_and_reports_nothing() -> None:
    http = mailbox()
    http.route("GET", HISTORY, json={"historyId": "48301"})
    assert await poll(http, "48300") == TriggerPollResult(events=(), cursor="48301")


async def test_an_expired_cursor_starts_again_from_now_with_one_notice_and_no_events() -> None:
    http = mailbox()
    http.route("GET", HISTORY, status=404, json={"error": {"code": 404}})
    result = await poll(http, "100")
    assert result.events == ()
    assert result.cursor == "48400"
    assert result.notice is not None and "missed" in result.notice


async def test_at_most_10_emails_per_poll_and_a_notice_about_the_rest() -> None:
    http = mailbox()
    added = [
        {"id": str(n), "messagesAdded": [{"message": {"id": f"m{n}", "threadId": f"t{n}", "labelIds": ["INBOX"]}}]}
        for n in range(13)
    ]
    http.route("GET", HISTORY, json={"history": added, "historyId": "48420"})
    for n in range(13):
        message = fixture("message_18f1a1_metadata") | {"id": f"m{n}", "threadId": f"t{n}"}
        http.route("GET", f"{USERS_ME}/messages/m{n}", json=message)

    result = await poll(http, "48300")

    assert [event.external_id for event in result.events] == [f"m{n}" for n in range(10)]
    assert result.notice == "3 more new emails arrived at once. Your bot reacts to at most 10 a minute."
    assert len(http.requests) == 1 + 10  # the rest weren't fetched


async def test_a_message_deleted_before_it_was_read_is_skipped() -> None:
    http = mailbox()
    http.route("GET", HISTORY, json=fixture("history_new_mail"))
    http.route("GET", f"{USERS_ME}/messages/18f1a1", status=404, json={})
    assert (await poll(http, "48300")).events == ()


async def test_an_odd_message_id_never_goes_into_a_url() -> None:
    http = mailbox()
    odd = [{"id": "1", "messagesAdded": [{"message": {"id": "../labels", "labelIds": ["INBOX"]}}]}]
    http.route("GET", HISTORY, json={"history": odd, "historyId": "48301"})
    assert (await poll(http, "48300")).events == ()
    assert len(http.requests) == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_other_failures_are_readable_errors_and_keep_the_cursor(status: int) -> None:
    http = mailbox()
    http.route("GET", HISTORY, status=status, json={})
    with pytest.raises(GmailError):
        await poll(http, "48300")

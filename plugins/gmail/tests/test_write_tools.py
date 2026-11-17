"""The write tools (slice 6.2, ADR 0011 §3) against Gmail API fixtures through `FakeHttp`.

Labels, archive, drafts, send and trash: each needs `gmail.modify`, makes exactly one change in
Gmail per call, and declares its risk so the app's policy asks a person when it should (the
policy itself is tested through the pipeline in `apps/api/tests/test_gmail_tools.py`).
"""

import base64
import email
import email.policy
import json
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest
from botdesk_plugin_sdk import ConnectionInfo, ToolResult, validate_manifest
from botdesk_plugin_sdk.manifest import manifest_json
from botdesk_plugin_sdk.testing import FakeHttp, call_tool, make_context
from pydantic import ValidationError

from botdesk_gmail import GMAIL_API, MODIFY_SCOPE, GmailError, gmail_plugin
from botdesk_gmail.markdown import markdown_to_html

FIXTURES = Path(__file__).parent / "fixtures"
USERS_ME = f"{GMAIL_API}/gmail/v1/users/me"
THREAD = f"{USERS_ME}/threads/18f0a0"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def gmail() -> FakeHttp:
    return FakeHttp(gmail_plugin())


async def run(http: FakeHttp, tool: str, args: dict[str, Any]) -> ToolResult:
    connection = ConnectionInfo(
        id=uuid.uuid4(), connector_id="gmail", account_label="ali@acme.dev", owner_kind="member", scopes=(MODIFY_SCOPE,)
    )
    return await call_tool(gmail_plugin(), tool, args, make_context(http=http, connection=connection))


def summary(tool: str, args: dict[str, Any]) -> str:
    spec = next(t for t in gmail_plugin().tools if t.name == tool)
    return spec.summary(spec.args_model.model_validate(args))


def sent_mail(raw: str) -> EmailMessage:
    """The RFC 2822 message a tool sent, decoded from Gmail's base64url `raw`."""
    message = email.message_from_bytes(base64.urlsafe_b64decode(raw), policy=email.policy.default)
    assert isinstance(message, EmailMessage)
    return message


MAIL = {"to": ["sara@acme.dev"], "subject": "Launch review", "body": "Hi Sara,\n\nThursday at 3 PM works.\n\nAli"}


# The manifest


def test_the_write_tools_need_gmail_modify_and_declare_their_risk() -> None:
    tools = {tool.name: tool for tool in validate_manifest(gmail_plugin()).tools}
    risks = {name: tool.risk for name, tool in tools.items() if tool.risk != "read"}
    assert risks == {
        "add_labels": "write-external",
        "remove_labels": "write-external",
        "archive": "write-external",
        "create_draft": "write-external",
        "send": "external-send",
        "trash": "destructive",
        "send_draft": "external-send",
    }
    for name in risks:
        assert tools[name].scopes == (MODIFY_SCOPE,)
        assert not tools[name].untrusted_output
    # Changing labels again changes nothing more; a second draft or send is a second email.
    assert tools["add_labels"].idempotent and tools["archive"].idempotent and tools["trash"].idempotent
    assert not tools["send"].idempotent and not tools["create_draft"].idempotent and not tools["send_draft"].idempotent


def test_the_generated_manifest_json_is_up_to_date() -> None:
    saved = (Path(__file__).parents[1] / "manifest.json").read_text(encoding="utf-8")
    assert saved == manifest_json(gmail_plugin())


# Labels and archive


async def test_add_labels_adds_them_to_the_whole_thread() -> None:
    http = gmail()
    http.route("POST", f"{THREAD}/modify", json=fixture("thread_modified"))

    result = await run(http, "add_labels", {"thread_id": "18f0a0", "label_ids": ["Label_7", "STARRED"]})

    (request,) = http.requests
    assert request.json == {"addLabelIds": ["Label_7", "STARRED"]}
    assert result == {"account": "ali@acme.dev", "threadId": "18f0a0", "added": ["Label_7", "STARRED"]}


async def test_remove_labels_marks_read_by_removing_unread() -> None:
    http = gmail()
    http.route("POST", f"{THREAD}/modify", json=fixture("thread_modified"))
    result = await run(http, "remove_labels", {"thread_id": "18f0a0", "label_ids": ["UNREAD"]})
    assert http.requests[0].json == {"removeLabelIds": ["UNREAD"]}
    assert result["removed"] == ["UNREAD"]


@pytest.mark.parametrize("label", ["TRASH", "SPAM", "trash", "DRAFT", "SENT", "../x", ""])
async def test_trash_spam_and_system_only_labels_are_not_labels_a_bot_changes(label: str) -> None:
    # Trashing goes through gmail.trash (destructive), never a label change.
    for tool in ("add_labels", "remove_labels"):
        with pytest.raises(ValidationError):
            await run(gmail(), tool, {"thread_id": "18f0a0", "label_ids": [label]})


async def test_archive_removes_the_thread_from_the_inbox() -> None:
    http = gmail()
    http.route("POST", f"{THREAD}/modify", json=fixture("thread_modified"))
    result = await run(http, "archive", {"thread_id": "18f0a0"})
    assert http.requests[0].json == {"removeLabelIds": ["INBOX"]}
    assert result == {"account": "ali@acme.dev", "threadId": "18f0a0", "archived": True}


def test_label_and_archive_summaries_name_the_thread_and_labels() -> None:
    assert summary("add_labels", {"thread_id": "18f0a0", "label_ids": ["STARRED"]}) == (
        "Add label STARRED to email thread 18f0a0"
    )
    assert summary("remove_labels", {"thread_id": "18f0a0", "label_ids": ["UNREAD", "INBOX"]}) == (
        "Remove labels UNREAD, INBOX from email thread 18f0a0"
    )
    assert summary("archive", {"thread_id": "18f0a0"}) == "Archive email thread 18f0a0"
    assert summary("trash", {"thread_id": "18f0a0"}) == "Move email thread 18f0a0 to Trash"


# Trash


async def test_trash_moves_the_thread_to_trash() -> None:
    http = gmail()
    http.route("POST", f"{THREAD}/trash", json={"id": "18f0a0"})
    result = await run(http, "trash", {"thread_id": "18f0a0"})
    (request,) = http.requests
    assert (request.method, request.url) == ("POST", f"{THREAD}/trash")
    assert result == {"account": "ali@acme.dev", "threadId": "18f0a0", "trashed": True}


# Send


async def test_send_sends_one_plain_text_email_built_from_the_arguments() -> None:
    http = gmail()
    http.route("POST", f"{USERS_ME}/messages/send", json=fixture("message_sent"))

    result = await run(http, "send", {**MAIL, "cc": ["omar@acme.dev"], "bcc": ["boss@acme.dev"]})

    (request,) = http.requests  # one request: no retry loop that could send twice
    assert set(request.json) == {"raw"}
    mail = sent_mail(request.json["raw"])
    assert mail["To"] == "sara@acme.dev"
    assert mail["Cc"] == "omar@acme.dev"
    assert mail["Bcc"] == "boss@acme.dev"  # Gmail delivers to Bcc and drops the header
    assert mail["Subject"] == "Launch review"
    assert mail["From"] is None  # Gmail sets the connected account
    assert mail.get_content_type() == "text/plain"
    assert mail.get_content() == "Hi Sara,\r\n\r\nThursday at 3 PM works.\r\n\r\nAli\r\n"  # RFC 2822 line ends
    assert result == {"account": "ali@acme.dev", "sent": True, "id": "18f0c1", "threadId": "18f0a0"}


MARKDOWN = (
    "# Launch plan\n\n"
    "Hi **Sara**, the review is *Thursday* at `3 PM`.\n"
    "Agenda:\n\n"
    "- Demo\n"
    "- [Checklist](https://acme.dev/launch?a=1&b=2)\n\n"
    "1. Ship\n"
    "2. Celebrate\n\n"
    "<script>alert(1)</script> <b onclick=x>raw</b> [bad](javascript:alert(1))"
)


async def test_a_markdown_body_is_sent_as_plain_text_and_html_we_generate() -> None:
    http = gmail()
    http.route("POST", f"{USERS_ME}/messages/send", json=fixture("message_sent"))

    await run(http, "send", {**MAIL, "body": MARKDOWN, "format": "markdown"})

    mail = sent_mail(http.requests[0].json["raw"])
    assert mail.get_content_type() == "multipart/alternative"
    plain, rich = mail.iter_parts()
    assert plain.get_content_type() == "text/plain"
    assert plain.get_content().replace("\r\n", "\n").strip() == MARKDOWN  # readable as it was written
    assert rich.get_content_type() == "text/html"
    html = rich.get_content()
    assert "<h1>Launch plan</h1>" in html
    assert "Hi <strong>Sara</strong>, the review is <em>Thursday</em> at <code>3 PM</code>.<br>" in html
    assert '<ul><li>Demo</li><li><a href="https://acme.dev/launch?a=1&amp;b=2">Checklist</a></li></ul>' in html
    assert "<ol><li>Ship</li><li>Celebrate</li></ol>" in html
    # The model's own markup is text, never HTML; only http(s) and mailto links become links.
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &lt;b onclick=x&gt;raw&lt;/b&gt;" in html
    assert "<script" not in html and "javascript:" not in html.split("[bad]")[0] and 'href="javascript' not in html


def test_markdown_links_keep_underscores_and_stars_in_their_address() -> None:
    html = markdown_to_html("[docs](https://x.example/_a_/b**c**) and *after*")
    assert '<a href="https://x.example/_a_/b**c**">docs</a> and <em>after</em>' in html


async def test_plain_is_the_default_and_a_markdown_draft_is_multipart_too() -> None:
    http = gmail()
    http.route("POST", f"{USERS_ME}/drafts", json=fixture("draft_created"))
    await run(http, "create_draft", {**MAIL, "format": "markdown"})
    assert sent_mail(http.requests[0].json["message"]["raw"]).get_content_type() == "multipart/alternative"
    with pytest.raises(ValidationError):
        await run(gmail(), "send", {**MAIL, "format": "html"})  # no raw HTML from the model


async def test_a_reply_goes_into_the_thread_with_in_reply_to_and_references() -> None:
    http = gmail()
    http.route("GET", THREAD, json=fixture("thread_reply_metadata"))
    http.route("POST", f"{USERS_ME}/messages/send", json=fixture("message_sent"))

    await run(http, "send", {**MAIL, "subject": "Re: Launch checklist", "reply_to_thread_id": "18f0a0"})

    lookup, send = http.requests
    assert lookup.params == {"format": "metadata"}
    assert send.json["threadId"] == "18f0a0"
    mail = sent_mail(send.json["raw"])
    # The newest message in the thread is the one answered.
    assert mail["In-Reply-To"] == "<CAF2@mail.acme.dev>"
    assert mail["References"] == "<CAF1@mail.acme.dev> <CAF2@mail.acme.dev>"


async def test_a_non_ascii_subject_and_body_are_encoded_properly() -> None:
    http = gmail()
    http.route("POST", f"{USERS_ME}/messages/send", json=fixture("message_sent"))
    await run(http, "send", {**MAIL, "subject": "Café 🎉", "body": "Grüße"})
    mail = sent_mail(http.requests[0].json["raw"])
    assert mail["Subject"] == "Café 🎉"
    assert mail.get_content().strip() == "Grüße"


@pytest.mark.parametrize(
    "change",
    [
        {"to": ["sara@acme.dev\r\nBcc: spy@evil.example"]},
        {"to": ["sara@acme.dev, spy@evil.example"]},
        {"to": ["Sara <sara@acme.dev>"]},
        {"to": ["not-an-address"]},
        {"cc": ["omar@acme.dev\nX-Evil: 1"]},
        {"bcc": ["spy@evil.example\r"]},
        {"subject": "Hi\r\nBcc: spy@evil.example"},
        {"subject": "Hi\nthere"},
        {"subject": "Hi\x00"},
        {"to": []},
        {"to": [f"p{n}@acme.dev" for n in range(21)]},
        {"body": "x" * 50_001},
        {"reply_to_thread_id": "../labels"},
    ],
)
async def test_header_injection_and_bad_recipients_are_refused_before_anything_is_sent(change: dict[str, Any]) -> None:
    http = gmail()
    for tool in ("send", "create_draft"):
        with pytest.raises(ValidationError):
            await run(http, tool, {**MAIL, **change})
    assert http.requests == []


async def test_at_most_20_recipients_in_all() -> None:
    many = {"to": [f"p{n}@acme.dev" for n in range(10)], "cc": [f"c{n}@acme.dev" for n in range(11)]}
    with pytest.raises(ValidationError, match="20"):
        await run(gmail(), "send", {**MAIL, **many})


def test_the_send_summary_shows_every_recipient_the_subject_and_the_start_of_the_body() -> None:
    text = summary("send", {**MAIL, "cc": ["omar@acme.dev"], "bcc": ["boss@acme.dev"]})
    assert text == (
        "Send an email to sara@acme.dev (cc omar@acme.dev; bcc boss@acme.dev): “Launch review”: "
        "Hi Sara, Thursday at 3 PM works. Ali"
    )
    long = summary("send", {**MAIL, "body": "word " * 100, "reply_to_thread_id": "18f0a0"})
    assert long.startswith("Reply in email thread 18f0a0 to sara@acme.dev: “Launch review”: word word")
    assert long.endswith("…") and len(long) < 260


async def test_a_failed_send_is_a_readable_error() -> None:
    http = gmail()
    http.route("POST", f"{USERS_ME}/messages/send", status=403, json={"error": {"message": "secret detail"}})
    with pytest.raises(GmailError, match="refused") as caught:
        await run(http, "send", MAIL)
    assert "secret detail" not in str(caught.value)
    assert len(http.requests) == 1


# Drafts


async def test_create_draft_saves_a_draft_without_sending_it() -> None:
    http = gmail()
    http.route("POST", f"{USERS_ME}/drafts", json=fixture("draft_created"))

    result = await run(http, "create_draft", MAIL)

    (request,) = http.requests
    assert set(request.json) == {"message"} and set(request.json["message"]) == {"raw"}
    mail = sent_mail(request.json["message"]["raw"])
    assert mail["To"] == "sara@acme.dev" and mail["Subject"] == "Launch review"
    assert result == {"account": "ali@acme.dev", "draftId": "r-5512", "messageId": "18f0d1", "threadId": "18f0d0"}


async def test_a_reply_draft_is_threaded_like_a_sent_reply() -> None:
    http = gmail()
    http.route("GET", THREAD, json=fixture("thread_reply_metadata"))
    http.route("POST", f"{USERS_ME}/drafts", json=fixture("draft_created"))
    await run(http, "create_draft", {**MAIL, "reply_to_thread_id": "18f0a0"})
    message = http.requests[1].json["message"]
    assert message["threadId"] == "18f0a0"
    assert sent_mail(message["raw"])["In-Reply-To"] == "<CAF2@mail.acme.dev>"


def test_the_draft_summary_says_it_is_a_draft() -> None:
    assert summary("create_draft", MAIL).startswith("Draft an email to sara@acme.dev: “Launch review”: Hi Sara")


async def test_replying_to_a_thread_that_is_gone_says_so() -> None:
    http = gmail()
    http.route("GET", THREAD, status=404, json={})
    with pytest.raises(GmailError, match="no thread 18f0a0"):
        await run(http, "send", {**MAIL, "reply_to_thread_id": "18f0a0"})
    assert len(http.requests) == 1  # nothing sent

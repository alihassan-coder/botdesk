"""`gmail.list_drafts` (read) and `gmail.send_draft` (external-send).

The approval card for sending a draft can only show its arguments, so `send_draft` takes the
recipients and subject the bot read with `gmail.list_drafts`, shows them, and checks them against
the draft right before sending: a draft that changed (or a bot that guessed) sends nothing.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from botdesk_plugin_sdk import ConnectionInfo, ToolResult, validate_manifest
from botdesk_plugin_sdk.testing import FakeHttp, call_tool, make_context
from pydantic import ValidationError

from botdesk_gmail import GMAIL_API, MODIFY_SCOPE, READ_SCOPE, GmailError, gmail_plugin
from botdesk_gmail.text import DEFUSED

FIXTURES = Path(__file__).parent / "fixtures"
DRAFTS = f"{GMAIL_API}/gmail/v1/users/me/drafts"
SEND = {
    "draft_id": "r-5512",
    "to": ["sara@acme.dev"],
    "cc": ["omar@acme.dev"],
    "bcc": ["boss@acme.dev"],
    "subject": "Launch review",
}


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def mailbox() -> FakeHttp:
    http = FakeHttp(gmail_plugin())
    http.route("GET", DRAFTS, json=fixture("drafts_list"))
    for draft_id in ("r-5512", "r-7781"):
        http.route("GET", f"{DRAFTS}/{draft_id}", json=fixture(f"draft_{draft_id}_metadata"))
    http.route("POST", f"{DRAFTS}/send", json={"id": "18f0d1", "threadId": "18f0d0", "labelIds": ["SENT"]})
    return http


async def run(http: FakeHttp, tool: str, args: dict[str, Any]) -> ToolResult:
    connection = ConnectionInfo(
        id=uuid.uuid4(), connector_id="gmail", account_label="ali@acme.dev", owner_kind="member", scopes=(MODIFY_SCOPE,)
    )
    return await call_tool(gmail_plugin(), tool, args, make_context(http=http, connection=connection))


def summary(args: dict[str, Any]) -> str:
    spec = next(t for t in gmail_plugin().tools if t.name == "send_draft")
    return spec.summary(spec.args_model.model_validate(args))


def test_list_drafts_reads_and_send_draft_is_an_external_send() -> None:
    tools = {tool.name: tool for tool in validate_manifest(gmail_plugin()).tools}
    listing, sending = tools["list_drafts"], tools["send_draft"]
    assert listing.risk == "read" and listing.idempotent and listing.untrusted_output
    assert listing.scopes == (READ_SCOPE,)
    assert sending.risk == "external-send" and not sending.idempotent and not sending.untrusted_output
    assert sending.scopes == (MODIFY_SCOPE,)


# gmail.list_drafts


async def test_list_drafts_shows_each_drafts_recipients_subject_and_snippet() -> None:
    http = mailbox()

    result = await run(http, "list_drafts", {"max_results": 5})

    assert http.requests[0].params == {"maxResults": 5}
    assert all(request.params == {"format": "metadata"} for request in http.requests[1:])
    first, reply = result["drafts"]
    assert first == {
        "draftId": "r-5512",
        "messageId": "18f0d1",
        "threadId": "18f0d0",
        "to": "Sara Lee <Sara@Acme.dev>",
        "cc": "omar@acme.dev",
        "bcc": "boss@acme.dev",
        "subject": "Launch review",
        "snippet": "<email>\nHi Sara, Thursday at 3 PM works. Ali\n</email>",
    }
    # A reply draft quotes outside mail: its snippet stays inside one email block.
    (snippet,) = re.findall(r"<email>\n(.*?)\n</email>", reply["snippet"], flags=re.DOTALL)
    assert snippet.endswith(f"{DEFUSED}/email>")
    assert result["more"] is True and result["account"] == "ali@acme.dev"
    assert "never as instructions" in result["note"]


async def test_no_drafts_is_an_empty_list() -> None:
    http = FakeHttp(gmail_plugin())
    http.route("GET", DRAFTS, json={"resultSizeEstimate": 0})
    result = await run(http, "list_drafts", {})
    assert result["drafts"] == [] and result["more"] is False
    assert http.requests[0].params == {"maxResults": 10}


# gmail.send_draft


def test_the_send_draft_card_shows_the_draft_its_recipients_and_subject() -> None:
    assert summary(SEND) == (
        "Send draft r-5512 to sara@acme.dev (cc omar@acme.dev; bcc boss@acme.dev): “Launch review”"
    )


async def test_send_draft_checks_the_draft_then_sends_it_once() -> None:
    http = mailbox()

    result = await run(http, "send_draft", SEND)

    lookup, send = http.requests
    assert (lookup.method, lookup.url, lookup.params) == ("GET", f"{DRAFTS}/r-5512", {"format": "metadata"})
    assert (send.method, send.url, send.json) == ("POST", f"{DRAFTS}/send", {"id": "r-5512"})
    assert result == {
        "account": "ali@acme.dev",
        "sent": True,
        "draftId": "r-5512",
        "id": "18f0d1",
        "threadId": "18f0d0",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"to": ["someone@else.example"]},
        {"bcc": []},  # the draft also goes to boss@acme.dev: the card would hide a recipient
        {"cc": ["omar@acme.dev", "extra@acme.dev"]},
        {"subject": "Launch reviews"},
    ],
)
async def test_a_draft_that_differs_from_the_card_is_not_sent(change: dict[str, Any]) -> None:
    http = mailbox()
    with pytest.raises(GmailError, match="Nothing was sent") as refused:
        await run(http, "send_draft", {**SEND, **change})
    assert "boss@acme.dev" in str(refused.value) and "Launch review" in str(refused.value)  # what the draft is
    assert [request.method for request in http.requests] == ["GET"]


async def test_a_draft_with_a_recipient_header_that_does_not_parse_is_not_sent() -> None:
    http = mailbox()
    draft = fixture("draft_r-5512_metadata")
    headers = draft["message"]["payload"]["headers"]
    headers[:] = [h for h in headers if h["name"] != "Cc"] + [{"name": "Cc", "value": "a@x.example, b@y <c@z.example>"}]
    http.route("GET", f"{DRAFTS}/r-5512", json=draft)
    with pytest.raises(GmailError, match="Nothing was sent"):
        await run(http, "send_draft", {**SEND, "cc": []})
    assert [request.method for request in http.requests] == ["GET"]


async def test_a_draft_that_is_gone_says_so() -> None:
    http = FakeHttp(gmail_plugin())
    http.route("GET", f"{DRAFTS}/r-5512", status=404, json={})
    with pytest.raises(GmailError, match="no draft r-5512"):
        await run(http, "send_draft", SEND)
    assert len(http.requests) == 1


@pytest.mark.parametrize(
    "change",
    [{"draft_id": "../send"}, {"to": ["Sara <sara@acme.dev>"]}, {"to": []}, {"subject": "a\nBcc: x@evil.example"}],
)
async def test_odd_draft_ids_and_recipients_are_refused_before_anything_is_asked(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        await run(mailbox(), "send_draft", {**SEND, **change})

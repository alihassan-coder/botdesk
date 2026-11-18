"""Drafts already in the mailbox: `gmail.list_drafts` (read) and `gmail.send_draft` (external-send).

- `list_drafts`: `drafts.list` + `drafts.get(format=full)`; each draft's id, recipients (Bcc too:
  they are the mailbox owner's own), subject, whole text (the plain-text part, or the HTML as text
  when there is none, quoted mail included: it is sent too) and attachments' names.
  `untrusted_output`: a reply draft quotes outside mail, so the text sits in an `<email>` block and
  the run is tainted. A text too long for an approval card is left out (`bodyLeftOut`).
- `send_draft`: an approval card only shows a call's arguments, so the call carries what will be
  sent, as `list_drafts` showed it: recipients, subject, text and attachments' names, and the card
  shows them all (ADR 0015 §3, updated 2026-11-18). Right before sending, the tool fetches the
  draft and sends it (`drafts.send`, once, never retried) only when its To, Cc, Bcc and Subject
  are exactly those, its text is the same (line breaks and spacing aside) and it has the same
  attachments; otherwise nothing is sent and the error says why.
"""

import asyncio
import re
from email.utils import getaddresses
from typing import Any

from botdesk_plugin_sdk import ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field, field_validator

from botdesk_gmail import api
from botdesk_gmail.text import MESSAGE_CAP, RESULT_CAP, Body, body_of, defuse, email_block, kept_headers
from botdesk_gmail.tools import ID_PATTERN, MAX_SEARCH_RESULTS, NOTE, READ_SCOPE
from botdesk_gmail.write_tools import MAX_BODY, MODIFY_SCOPE, Recipients, body_preview, recipients_line

_ID = re.compile(ID_PATTERN)
_DRAFT_HEADERS = ("To", "Cc", "Bcc", "Subject")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BLOCK = re.compile(r"\A\s*<email>\n?(.*?)\n?</email>\s*\Z", re.DOTALL)
MAX_ATTACHMENTS = 20


class ListDraftsArgs(BaseModel):
    max_results: int = Field(default=10, ge=1, le=MAX_SEARCH_RESULTS, description="How many drafts, 1-25.")


class SendDraftArgs(Recipients):
    draft_id: str = Field(pattern=ID_PATTERN, description="The draft's id (`draftId` from gmail.list_drafts).")
    subject: str = Field(
        min_length=1, max_length=250, description="The draft's subject, as gmail.list_drafts shows it."
    )
    body: str = Field(
        max_length=MAX_BODY,
        description=(
            "The draft's whole text, exactly as gmail.list_drafts shows it (`body`, without the <email> lines "
            "around it). The person approves this text; nothing is sent if the draft's text differs."
        ),
    )
    attachments: list[str] = Field(
        default_factory=list,
        max_length=MAX_ATTACHMENTS,
        description="The names of the draft's attachments, as gmail.list_drafts shows them. Empty: none.",
    )

    @field_validator("body")
    @classmethod
    def _without_block(cls, value: str) -> str:
        """The text as `list_drafts` showed it, with or without its `<email>` block: the card shows the text."""
        block = _BLOCK.match(value)
        return block.group(1) if block else value

    @field_validator("attachments")
    @classmethod
    def _names(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or len(value) > 255 or _CONTROL.search(value):
                raise ValueError(f"{value!r} isn't an attachment name as gmail.list_drafts shows it.")
        return values


def _account(ctx: ToolContext) -> str | None:
    return ctx.connection.account_label if ctx.connection else None


async def _draft(ctx: ToolContext, draft_id: str) -> Any:
    return await api.get(
        ctx.http, f"drafts/{draft_id}", what=f"draft {draft_id}", account=_account(ctx), params={"format": "full"}
    )


def _payload(draft: dict[str, Any]) -> Any:
    return (draft.get("message") or {}).get("payload") or {}


def _headers(draft: dict[str, Any]) -> Any:
    return _payload(draft).get("headers")


def _content(draft: dict[str, Any]) -> tuple[str, list[str]]:
    """What the draft sends, as a card can show it: its text (defused, like the model reads it)
    and its attachments' names."""
    body: Body = body_of(_payload(draft), whole=True)
    return defuse(body.text), [str(attachment["name"]) for attachment in body.attachments]


async def list_drafts(args: ListDraftsArgs, ctx: ToolContext) -> ToolResult:
    listing = await api.get(
        ctx.http, "drafts", what="drafts", account=_account(ctx), params={"maxResults": args.max_results}
    )
    ids = [d["id"] for d in listing.get("drafts") or [] if isinstance(d, dict) and _ID.fullmatch(str(d.get("id")))]
    drafts = await asyncio.gather(*(_draft(ctx, draft_id) for draft_id in ids[: args.max_results]))
    shown = []
    room = RESULT_CAP  # characters of text left for this result
    for draft_id, draft in zip(ids, drafts, strict=False):
        message = draft.get("message") or {}
        headers = kept_headers(_headers(draft), _DRAFT_HEADERS)
        text, attachments = _content(draft)
        entry: dict[str, Any] = {
            "draftId": draft_id,
            "messageId": str(message.get("id", "")),
            "threadId": str(message.get("threadId", "")),
            "to": headers.get("To", ""),
            "cc": headers.get("Cc", ""),
            "bcc": headers.get("Bcc", ""),
            "subject": headers.get("Subject", ""),
            "body": None,
            "attachments": attachments,
        }
        if len(text) > MESSAGE_CAP:
            entry["bodyLeftOut"] = (
                f"This draft's text is too long to show ({len(text)} characters), so gmail.send_draft can't "
                "send it. The person can send it from Gmail."
            )
        elif len(text) > room:
            entry["bodyLeftOut"] = "Left out to keep this list short: list fewer drafts (max_results) to see it."
        else:
            entry["body"] = email_block(text)
            room -= len(text)
        shown.append(entry)
    return {"account": _account(ctx), "drafts": shown, "more": bool(listing.get("nextPageToken")), "note": NOTE}


def _addresses(value: str) -> set[str] | None:
    """The addresses in a draft's header, or None when part of it doesn't parse as an address
    (Gmail might still send to it, so it never matches the card)."""
    parsed = [address for _name, address in getaddresses([value])] if value.strip() else []
    if any("@" not in address for address in parsed):
        return None
    return {address.lower() for address in parsed}


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _difference(args: SendDraftArgs, draft: dict[str, Any]) -> str | None:
    """How the draft differs from the approved call, or None when it is the email the card showed."""
    raw: dict[str, list[str]] = {}
    for header in _headers(draft) or []:
        if isinstance(header, dict):
            raw.setdefault(str(header.get("name", "")).lower(), []).append(str(header.get("value", "")))
    to, cc, bcc, subject = (", ".join(raw.get(name.lower(), [])) for name in _DRAFT_HEADERS)
    if not (
        _addresses(to) == {a.lower() for a in args.to}
        and _addresses(cc) == {a.lower() for a in args.cc}
        and _addresses(bcc) == {a.lower() for a in args.bcc}
        and _one_line(subject) == _one_line(args.subject)
    ):
        return f"Draft {args.draft_id} isn't the email the approval showed."
    text, attachments = _content(draft)
    if _one_line(text) != _one_line(args.body):
        return f"Draft {args.draft_id}'s text isn't the one the approval showed."
    if sorted(attachments) != sorted(args.attachments):
        names = ", ".join(attachments) or "none"
        return f"Draft {args.draft_id}'s attachments ({names}) aren't the ones the approval showed."
    return None


async def send_draft(args: SendDraftArgs, ctx: ToolContext) -> ToolResult:
    draft = await _draft(ctx, args.draft_id)
    if (difference := _difference(args, draft)) is not None:
        shown = kept_headers(_headers(draft), _DRAFT_HEADERS)
        holds = "; ".join(f"{name}: {shown[name]}" for name in _DRAFT_HEADERS if shown.get(name)) or "no recipients"
        raise api.GmailError(
            f"{difference} Nothing was sent. The draft has: {email_block(holds)} "
            "Check with the person, then call gmail.list_drafts again and gmail.send_draft with the draft "
            "as it is now."
        )
    sent = await api.post(
        ctx.http, "drafts/send", what=f"draft {args.draft_id}", account=_account(ctx), body={"id": args.draft_id}
    )
    return {
        "account": _account(ctx),
        "sent": True,
        "draftId": args.draft_id,
        "id": str(sent.get("id", "")),
        "threadId": str(sent.get("threadId", "")),
    }


def _summary(args: SendDraftArgs) -> str:
    attached = f" with {', '.join(args.attachments)}" if args.attachments else ""
    return (
        f"Send draft {args.draft_id} to {recipients_line(args)}: “{args.subject}”{attached}: {body_preview(args.body)}"
    )


DRAFT_TOOLS = (
    ToolSpec(
        name="list_drafts",
        title="List email drafts",
        description=(
            "List the drafts in the connected Gmail mailbox, newest first: draftId, to, cc, bcc, subject, the "
            "whole text (body) and the attachments' names. Use them with gmail.send_draft."
        ),
        args_model=ListDraftsArgs,
        risk="read",
        handler=list_drafts,
        idempotent=True,
        untrusted_output=True,
        scopes=(READ_SCOPE,),
    ),
    ToolSpec(
        name="send_draft",
        title="Send an email draft",
        description=(
            "Send a draft that is already in Gmail. Give its draftId and, exactly as gmail.list_drafts shows "
            "them, its recipients (plain addresses), subject, text (body) and attachments' names: the person "
            "approves those, and nothing is sent if the draft doesn't match."
        ),
        args_model=SendDraftArgs,
        risk="external-send",
        handler=send_draft,
        scopes=(MODIFY_SCOPE,),
        summarize=_summary,
    ),
)

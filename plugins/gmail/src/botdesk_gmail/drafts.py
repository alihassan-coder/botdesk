"""Drafts already in the mailbox: `gmail.list_drafts` (read) and `gmail.send_draft` (external-send).

- `list_drafts`: `drafts.list` + `drafts.get(format=metadata)`; each draft's id, recipients
  (Bcc too: they are the mailbox owner's own), subject and snippet. `untrusted_output`: a reply
  draft quotes outside mail, so the snippet sits in an `<email>` block and the run is tainted.
- `send_draft`: an approval card only shows a call's arguments, so the call carries the draft's
  recipients and subject (from `list_drafts`) and the card shows them. Right before sending, the
  tool fetches the draft and sends it (`drafts.send`, once, never retried) only when its To, Cc,
  Bcc and Subject are exactly those; otherwise nothing is sent and the error says what the draft
  holds. The body isn't on the card: the draft is the person's own (or one a bot saved through an
  approved `gmail.create_draft`).
"""

import asyncio
import re
from email.utils import getaddresses
from typing import Any

from botdesk_plugin_sdk import ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field

from botdesk_gmail import api
from botdesk_gmail.text import email_block, kept_headers, plain_snippet
from botdesk_gmail.tools import ID_PATTERN, MAX_SEARCH_RESULTS, NOTE, READ_SCOPE
from botdesk_gmail.write_tools import MODIFY_SCOPE, Recipients, recipients_line

_ID = re.compile(ID_PATTERN)
_DRAFT_HEADERS = ("To", "Cc", "Bcc", "Subject")


class ListDraftsArgs(BaseModel):
    max_results: int = Field(default=10, ge=1, le=MAX_SEARCH_RESULTS, description="How many drafts, 1-25.")


class SendDraftArgs(Recipients):
    draft_id: str = Field(pattern=ID_PATTERN, description="The draft's id (`draftId` from gmail.list_drafts).")
    subject: str = Field(
        min_length=1, max_length=250, description="The draft's subject, as gmail.list_drafts shows it."
    )


def _account(ctx: ToolContext) -> str | None:
    return ctx.connection.account_label if ctx.connection else None


async def _draft(ctx: ToolContext, draft_id: str) -> Any:
    return await api.get(
        ctx.http, f"drafts/{draft_id}", what=f"draft {draft_id}", account=_account(ctx), params={"format": "metadata"}
    )


def _headers(draft: dict[str, Any]) -> Any:
    return ((draft.get("message") or {}).get("payload") or {}).get("headers")


async def list_drafts(args: ListDraftsArgs, ctx: ToolContext) -> ToolResult:
    listing = await api.get(
        ctx.http, "drafts", what="drafts", account=_account(ctx), params={"maxResults": args.max_results}
    )
    ids = [d["id"] for d in listing.get("drafts") or [] if isinstance(d, dict) and _ID.fullmatch(str(d.get("id")))]
    drafts = await asyncio.gather(*(_draft(ctx, draft_id) for draft_id in ids[: args.max_results]))
    shown = []
    for draft_id, draft in zip(ids, drafts, strict=False):
        message = draft.get("message") or {}
        headers = kept_headers(_headers(draft), _DRAFT_HEADERS)
        shown.append(
            {
                "draftId": draft_id,
                "messageId": str(message.get("id", "")),
                "threadId": str(message.get("threadId", "")),
                "to": headers.get("To", ""),
                "cc": headers.get("Cc", ""),
                "bcc": headers.get("Bcc", ""),
                "subject": headers.get("Subject", ""),
                "snippet": email_block(plain_snippet(message.get("snippet"))),
            }
        )
    return {"account": _account(ctx), "drafts": shown, "more": bool(listing.get("nextPageToken")), "note": NOTE}


def _addresses(value: str) -> set[str] | None:
    """The addresses in a draft's header, or None when part of it doesn't parse as an address
    (Gmail might still send to it, so it never matches the card)."""
    parsed = [address for _name, address in getaddresses([value])] if value.strip() else []
    if any("@" not in address for address in parsed):
        return None
    return {address.lower() for address in parsed}


async def send_draft(args: SendDraftArgs, ctx: ToolContext) -> ToolResult:
    draft = await _draft(ctx, args.draft_id)
    raw: dict[str, list[str]] = {}
    for header in _headers(draft) or []:
        if isinstance(header, dict):
            raw.setdefault(str(header.get("name", "")).lower(), []).append(str(header.get("value", "")))
    to, cc, bcc, subject = (", ".join(raw.get(name.lower(), [])) for name in _DRAFT_HEADERS)
    matches = (
        _addresses(to) == {a.lower() for a in args.to}
        and _addresses(cc) == {a.lower() for a in args.cc}
        and _addresses(bcc) == {a.lower() for a in args.bcc}
        and " ".join(subject.split()) == " ".join(args.subject.split())
    )
    if not matches:
        shown = kept_headers(_headers(draft), _DRAFT_HEADERS)
        holds = "; ".join(f"{name}: {shown[name]}" for name in _DRAFT_HEADERS if shown.get(name)) or "no recipients"
        raise api.GmailError(
            f"Draft {args.draft_id} isn't the email the approval showed. Nothing was sent. "
            f"The draft has: {email_block(holds)} "
            "Check with the person, then call gmail.send_draft with the draft's own recipients and subject."
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


DRAFT_TOOLS = (
    ToolSpec(
        name="list_drafts",
        title="List email drafts",
        description=(
            "List the drafts in the connected Gmail mailbox, newest first: draftId, to, cc, bcc, subject "
            "and a snippet. Use them with gmail.send_draft."
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
            "them, its recipients (plain addresses) and subject: the person approves those, and nothing is "
            "sent if the draft doesn't match."
        ),
        args_model=SendDraftArgs,
        risk="external-send",
        handler=send_draft,
        scopes=(MODIFY_SCOPE,),
        summarize=lambda args: f"Send draft {args.draft_id} to {recipients_line(args)}: “{args.subject}”",
    ),
)

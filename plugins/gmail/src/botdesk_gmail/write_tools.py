"""The write tools (slice 6.2, ADR 0011 §3): labels, archive, drafts, send and trash.

Each needs `gmail.modify` and makes one change per call, with one request to Gmail that is never
retried here (the app's `tool_executions` record makes sure a started send isn't run again).

| Tool | Gmail API | Risk |
|---|---|---|
| `add_labels`, `remove_labels` | `threads.modify` | `write-external` |
| `archive` (remove `INBOX`) | `threads.modify` | `write-external` |
| `create_draft` (new or reply) | `drafts.create` | `write-external` |
| `send` (new or reply) | `messages.send` | `external-send` |
| `trash` | `threads.trash` | `destructive` |

Mail is plain text, built with the standard library's `email` package and sent base64url-encoded
(`raw`). With `format="markdown"` it is `multipart/alternative`: the body as written, and HTML that
`markdown.py` generates from it (the model's own markup is escaped, never sent as HTML).
Recipients are bare addresses and the subject is one line: anything that could add a
header (a line break, a second address in one entry, a display name) is refused by the args
model, before an approval card is even shown. A reply is threaded with `threadId`, `In-Reply-To`
and `References` taken from the thread's newest message. Sending an existing draft by id is
`drafts.py` (`send_draft`).
"""

import base64
import email.policy
import re
from email.message import EmailMessage
from typing import Any, Literal

from botdesk_plugin_sdk import ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field, field_validator, model_validator

from botdesk_gmail import api
from botdesk_gmail.markdown import markdown_to_html
from botdesk_gmail.tools import ID_PATTERN

MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
MAX_RECIPIENTS = 20
MAX_BODY = 50_000
PREVIEW = 120  # characters of the body on an approval card's summary line

_ADDRESS = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LABEL = re.compile(r"[A-Za-z0-9_-]{1,100}")
# Trash and spam have their own tool (or none); drafts and sent mail aren't labels Gmail lets anyone set.
_NOT_LABELS = {"TRASH", "SPAM", "DRAFT", "SENT"}
_MESSAGE_ID = re.compile(r"<[^<>\s]{1,250}>")


def _addresses(values: list[str]) -> list[str]:
    for value in values:
        if not _ADDRESS.fullmatch(value):
            raise ValueError(
                f"{value!r} isn't a plain email address. Give one address per entry, like sara@acme.dev, "
                "without a name or anything else."
            )
    return values


class LabelArgs(BaseModel):
    thread_id: str = Field(pattern=ID_PATTERN, description="The thread's id (`threadId` from gmail.search).")
    label_ids: list[str] = Field(
        min_length=1,
        max_length=10,
        description=(
            "Label ids from gmail.list_labels: the user's own (Label_12) or system ones such as STARRED, "
            "IMPORTANT, UNREAD (remove it to mark as read) or INBOX. Not TRASH or SPAM: use gmail.trash."
        ),
    )

    @field_validator("label_ids")
    @classmethod
    def _labels(cls, values: list[str]) -> list[str]:
        for value in values:
            if not _LABEL.fullmatch(value):
                raise ValueError(f"{value!r} isn't a label id. Get ids from gmail.list_labels.")
            if value.upper() in _NOT_LABELS:
                raise ValueError(f"{value} can't be changed as a label. To move mail to Trash use gmail.trash.")
        return values


class ThreadArgs(BaseModel):
    thread_id: str = Field(pattern=ID_PATTERN, description="The thread's id (`threadId` from gmail.search).")


class Recipients(BaseModel):
    """Who an email goes to and its subject: what an approval card shows, safe as headers."""

    to: list[str] = Field(min_length=1, max_length=MAX_RECIPIENTS, description="Recipients: plain addresses.")
    cc: list[str] = Field(default_factory=list, max_length=MAX_RECIPIENTS, description="Cc: plain addresses.")
    bcc: list[str] = Field(default_factory=list, max_length=MAX_RECIPIENTS, description="Bcc: plain addresses.")
    subject: str = Field(
        min_length=1,
        max_length=250,
        description=(
            "One line. For a reply, the thread's subject with 'Re: ' in front, so Gmail keeps it in the thread."
        ),
    )

    _to = field_validator("to")(_addresses)
    _cc = field_validator("cc")(_addresses)
    _bcc = field_validator("bcc")(_addresses)

    @field_validator("subject")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if _CONTROL.search(value):
            raise ValueError("The subject must be one line, without line breaks or control characters.")
        return value

    @model_validator(mode="after")
    def _not_too_many(self) -> "Recipients":
        if len(self.to) + len(self.cc) + len(self.bcc) > MAX_RECIPIENTS:
            raise ValueError(f"An email can have at most {MAX_RECIPIENTS} recipients in To, Cc and Bcc together.")
        return self


class MailArgs(Recipients):
    body: str = Field(min_length=1, max_length=MAX_BODY, description="The message, as plain text or Markdown.")
    format: Literal["plain", "markdown"] = Field(
        default="plain",
        description=(
            "plain (the default): the body is sent as written. markdown: also send it formatted, from "
            "simple Markdown only (# headings, - and 1. lists, **bold**, *italic*, `code`, [text](https://…)). "
            "HTML in the body is sent as text, never as HTML."
        ),
    )
    reply_to_thread_id: str | None = Field(
        default=None,
        pattern=ID_PATTERN,
        description="To reply in a thread: its threadId. The reply answers the thread's newest message.",
    )


def _account(ctx: ToolContext) -> str | None:
    return ctx.connection.account_label if ctx.connection else None


# Labels, archive, trash


async def _modify(ctx: ToolContext, thread_id: str, change: dict[str, list[str]]) -> None:
    await api.post(
        ctx.http, f"threads/{thread_id}/modify", what=f"thread {thread_id}", account=_account(ctx), body=change
    )


async def add_labels(args: LabelArgs, ctx: ToolContext) -> ToolResult:
    await _modify(ctx, args.thread_id, {"addLabelIds": args.label_ids})
    return {"account": _account(ctx), "threadId": args.thread_id, "added": args.label_ids}


async def remove_labels(args: LabelArgs, ctx: ToolContext) -> ToolResult:
    await _modify(ctx, args.thread_id, {"removeLabelIds": args.label_ids})
    return {"account": _account(ctx), "threadId": args.thread_id, "removed": args.label_ids}


async def archive(args: ThreadArgs, ctx: ToolContext) -> ToolResult:
    await _modify(ctx, args.thread_id, {"removeLabelIds": ["INBOX"]})
    return {"account": _account(ctx), "threadId": args.thread_id, "archived": True}


async def trash(args: ThreadArgs, ctx: ToolContext) -> ToolResult:
    thread_id = args.thread_id
    await api.post(ctx.http, f"threads/{thread_id}/trash", what=f"thread {thread_id}", account=_account(ctx))
    return {"account": _account(ctx), "threadId": thread_id, "trashed": True}


# Drafts and send


async def _threading(ctx: ToolContext, thread_id: str) -> dict[str, str]:
    """`In-Reply-To` and `References` answering the thread's newest message. Its headers are outside
    text, so only well-formed message ids are kept."""
    thread = await api.get(
        ctx.http,
        f"threads/{thread_id}",
        what=f"thread {thread_id}",
        account=_account(ctx),
        params={"format": "metadata"},
    )
    messages = [m for m in thread.get("messages") or [] if isinstance(m, dict)]
    if not messages:
        return {}
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in (messages[-1].get("payload") or {}).get("headers") or []
        if isinstance(h, dict)
    }
    message_id = headers.get("message-id", "").strip()
    if not _MESSAGE_ID.fullmatch(message_id):
        return {}
    earlier = [ref for ref in headers.get("references", "").split() if _MESSAGE_ID.fullmatch(ref)]
    return {"In-Reply-To": message_id, "References": " ".join([*earlier[-20:], message_id])}


async def _raw_mail(args: MailArgs, ctx: ToolContext) -> dict[str, Any]:
    """Gmail's message resource for this email: `raw` (base64url RFC 2822) and, for a reply, `threadId`."""
    mail = EmailMessage(policy=email.policy.SMTP)
    mail["To"] = ", ".join(args.to)
    if args.cc:
        mail["Cc"] = ", ".join(args.cc)
    if args.bcc:
        mail["Bcc"] = ", ".join(args.bcc)  # Gmail delivers to them and drops the header
    mail["Subject"] = args.subject
    threading = await _threading(ctx, args.reply_to_thread_id) if args.reply_to_thread_id else {}
    for name, value in threading.items():
        mail[name] = value
    mail.set_content(args.body)
    if args.format == "markdown":  # plain text first, then the HTML we generate: mail apps show the last they can
        mail.add_alternative(markdown_to_html(args.body), subtype="html")
    message: dict[str, Any] = {"raw": base64.urlsafe_b64encode(mail.as_bytes()).decode("ascii")}
    if args.reply_to_thread_id:
        message["threadId"] = args.reply_to_thread_id
    return message


async def send(args: MailArgs, ctx: ToolContext) -> ToolResult:
    message = await _raw_mail(args, ctx)
    sent = await api.post(ctx.http, "messages/send", what="the email", account=_account(ctx), body=message)
    return {
        "account": _account(ctx),
        "sent": True,
        "id": str(sent.get("id", "")),
        "threadId": str(sent.get("threadId", "")),
    }


async def create_draft(args: MailArgs, ctx: ToolContext) -> ToolResult:
    message = await _raw_mail(args, ctx)
    draft = await api.post(ctx.http, "drafts", what="the draft", account=_account(ctx), body={"message": message})
    saved = draft.get("message") or {}
    return {
        "account": _account(ctx),
        "draftId": str(draft.get("id", "")),
        "messageId": str(saved.get("id", "")),
        "threadId": str(saved.get("threadId", "")),
    }


# Approval card summaries: the exact action, from the arguments alone.


def _labels_summary(verb: str, preposition: str) -> Any:
    def summarize(args: LabelArgs) -> str:
        noun = "label" if len(args.label_ids) == 1 else "labels"
        return f"{verb} {noun} {', '.join(args.label_ids)} {preposition} email thread {args.thread_id}"

    return summarize


def recipients_line(args: Recipients) -> str:
    """ "sara@acme.dev (cc omar@acme.dev; bcc boss@acme.dev)": every recipient, for a card."""
    copies = [f"cc {', '.join(args.cc)}"] * bool(args.cc) + [f"bcc {', '.join(args.bcc)}"] * bool(args.bcc)
    return ", ".join(args.to) + (f" ({'; '.join(copies)})" if copies else "")


def body_preview(text: str) -> str:
    """The start of a body on one line, for a card's summary (the card shows all of it below)."""
    body = " ".join(text.split())
    return body if len(body) <= PREVIEW else body[:PREVIEW].rstrip() + "…"


def _mail_summary(draft: bool) -> Any:
    def summarize(args: MailArgs) -> str:
        if args.reply_to_thread_id:
            action = f"{'Draft a reply' if draft else 'Reply'} in email thread {args.reply_to_thread_id} to"
        else:
            action = f"{'Draft' if draft else 'Send'} an email to"
        return f"{action} {recipients_line(args)}: “{args.subject}”: {body_preview(args.body)}"

    return summarize


WRITE_TOOLS = (
    ToolSpec(
        name="add_labels",
        title="Add email labels",
        description="Add labels to every message of a Gmail thread (STARRED to star it, IMPORTANT, or the user's own).",
        args_model=LabelArgs,
        risk="write-external",
        handler=add_labels,
        idempotent=True,
        scopes=(MODIFY_SCOPE,),
        summarize=_labels_summary("Add", "to"),
    ),
    ToolSpec(
        name="remove_labels",
        title="Remove email labels",
        description="Remove labels from every message of a Gmail thread (UNREAD to mark it read, STARRED to unstar).",
        args_model=LabelArgs,
        risk="write-external",
        handler=remove_labels,
        idempotent=True,
        scopes=(MODIFY_SCOPE,),
        summarize=_labels_summary("Remove", "from"),
    ),
    ToolSpec(
        name="archive",
        title="Archive an email thread",
        description="Archive a Gmail thread: it leaves the inbox and stays in All Mail.",
        args_model=ThreadArgs,
        risk="write-external",
        handler=archive,
        idempotent=True,
        scopes=(MODIFY_SCOPE,),
        summarize=lambda args: f"Archive email thread {args.thread_id}",
    ),
    ToolSpec(
        name="create_draft",
        title="Draft an email",
        description=(
            "Save a plain-text draft in the connected Gmail account, new or as a reply in a thread "
            "(reply_to_thread_id). Nothing is sent: the person sends it from Gmail."
        ),
        args_model=MailArgs,
        risk="write-external",
        handler=create_draft,
        scopes=(MODIFY_SCOPE,),
        summarize=_mail_summary(draft=True),
    ),
    ToolSpec(
        name="send",
        title="Send an email",
        description=(
            "Send a plain-text email from the connected Gmail account, new or as a reply in a thread "
            "(reply_to_thread_id). At most 20 recipients."
        ),
        args_model=MailArgs,
        risk="external-send",
        handler=send,
        scopes=(MODIFY_SCOPE,),
        summarize=_mail_summary(draft=False),
    ),
    ToolSpec(
        name="trash",
        title="Move an email thread to Trash",
        description="Move a Gmail thread to Trash. Gmail deletes it for good after 30 days.",
        args_model=ThreadArgs,
        risk="destructive",
        handler=trash,
        idempotent=True,
        scopes=(MODIFY_SCOPE,),
        summarize=lambda args: f"Move email thread {args.thread_id} to Trash",
    ),
)

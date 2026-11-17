"""`gmail.read_attachment`: one attachment as text, when it is text.

`read` and idempotent, needing `gmail.readonly`, and `untrusted_output`: an attachment was
written by someone outside, so reading it taints the run, and its text sits in an `<email>`
block like a message body (ADR 0011 §4).

- The attachment is named by its message and **part** ("1", "0.2"), as `gmail.read_thread`
  lists it. Gmail's attachment ids change from one read to the next, so the tool looks the part
  up again (`messages.get(format=full)`) and fetches it with the id from that answer
  (`messages.attachments.get`).
- Only text is read: `text/*` (HTML as text), JSON, CSV and XML, or a file with a text name
  (`.csv`, `.txt`…) sent as `application/octet-stream`. PDFs, images and Office files are not
  downloaded; the result says so. Nothing is installed to read them.
- At most `MAX_DOWNLOAD` bytes are fetched and `TEXT_CAP` characters shown, with a `cut` note.
"""

import re
from typing import Any

from botdesk_plugin_sdk import ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field

from botdesk_gmail import api
from botdesk_gmail.text import attachment_part, cap, charset_of, decode, defuse, email_block, html_to_text
from botdesk_gmail.tools import ID_PATTERN, NOTE, READ_SCOPE

TEXT_CAP = 100_000  # characters of one attachment's text
MAX_DOWNLOAD = 10_000_000  # bytes, as Gmail reports the attachment's size
_TEXT_TYPES = {"application/json", "application/csv", "application/xml", "text/csv"}
_TEXT_NAMES = (".csv", ".tsv", ".txt", ".md", ".json", ".log", ".xml")
_ATTACHMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,2048}")


class AttachmentArgs(BaseModel):
    message_id: str = Field(
        pattern=ID_PATTERN, description="The message's id (`id` of a message in gmail.read_thread)."
    )
    part: str = Field(
        pattern=r"^[0-9]{1,4}(\.[0-9]{1,4}){0,9}$",
        description="The attachment's `part` as gmail.read_thread lists it, like 1 or 0.2.",
    )


def _account(ctx: ToolContext) -> str | None:
    return ctx.connection.account_label if ctx.connection else None


def _is_text(mime: str, name: str) -> bool:
    if mime.startswith("text/") or mime in _TEXT_TYPES or mime.endswith(("+json", "+xml")):
        return True
    return mime in ("application/octet-stream", "") and name.lower().endswith(_TEXT_NAMES)


async def read_attachment(args: AttachmentArgs, ctx: ToolContext) -> ToolResult:
    account = _account(ctx)
    path = f"messages/{args.message_id}"
    message = await api.get(
        ctx.http, path, what=f"message {args.message_id}", account=account, params={"format": "full"}
    )
    part = attachment_part(message.get("payload"), args.part)
    if part is None:
        raise api.GmailError(
            f"Message {args.message_id} has no attachment in part {args.part}. "
            "Use the `part` gmail.read_thread lists for the attachment."
        )
    content: dict[str, Any] = part["body"] if isinstance(part.get("body"), dict) else {}
    name = defuse(str(part.get("filename") or "")) or "(no name)"
    mime = str(part.get("mimeType", "")).lower()
    size = int(content.get("size") or 0)
    result: dict[str, Any] = {
        "account": account,
        "messageId": args.message_id,
        "part": args.part,
        "name": name,
        "type": defuse(mime),
        "size": size,
    }
    unreadable = _unreadable(name, mime, size)
    if unreadable:
        return {**result, "unreadable": unreadable, "note": NOTE}

    data = content.get("data")
    if not data:  # the usual case: the content is fetched on its own
        attachment_id = str(content.get("attachmentId") or "")
        if not _ATTACHMENT_ID.fullmatch(attachment_id):
            raise api.GmailError(f"Gmail didn't say where the attachment in part {args.part} is. Try again.")
        fetched = await api.get(ctx.http, f"{path}/attachments/{attachment_id}", what=name, account=account)
        data = fetched.get("data")
    text = decode(data, charset_of(part)).replace("\r\n", "\n")
    text = html_to_text(text) if mime == "text/html" else text.strip()
    shown, left_out = cap(text, TEXT_CAP)
    result["text"] = email_block(shown)
    if left_out:
        result["cut"] = f"[cut: {left_out} more characters not shown]"
    return {**result, "note": NOTE}


def _unreadable(name: str, mime: str, size: int) -> str | None:
    """Why this attachment isn't downloaded, or None when it will be read."""
    if mime == "application/pdf" or name.lower().endswith(".pdf"):
        return f"BotDesk can't read PDF attachments yet. Ask the person to open {name} in Gmail."
    if not _is_text(mime, name):
        return (
            f"{name} is {defuse(mime) or 'of an unknown type'}: BotDesk only reads text attachments "
            "(plain text, CSV, JSON, XML, HTML)."
        )
    if size > MAX_DOWNLOAD:
        return f"{name} is too big to read here ({size / 1_000_000:.1f} MB; at most {MAX_DOWNLOAD // 1_000_000} MB)."
    return None


ATTACHMENT_TOOLS = (
    ToolSpec(
        name="read_attachment",
        title="Read an email attachment",
        description=(
            "Read one attachment of a Gmail message as text: plain text, CSV, JSON, XML or HTML, up to "
            "100 000 characters. Give the message id and the attachment's `part` from gmail.read_thread. "
            "PDFs, images and Office files can't be read."
        ),
        args_model=AttachmentArgs,
        risk="read",
        handler=read_attachment,
        idempotent=True,
        untrusted_output=True,
        scopes=(READ_SCOPE,),
    ),
)

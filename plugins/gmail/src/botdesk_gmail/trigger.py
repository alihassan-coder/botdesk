"""The `new_email` trigger (slice 6.3, ADR 0011 §5): history polling, once a minute.

The cursor is a Gmail `historyId`:

- no cursor (just switched on): remember the mailbox's current `historyId` (`users.getProfile`)
  and report nothing, so old mail never starts runs;
- otherwise `users.history.list(startHistoryId=cursor, historyTypes=messageAdded, labelId=INBOX)`:
  each new inbox message is one event, except the mailbox's own mail (`SENT`, or from its own
  address: a bot that emails its own mailbox must not start itself again), drafts, and the
  Promotions and Social tabs. At most `MAX_EVENTS` per poll; a notice counts the rest;
- an expired cursor (404, Gmail keeps history about a week): start again from now, with one
  notice and no events.

Events carry the sender and subject for the chat line people see; the run reads the mail itself
with `gmail.read_thread`, so the email's text reaches the model only as untrusted tool output.
"""

import re
from email.utils import parseaddr
from typing import Any

from botdesk_plugin_sdk import ToolContext, TriggerEvent, TriggerPollResult, TriggerSpec

from botdesk_gmail import api
from botdesk_gmail.text import kept_headers
from botdesk_gmail.tools import ID_PATTERN

MAX_EVENTS = 10
SKIPPED_LABELS = {"SENT", "DRAFT", "SPAM", "TRASH", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}
SUMMARY_CAP = 200
_ID = re.compile(ID_PATTERN)
MISSED = "BotDesk missed some new mail while it couldn't check this mailbox; it reacts to new mail from now on."


def _account(ctx: ToolContext) -> str | None:
    return ctx.connection.account_label if ctx.connection else None


async def _now(ctx: ToolContext) -> str:
    profile = await api.get(ctx.http, "profile", what="mailbox profile", account=_account(ctx))
    if not profile.get("historyId"):
        raise api.GmailError("Gmail didn't say where this mailbox's history is. BotDesk will try again.")
    return str(profile["historyId"])


async def poll_new_email(ctx: ToolContext, cursor: str | None) -> TriggerPollResult:
    if cursor is None:
        return TriggerPollResult(events=(), cursor=await _now(ctx))
    try:
        history = await api.get(
            ctx.http,
            "history",
            what="mail history",
            account=_account(ctx),
            params={"startHistoryId": cursor, "historyTypes": "messageAdded", "labelId": "INBOX", "maxResults": 500},
        )
    except api.GmailError as error:
        if error.status == 404:  # the cursor is too old: Gmail no longer has that history
            return TriggerPollResult(events=(), cursor=await _now(ctx), notice=MISSED)
        raise
    new = _new_inbox_ids(history)
    events = []
    for message_id in new[:MAX_EVENTS]:
        if event := await _event(ctx, message_id):
            events.append(event)
    left_out = len(new) - MAX_EVENTS
    notice = None
    if left_out > 0 or history.get("nextPageToken"):
        count = f"{max(left_out, 0)}{'+' if history.get('nextPageToken') else ''}"
        notice = f"{count} more new emails arrived at once. Your bot reacts to at most {MAX_EVENTS} a minute."
    return TriggerPollResult(events=tuple(events), cursor=str(history.get("historyId") or cursor), notice=notice)


def _new_inbox_ids(history: dict[str, Any]) -> list[str]:
    """Ids of messages added to the inbox, oldest first, each once."""
    ids: dict[str, None] = {}
    for record in history.get("history") or []:
        for added in record.get("messagesAdded") or [] if isinstance(record, dict) else []:
            message = added.get("message") if isinstance(added, dict) else None
            if not isinstance(message, dict):
                continue
            labels = set(message.get("labelIds") or [])
            message_id = message.get("id")
            if (
                "INBOX" in labels
                and not labels & SKIPPED_LABELS
                and isinstance(message_id, str)
                and _ID.match(message_id)
            ):
                ids[message_id] = None
    return list(ids)


async def _event(ctx: ToolContext, message_id: str) -> TriggerEvent | None:
    try:
        message = await api.get(
            ctx.http,
            f"messages/{message_id}",
            what=f"message {message_id}",
            account=_account(ctx),
            params={"format": "metadata"},
        )
    except api.GmailError as error:
        if error.status == 404:  # deleted already
            return None
        raise
    headers = kept_headers((message.get("payload") or {}).get("headers"))
    sender, subject = headers.get("From", ""), headers.get("Subject", "")
    name, address = parseaddr(sender)
    account = _account(ctx)
    if account and address.casefold() == account.casefold():
        return None
    summary = f"New email from {name or address or 'an unknown sender'}: {subject or '(no subject)'}"
    return TriggerEvent(
        external_id=message_id,
        summary=" ".join(summary.split())[:SUMMARY_CAP],
        payload={
            "messageId": message_id,
            "threadId": str(message.get("threadId", "")),
            "from": sender,
            "subject": subject,
            "account": account,
        },
    )


NEW_EMAIL = TriggerSpec(
    name="new_email",
    title="React to new email",
    description=(
        "When a new email reaches the inbox, the bot gets a message in your chat with it and reads the "
        "email. Not for your own sent mail, drafts, Promotions or Social."
    ),
    poll=poll_new_email,
    interval_seconds=60,
    untrusted_payload=True,
)

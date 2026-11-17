"""Triggers: something in another app that starts a run ("a new email arrived").

Declared in the manifest so consent screens show them; BotDesk polls each subscription from a
scheduled job on its job queue (ADR 0011, owner decision 2026-11-15). The first trigger is
Gmail's `new_email` (slice 6.3).

    async def poll(ctx, cursor):          # ctx.http reaches the subscription's connection
        if cursor is None:                # just switched on: remember "now", start nothing
            return TriggerPollResult(events=(), cursor=current_position)
        ...
        return TriggerPollResult(events=new_things, cursor=next_position)

BotDesk saves the returned cursor only after it has handled the events, and handles each
`external_id` once.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from botdesk_plugin_sdk.tool import ToolContext


@dataclass(frozen=True)
class TriggerEvent:
    """One thing that happened. `external_id` is the provider's id, so it's handled once."""

    external_id: str
    summary: str  # one line for the chat: "New email from sara@acme.dev: Launch"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TriggerPollResult:
    """What one poll found, and the cursor to pass to the next poll."""

    events: tuple[TriggerEvent, ...]
    cursor: str | None
    # One line for the chat when something couldn't be handled event by event ("Some new mail
    # was missed…", "12 more emails arrived…"). Shown to people, never starts a run.
    notice: str | None = None


TriggerPoll = Callable[[ToolContext, str | None], Awaitable[TriggerPollResult]]
"""`async def poll(ctx, cursor) -> TriggerPollResult`. `cursor` is None on the first poll."""

MIN_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class TriggerSpec:
    """A trigger a bot can subscribe to. `untrusted_payload`: the events are outside text, so the
    run they start is tainted from its first step (ADR 0004)."""

    name: str  # "new_email"
    title: str  # "When a new email arrives"
    description: str
    poll: TriggerPoll
    interval_seconds: int = 300
    untrusted_payload: bool = True

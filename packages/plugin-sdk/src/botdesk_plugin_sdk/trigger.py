"""Triggers: something in another app that starts a run ("a new email arrived").

Declared in the manifest now so consent screens show them; BotDesk runs them as scheduled jobs
on its job queue (ADR 0011, owner decision 2026-11-15). The poll handler's shape may still grow
before the first trigger ships (roadmap slice 6.3).
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

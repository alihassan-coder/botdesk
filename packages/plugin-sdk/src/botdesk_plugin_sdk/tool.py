"""Tools: one thing a bot can do, and what its handler is given when it runs."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from botdesk_plugin_sdk.risk import Egress, RiskClass

ToolResult = dict[str, Any]
"""What a handler returns: a JSON-friendly dict (str keys; str, number, bool, None, list or
dict values). BotDesk stores it with the run and shows it to the model, so keep it small and
leave secrets out."""


@dataclass(frozen=True)
class ToolContext:
    """What a handler gets besides its arguments, and nothing more.

    There is deliberately no database session, no settings object and no other organization's
    tokens here: a plugin can only reach what the app hands it. `idempotency_key` stays the same
    when the same call is retried, so a tool whose service accepts one (Stripe, for example) can
    pass it on and a retry never charges twice. `logger` is named after the plugin, so its lines
    are easy to find.
    """

    org_id: uuid.UUID
    bot_id: uuid.UUID
    run_id: uuid.UUID
    tool_call_id: str
    idempotency_key: str
    logger: logging.Logger


ToolHandler = Callable[[Any, ToolContext], Awaitable[ToolResult]]
"""`async def handler(args: YourArgs, ctx: ToolContext) -> ToolResult`. The first argument is
typed `Any` here so each handler can name its own args model."""


class NoArgs(BaseModel):
    """The args model for a tool that takes no arguments."""


@dataclass(frozen=True)
class ToolSpec:
    """One thing a bot can do.

    Arguments are always a Pydantic model (`args_model`): its JSON schema is what the model is
    shown, and BotDesk validates every call against it before the handler runs, so the handler
    only ever sees clean, typed input. Describe each field with `Field(description=...)`; the
    model reads those descriptions.

    `untrusted_output` marks tools that return outside text (an email body, a web page): reading
    it "taints" the run, and risky tools ask a person from then on. `idempotent` tools may be
    run again after a crash; the rest stop and ask a person instead (ADR 0004 §2).
    """

    name: str  # "create_note". BotDesk adds the plugin id: "demo.create_note".
    title: str  # What people read on an approval card: "Create a note".
    description: str  # What the model reads when choosing a tool.
    args_model: type[BaseModel]
    risk: RiskClass
    handler: ToolHandler
    egress: Egress = "fixed"
    idempotent: bool = False
    untrusted_output: bool = False
    # A one-line summary of a call for the approval card ("Send an email to sara@acme.dev").
    # Default: the title.
    summarize: Callable[[Any], str] | None = None

    def summary(self, args: BaseModel) -> str:
        return self.summarize(args) if self.summarize else self.title

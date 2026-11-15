"""TEMPLATE PLUGIN (`botdesk-plugin-template`, plugin id `template`). Copy this folder to start
a plugin; README.md has the rename steps.

Two tools, one per kind you'll usually write:

| Tool | Risk | Shows |
|---|---|---|
| `template.look_up_order` | read | an args model with a described field; runs without asking |
| `template.send_message` | external-send | something leaving: asks a person first, with a clear approval card |

Both are fake (no network), so the template runs anywhere. Replace the bodies with calls to
your service; keep the shapes. Import only `botdesk_plugin_sdk`, the standard library and the
libraries listed in pyproject.toml: CI checks it.
"""

from dataclasses import dataclass, field

from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field

FAKE_ORDERS = {
    "A-1001": {"id": "A-1001", "status": "shipped", "total": "49.00 USD"},
    "A-1002": {"id": "A-1002", "status": "processing", "total": "12.50 USD"},
}


class LookUpOrderArgs(BaseModel):
    """The model reads this schema, so describe every field."""

    order_id: str = Field(min_length=1, max_length=40, description="The order number, e.g. 'A-1001'")


class SendMessageArgs(BaseModel):
    to: str = Field(min_length=1, max_length=80, description="Who gets it: a channel ('#launch') or a person")
    text: str = Field(min_length=1, max_length=2000, description="The message, as it will be sent")


@dataclass
class Outbox:
    """Where the fake `send_message` puts messages. A real plugin calls its service instead."""

    sent: list[dict[str, str]] = field(default_factory=list)


def template_plugin(outbox: Outbox | None = None) -> PluginManifest:
    """The entry point (see pyproject.toml). BotDesk calls it with no arguments; tests pass an
    `Outbox` to look inside. Build state here, not at import time, so each app and test gets
    its own."""
    outbox = outbox or Outbox()

    async def look_up_order(args: LookUpOrderArgs, ctx: ToolContext) -> ToolResult:
        ctx.logger.info("looking up order %s", args.order_id)
        order = FAKE_ORDERS.get(args.order_id)
        return {"found": True, "order": order} if order else {"found": False}

    async def send_message(args: SendMessageArgs, ctx: ToolContext) -> ToolResult:
        # ctx.idempotency_key stays the same when BotDesk retries this call: pass it to services
        # that accept one, so a retry never sends twice.
        outbox.sent.append({"to": args.to, "text": args.text, "idempotencyKey": ctx.idempotency_key})
        return {"sent": True, "to": args.to}

    def summarize_send(args: SendMessageArgs) -> str:
        return f"Send a message to {args.to}"

    return PluginManifest(
        id="template",
        name="Template",
        version="0.1.0",
        description="A starting point for a plugin: look up an order, send a message.",
        tools=(
            ToolSpec(
                name="look_up_order",
                title="Look up an order",
                description="Find an order by its number and return its status and total.",
                args_model=LookUpOrderArgs,
                risk="read",
                handler=look_up_order,
                idempotent=True,  # reading twice does no harm, so it may run again after a crash
            ),
            ToolSpec(
                name="send_message",
                title="Send a message",
                description="Send a short message to a channel or a person.",
                args_model=SendMessageArgs,
                risk="external-send",  # it leaves: a person approves it unless the bot is Autonomous
                handler=send_message,
                summarize=summarize_send,  # the line on the approval card
            ),
        ),
    )

"""The plugin through the SDK's test helpers: no app, no database, no network."""

from pathlib import Path

import pytest
from botdesk_plugin_sdk import validate_manifest
from botdesk_plugin_sdk.project import load_plugin
from botdesk_plugin_sdk.testing import call_tool, make_context
from pydantic import ValidationError

from botdesk_template import Outbox, template_plugin

PROJECT = Path(__file__).parent.parent


def test_the_manifest_is_valid() -> None:
    manifest = validate_manifest(template_plugin())
    assert [(tool.name, tool.risk) for tool in manifest.tools] == [
        ("look_up_order", "read"),
        ("send_message", "external-send"),
    ]


def test_the_entry_point_in_pyproject_finds_this_plugin() -> None:
    # The same lookup BotDesk does, read from pyproject.toml: the entry-point name is the id.
    assert load_plugin(PROJECT).id == "template"


async def test_look_up_order_finds_a_known_order() -> None:
    result = await call_tool(template_plugin(), "look_up_order", {"order_id": "A-1001"})
    assert result == {"found": True, "order": {"id": "A-1001", "status": "shipped", "total": "49.00 USD"}}
    missing = await call_tool(template_plugin(), "look_up_order", {"order_id": "Z-9"})
    assert missing == {"found": False}


async def test_send_message_records_it_with_the_idempotency_key() -> None:
    outbox = Outbox()
    ctx = make_context(tool_call_id="call-1")
    result = await call_tool(template_plugin(outbox), "send_message", {"to": "#launch", "text": "Ship it"}, ctx)
    assert result == {"sent": True, "to": "#launch"}
    assert outbox.sent == [{"to": "#launch", "text": "Ship it", "idempotencyKey": "test:call-1"}]


async def test_bad_arguments_never_reach_the_handler() -> None:
    outbox = Outbox()
    with pytest.raises(ValidationError):
        await call_tool(template_plugin(outbox), "send_message", {"to": "#launch", "text": ""})
    assert outbox.sent == []


def test_the_approval_card_says_what_will_be_sent() -> None:
    (send,) = [tool for tool in template_plugin().tools if tool.name == "send_message"]
    args = send.args_model.model_validate({"to": "#launch", "text": "Ship it"})
    assert send.summary(args) == "Send a message to #launch"

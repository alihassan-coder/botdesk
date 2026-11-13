"""Helpers for testing a plugin without BotDesk: no database, no server, no model.

    result = await call_tool(my_plugin(), "create_note", {"title": "Hi"})

`call_tool` does what the app does before a handler runs (check the manifest, validate the
arguments against the args model), then calls the handler with a throwaway context. It does
not apply the approval policy: that belongs to the app, not to the plugin.
"""

import logging
import uuid
from typing import Any

from botdesk_plugin_sdk.manifest import PluginManifest
from botdesk_plugin_sdk.tool import ToolContext, ToolResult
from botdesk_plugin_sdk.validation import validate_manifest


def make_context(**overrides: Any) -> ToolContext:
    """A `ToolContext` with fresh random ids. Pass any field to fix it (`org_id=...`)."""
    call_id = overrides.pop("tool_call_id", f"test-{uuid.uuid4().hex[:8]}")
    values: dict[str, Any] = {
        "org_id": uuid.uuid4(),
        "bot_id": uuid.uuid4(),
        "run_id": uuid.uuid4(),
        "tool_call_id": call_id,
        "idempotency_key": f"test:{call_id}",
        "logger": logging.getLogger("botdesk.plugins.test"),
    }
    values.update(overrides)
    return ToolContext(**values)


async def call_tool(
    manifest: PluginManifest, tool_name: str, args: dict[str, Any], ctx: ToolContext | None = None
) -> ToolResult:
    """Run one tool the way BotDesk would. Raises `pydantic.ValidationError` for bad arguments."""
    validate_manifest(manifest)
    tool = next((t for t in manifest.tools if t.name == tool_name), None)
    if tool is None:
        raise KeyError(f"Plugin {manifest.id!r} has no tool called {tool_name!r}.")
    parsed = tool.args_model.model_validate(args)
    return await tool.handler(parsed, ctx or make_context())

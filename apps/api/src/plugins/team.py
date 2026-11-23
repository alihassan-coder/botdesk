"""The Team plugin (ADR 0014): one tool, `team.handoff`, that hands a task to a teammate bot.

A core plugin: the server always loads it (it isn't in `PLUGINS`), its id is reserved, and it
isn't listed among the apps people connect (`GET /plugins`). A bot gets it through a binding like
any other plugin, switched on by default, so the bot's Tools tab can switch it off.

The tool never runs through the tool pipeline's `execute`: the graph's `hand_off` node creates the
task, the child run and its job in one transaction (`services/task_service.py`).
"""

from typing import Any

from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolSpec
from pydantic import BaseModel, Field

TEAM_PLUGIN_ID = "team"
HANDOFF_TOOL = "team.handoff"

HANDOFF_DESCRIPTION = (
    "Hand a task to a teammate bot. They do it in this chat with their own tools, and their result comes back "
    "to you before your next step. To hand off several tasks, call this once per task in the same answer. "
    "Use it for work that needs a teammate's skills, tools or accounts; do the rest yourself."
)


class HandoffArgs(BaseModel):
    bot: str = Field(min_length=1, max_length=65, description="The teammate's @handle, like @sales.")
    task: str = Field(
        min_length=1,
        max_length=2000,
        description="What to do, written so it makes sense on its own: the teammate sees this chat, not your thinking.",
    )
    context: str | None = Field(
        default=None, max_length=8000, description="Anything else the teammate needs that isn't in the chat."
    )


def normalise_handle(handle: str) -> str:
    """`@Sales` → `sales`: one leading @ stripped, then lowercased."""
    return handle.strip().removeprefix("@").lower()


async def _never_called(args: Any, ctx: ToolContext) -> dict[str, Any]:
    raise RuntimeError("team.handoff is handled by the graph's hand_off node, never by its handler.")


def manifest() -> PluginManifest:
    return PluginManifest(
        id=TEAM_PLUGIN_ID,
        name="Team",
        version="1.0.0",
        description="Hand tasks to teammate bots in the same chat, and get their results back.",
        tools=(
            ToolSpec(
                name="handoff",
                title="Hand off",
                description=HANDOFF_DESCRIPTION,
                args_model=HandoffArgs,
                risk="write-internal",
                handler=_never_called,
                idempotent=True,
                untrusted_output=False,
            ),
        ),
        auth=None,
    )


def is_team_tool(tool_name: str) -> bool:
    """`team.handoff` and friends: no tool line, no tool events (the handoff card shows them)."""
    return tool_name.split(".", 1)[0] == TEAM_PLUGIN_ID

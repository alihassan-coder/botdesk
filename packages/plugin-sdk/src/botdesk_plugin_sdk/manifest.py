"""The plugin manifest: who a plugin is and which tools it adds.

A manifest is built by code (a function in the plugin package), never hand-written, so the
manifest and the tools can't drift apart. `to_json()` is the stored, diffable form that
consent screens and version checks read.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from botdesk_plugin_sdk.tool import ToolSpec

MANIFEST_VERSION = 1
"""Bumped only when the manifest's shape changes in a way older apps can't read."""

ENTRY_POINT_GROUP = "botdesk.plugins"
"""The Python entry-point group BotDesk looks in. A plugin package registers itself with

    [project.entry-points."botdesk.plugins"]
    my-plugin = "my_package:my_plugin"

where the name is the plugin id and the value is a function that returns a `PluginManifest`.
Being installed is not enough to run: the operator must also list the id in `PLUGINS`."""


@dataclass(frozen=True)
class PluginManifest:
    """A plugin: who it is and the tools it adds."""

    id: str  # "demo", "gmail". Lowercase letters, digits and dashes; same as the entry-point name.
    name: str  # Shown to people: "Gmail".
    version: str  # The plugin's own version, usually the package version.
    description: str
    tools: tuple[ToolSpec, ...] = field(default_factory=tuple)
    runtime: Literal["builtin"] = "builtin"

    def to_json(self) -> dict[str, Any]:
        """The manifest as plain JSON: stored, diffed between versions, shown on consent screens."""
        return {
            "manifestVersion": MANIFEST_VERSION,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "runtime": self.runtime,
            "tools": [
                {
                    "name": tool.name,
                    "title": tool.title,
                    "description": tool.description,
                    "risk": tool.risk,
                    "egress": tool.egress,
                    "idempotent": tool.idempotent,
                    "untrustedOutput": tool.untrusted_output,
                    "inputSchema": tool.args_model.model_json_schema(),
                }
                for tool in self.tools
            ],
        }

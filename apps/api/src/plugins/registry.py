"""The tool registry: every tool from every allowed plugin, under its full name.

Built once at startup from the `PLUGINS` allowlist (ADR 0006: installed never means trusted;
the operator names the plugins, see `loader.py`). Inside BotDesk a tool is `demo.create_note`;
model providers only accept letters, digits, `_` and `-`, so the model sees
`demo__create_note` and the registry maps it back.
"""

from dataclasses import dataclass
from typing import Any

from botdesk_plugin_sdk import PluginManifest, ToolSpec, validate_manifest

from src.plugins.loader import load_plugins

MODEL_NAME_SEPARATOR = "__"


@dataclass(frozen=True)
class RegisteredTool:
    plugin_id: str
    spec: ToolSpec

    @property
    def name(self) -> str:
        return f"{self.plugin_id}.{self.spec.name}"

    @property
    def model_name(self) -> str:
        return f"{self.plugin_id}{MODEL_NAME_SEPARATOR}{self.spec.name}"

    def args_schema(self) -> dict[str, Any]:
        return self.spec.args_model.model_json_schema()

    def for_model(self) -> dict[str, Any]:
        """The tool as an OpenAI-style function definition, which every LangChain chat model's
        `bind_tools` accepts."""
        return {
            "type": "function",
            "function": {
                "name": self.model_name,
                "description": self.spec.description,
                "parameters": self.args_schema(),
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._plugins: dict[str, PluginManifest] = {}

    def register(self, plugin: PluginManifest) -> None:
        """Add a plugin's tools. Raises `ValueError` (a `PluginError` for a bad manifest) and
        changes nothing if the plugin is invalid or clashes with one already registered."""
        validate_manifest(plugin)
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin {plugin.id!r} is already registered.")
        tools = [RegisteredTool(plugin.id, spec) for spec in plugin.tools]
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Tool {tool.name!r} is declared twice.")
        self._plugins[plugin.id] = plugin
        self._tools.update({tool.name: tool for tool in tools})

    def unregister(self, plugin_id: str) -> None:
        """For tests. A running server never unloads code; organizations switch plugins off as data."""
        self._plugins.pop(plugin_id, None)
        self._tools = {name: tool for name, tool in self._tools.items() if tool.plugin_id != plugin_id}

    def get(self, name: str) -> RegisteredTool | None:
        """Find a tool by its full name (`demo.create_note`) or the model's name (`demo__create_note`)."""
        # Exact full name first, so a full name is never rewritten.
        return self._tools.get(name) or self._tools.get(name.replace(MODEL_NAME_SEPARATOR, ".", 1))

    def tools(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def plugins(self) -> list[PluginManifest]:
        return list(self._plugins.values())


def build_registry(plugin_ids: list[str]) -> ToolRegistry:
    """The registry for the allowlisted plugins, found through their entry points.

    A plugin that is installed but broken is skipped (and logged) so one bad plugin can't take
    the API down. An id in `PLUGINS` that no installed package provides is an operator typo, and
    stops startup with a clear message instead of quietly running without the plugin.
    """
    registry = ToolRegistry()
    for manifest in load_plugins(plugin_ids):
        registry.register(manifest)
    return registry

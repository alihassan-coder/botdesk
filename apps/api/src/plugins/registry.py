"""The tool registry: every tool from every allowed plugin, under its full name.

Built once at startup from the `PLUGINS` allowlist (ADR 0006: installed never means trusted;
the operator names the plugins). Inside BotDesk a tool is `demo.create_note`; model
providers only accept letters, digits, `_` and `-`, so the model sees `demo__create_note`
and the registry maps it back.
"""

from dataclasses import dataclass
from typing import Any

from src.plugins.sdk import PluginManifest, ToolSpec

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
        return self._tools.get(name.replace(MODEL_NAME_SEPARATOR, ".", 1))

    def tools(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def plugins(self) -> list[PluginManifest]:
        return list(self._plugins.values())


def build_registry(plugin_ids: list[str]) -> ToolRegistry:
    """The registry for the allowlisted built-in plugins. An unknown id is an operator mistake."""
    from src.plugins import BUILTIN_PLUGINS

    registry = ToolRegistry()
    for plugin_id in plugin_ids:
        if plugin_id not in BUILTIN_PLUGINS:
            raise ValueError(f"PLUGINS names {plugin_id!r}, but there is no such plugin.")
        registry.register(BUILTIN_PLUGINS[plugin_id]())
    return registry

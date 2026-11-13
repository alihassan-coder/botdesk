"""Checks a manifest before BotDesk loads it.

The app runs these at startup and skips a plugin that fails them (with a log line saying
why) instead of crashing. Plugin authors run the same checks in their own tests
(`validate_manifest(my_plugin())`), so a mistake shows up there first.
"""

import inspect
import re

from pydantic import BaseModel

from botdesk_plugin_sdk.manifest import PluginManifest
from botdesk_plugin_sdk.risk import EGRESS_KINDS, RISK_CLASSES
from botdesk_plugin_sdk.tool import ToolSpec

# Ids and names end up inside model tool names (`demo__create_note`), which providers limit to
# letters, digits, `_` and `-`. Plugin ids can't use `_`, so `__` always splits id from name.
PLUGIN_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
# Single underscores only: the model sees `plugin__tool`, so `__` inside a name would be ambiguous.
TOOL_NAME = re.compile(r"^(?=.{1,48}$)[a-z][a-z0-9]*(_[a-z0-9]+)*$")


class PluginError(ValueError):
    """A manifest that BotDesk won't load. `problems` lists every reason, not just the first."""

    def __init__(self, plugin_id: str, problems: list[str]) -> None:
        self.plugin_id = plugin_id
        self.problems = problems
        super().__init__(f"Plugin {plugin_id!r} is invalid: " + "; ".join(problems))


def manifest_problems(manifest: object) -> list[str]:
    """Everything wrong with a manifest, in plain words. Empty when it's fine."""
    if not isinstance(manifest, PluginManifest):
        return [f"expected a PluginManifest, got {type(manifest).__name__}"]

    # A frozen dataclass doesn't check types, so look before touching the fields.
    if not all(isinstance(value, str) for value in (manifest.id, manifest.name, manifest.version)):
        return ["id, name and version must be strings"]
    if not isinstance(manifest.tools, (tuple, list)):
        return ["tools must be a tuple of ToolSpec"]

    problems: list[str] = []
    if not PLUGIN_ID.match(manifest.id):
        problems.append(f"id {manifest.id!r} must be lowercase letters, digits and dashes, starting with a letter")
    if not manifest.name.strip():
        problems.append("name is empty")
    if not manifest.version.strip():
        problems.append("version is empty")
    if not manifest.tools:
        problems.append("it has no tools")

    seen: set[str] = set()
    for tool in manifest.tools:
        if not isinstance(tool, ToolSpec) or not isinstance(tool.name, str):
            problems.append(f"every tool must be a ToolSpec, got {type(tool).__name__}")
            continue
        label = f"tool {tool.name!r}"
        if not TOOL_NAME.match(tool.name):
            problems.append(f"{label}: name must be lowercase letters and digits, single underscores between words")
        if tool.name in seen:
            problems.append(f"{label} is declared twice")
        seen.add(tool.name)
        if not tool.title.strip() or not tool.description.strip():
            problems.append(f"{label}: title and description are required")
        if tool.risk not in RISK_CLASSES:
            problems.append(f"{label}: risk {tool.risk!r} is not one of {', '.join(RISK_CLASSES)}")
        if tool.egress not in EGRESS_KINDS:
            problems.append(f"{label}: egress {tool.egress!r} is not one of {', '.join(EGRESS_KINDS)}")
        if not (isinstance(tool.args_model, type) and issubclass(tool.args_model, BaseModel)):
            problems.append(f"{label}: args_model must be a Pydantic BaseModel class")
        else:
            # The model is shown this schema on every run; a field that can't be described
            # would fail every run on the server, not just this tool.
            try:
                tool.args_model.model_json_schema()
            except Exception as error:
                problems.append(f"{label}: args_model has no JSON schema ({type(error).__name__}: {error})")
        # A blocking handler would stall every other run on the server while it waits.
        if not inspect.iscoroutinefunction(tool.handler):
            problems.append(f"{label}: handler must be an async function")
    return problems


def validate_manifest(manifest: object) -> PluginManifest:
    """Return the manifest if it's valid; raise `PluginError` listing every problem if not."""
    problems = manifest_problems(manifest)
    if problems or not isinstance(manifest, PluginManifest):
        plugin_id = manifest.id if isinstance(manifest, PluginManifest) else "?"
        raise PluginError(plugin_id, problems)
    return manifest

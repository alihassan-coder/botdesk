"""The plugin manifest: who a plugin is and which tools it adds.

A manifest is built by code (a function in the plugin package), never hand-written, so the
manifest and the tools can't drift apart. `to_json()` is the stored, diffable form that
consent screens and version checks read.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from botdesk_plugin_sdk.auth import ApiKeyAuth, Auth, OAuth2Auth
from botdesk_plugin_sdk.tool import ToolSpec
from botdesk_plugin_sdk.trigger import TriggerSpec

MANIFEST_VERSION = 2
"""The shape of `to_json()`. Version 2 added `auth`, `egress`, per-tool `scopes`, `triggers` and
the settings schemas (ADR 0010 §7). Additive: a plugin written for version 1 sets none of them
and loads unchanged."""

ENTRY_POINT_GROUP = "botdesk.plugins"
"""The Python entry-point group BotDesk looks in. A plugin package registers itself with

    [project.entry-points."botdesk.plugins"]
    my-plugin = "my_package:my_plugin"

where the name is the plugin id and the value is a function that returns a `PluginManifest`.
Being installed is not enough to run: the operator must also list the id in `PLUGINS`."""


@dataclass(frozen=True)
class PluginManifest:
    """A plugin: who it is and the tools it adds.

    Version 2 fields, all optional:

    - `auth`: the plugin works on an account (`ApiKeyAuth` or `OAuth2Auth`). None: no account.
    - `egress`: the host names its tools call through `ctx.http` ("gmail.googleapis.com"). BotDesk
      enforces this list: any other host is refused. Required with `auth`.
    - `settings_model` / `bot_settings_model`: Pydantic models for the organization's and each
      bot's settings for this plugin; their JSON Schema drives the settings forms.
    - `triggers`: things in the other app that can start a run.
    """

    id: str  # "demo", "gmail". Lowercase letters, digits and dashes; same as the entry-point name.
    name: str  # Shown to people: "Gmail".
    version: str  # The plugin's own version, usually the package version.
    description: str
    tools: tuple[ToolSpec, ...] = field(default_factory=tuple)
    runtime: Literal["builtin"] = "builtin"
    auth: Auth | None = None
    egress: tuple[str, ...] = ()
    settings_model: type[BaseModel] | None = None
    bot_settings_model: type[BaseModel] | None = None
    triggers: tuple[TriggerSpec, ...] = ()

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
                    "scopes": list(tool.scopes),
                }
                for tool in self.tools
            ],
            "auth": auth_json(self.auth),
            "egress": sorted(self.egress),
            "settingsSchema": self.settings_model.model_json_schema() if self.settings_model else None,
            "botSettingsSchema": self.bot_settings_model.model_json_schema() if self.bot_settings_model else None,
            "triggers": [
                {
                    "name": trigger.name,
                    "title": trigger.title,
                    "description": trigger.description,
                    "intervalSeconds": trigger.interval_seconds,
                    "untrustedPayload": trigger.untrusted_payload,
                }
                for trigger in self.triggers
            ],
        }


def auth_json(auth: Auth | None) -> dict[str, Any] | None:
    """How the plugin's accounts are authorised, without any handler code."""
    if isinstance(auth, ApiKeyAuth):
        return {"type": "api_key", "header": auth.header, "prefix": auth.prefix}
    if isinstance(auth, OAuth2Auth):
        return {
            "type": "oauth2",
            "provider": auth.provider,
            "authorizeUrl": auth.authorize_url,
            "tokenUrl": auth.token_url,
            "revokeUrl": auth.revoke_url,
            "scopeSets": {name: list(scopes) for name, scopes in auth.scope_sets.items()},
            "extraAuthorizeParams": dict(auth.extra_authorize_params),
        }
    return None


def manifest_json(manifest: PluginManifest) -> str:
    """The manifest as the text of a plugin's checked-in `manifest.json`.

    Stable on purpose, so CI can regenerate it and compare: keys sorted, tools sorted by name,
    two-space indent and a final newline. Reordering tools in code doesn't change the file;
    changing what a tool is or does (its risk, its arguments) does.
    """
    data = manifest.to_json()
    data["tools"] = sorted(data["tools"], key=lambda tool: tool["name"])
    data["triggers"] = sorted(data["triggers"], key=lambda trigger: trigger["name"])
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

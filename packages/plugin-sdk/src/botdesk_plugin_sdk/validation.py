"""Checks a manifest before BotDesk loads it.

The app runs these at startup and skips a plugin that fails them (with a log line saying
why) instead of crashing. Plugin authors run the same checks in their own tests
(`validate_manifest(my_plugin())`), so a mistake shows up there first.
"""

import inspect
import re

from pydantic import BaseModel

from botdesk_plugin_sdk.auth import ApiKeyAuth, OAuth2Auth
from botdesk_plugin_sdk.manifest import PluginManifest
from botdesk_plugin_sdk.risk import EGRESS_KINDS, RISK_CLASSES
from botdesk_plugin_sdk.tool import ToolSpec
from botdesk_plugin_sdk.trigger import MIN_INTERVAL_SECONDS, TriggerSpec

# Ids and names end up inside model tool names (`demo__create_note`), which providers limit to
# letters, digits, `_` and `-`. Plugin ids can't use `_`, so `__` always splits id from name.
PLUGIN_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
# Single underscores only: the model sees `plugin__tool`, so `__` inside a name would be ambiguous.
TOOL_NAME = re.compile(r"^(?=.{1,48}$)[a-z][a-z0-9]*(_[a-z0-9]+)*$")
# A plain DNS name with at least one dot: no scheme, port, path, wildcard or upper case. An exact
# list is what `ctx.http` enforces, so it must be something a host name can be compared with.
EGRESS_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")
# An HTTP header name (RFC 9110 token), kept to the usual letters, digits and dashes.
HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")


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
    # A plugin may only connect an account (or offer triggers) before it has tools (Gmail, slice 5.3).
    if not manifest.tools and manifest.auth is None and not manifest.triggers:
        problems.append("it has no tools")
    problems += _v2_problems(manifest)

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
        problems += _scope_problems(manifest, tool, label)
    return problems


def _v2_problems(manifest: PluginManifest) -> list[str]:
    """Manifest version 2: auth, egress, settings models and triggers. All optional."""
    problems: list[str] = []
    auth = manifest.auth
    if auth is not None and not isinstance(auth, (ApiKeyAuth, OAuth2Auth)):
        problems.append(f"auth must be ApiKeyAuth or OAuth2Auth, got {type(auth).__name__}")
    if isinstance(auth, ApiKeyAuth):
        if not isinstance(auth.header, str) or not HEADER_NAME.match(auth.header):
            problems.append(f"auth header {auth.header!r} must be a header name (letters, digits and dashes)")
        if not isinstance(auth.prefix, str) or any(c in auth.prefix for c in "\r\n"):
            problems.append("auth prefix must be one line of text")
    if isinstance(auth, OAuth2Auth):
        problems += _oauth_problems(auth)

    if not isinstance(manifest.egress, (tuple, list)):
        return [*problems, "egress must be a tuple of host names"]
    for host in manifest.egress:
        if not isinstance(host, str) or not EGRESS_HOST.match(host):
            problems.append(
                f"egress host {host!r} must be a lowercase host name like 'api.example.com' (no scheme, port or path)"
            )
    if auth is not None and not manifest.egress:
        problems.append("a plugin with auth must list the hosts it calls in egress")

    for field_name in ("settings_model", "bot_settings_model"):
        model = getattr(manifest, field_name)
        if model is None:
            continue
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            problems.append(f"{field_name} must be a Pydantic BaseModel class")
            continue
        try:
            model.model_json_schema()
        except Exception as error:
            problems.append(f"{field_name} has no JSON schema ({type(error).__name__}: {error})")

    seen: set[str] = set()
    for trigger in manifest.triggers:
        if not isinstance(trigger, TriggerSpec) or not isinstance(trigger.name, str):
            problems.append(f"every trigger must be a TriggerSpec, got {type(trigger).__name__}")
            continue
        label = f"trigger {trigger.name!r}"
        if not TOOL_NAME.match(trigger.name):
            problems.append(f"{label}: name must be lowercase letters and digits, single underscores between words")
        if trigger.name in seen:
            problems.append(f"{label} is declared twice")
        seen.add(trigger.name)
        if not trigger.title.strip() or not trigger.description.strip():
            problems.append(f"{label}: title and description are required")
        if not inspect.iscoroutinefunction(trigger.poll):
            problems.append(f"{label}: poll must be an async function")
        if not isinstance(trigger.interval_seconds, int) or trigger.interval_seconds < MIN_INTERVAL_SECONDS:
            problems.append(f"{label}: interval_seconds must be at least {MIN_INTERVAL_SECONDS}")
    return problems


def _oauth_problems(auth: OAuth2Auth) -> list[str]:
    problems: list[str] = []
    if not isinstance(auth.provider, str) or not PLUGIN_ID.match(auth.provider):
        problems.append(f"auth provider {auth.provider!r} must be lowercase letters, digits and dashes")
    for name in ("authorize_url", "token_url", "revoke_url"):
        url = getattr(auth, name)
        if url is None and name == "revoke_url":
            continue
        if not isinstance(url, str) or not url.startswith("https://"):
            problems.append(f"auth {name} must start with https://")
    if not auth.scope_sets:
        problems.append("auth scope_sets needs at least one access level")
    for level, scopes in auth.scope_sets.items():
        if not isinstance(scopes, tuple) or not scopes or not all(isinstance(s, str) and s for s in scopes):
            problems.append(f"auth scope set {level!r} must be a non-empty tuple of scopes")
    if auth.account is not None and not inspect.iscoroutinefunction(auth.account):
        problems.append("auth account must be an async function")
    return problems


def _scope_problems(manifest: PluginManifest, tool: ToolSpec, label: str) -> list[str]:
    if not isinstance(tool.scopes, tuple) or not all(isinstance(scope, str) for scope in tool.scopes):
        return [f"{label}: scopes must be a tuple of strings"]
    if not tool.scopes:
        return []
    if not isinstance(manifest.auth, OAuth2Auth):
        return [f"{label}: scopes need OAuth2Auth (an API key has no scopes)"]
    known = {scope for scopes in manifest.auth.scope_sets.values() for scope in scopes}
    return [f"{label}: scope {scope!r} is not in any scope set of auth" for scope in tool.scopes if scope not in known]


def validate_manifest(manifest: object) -> PluginManifest:
    """Return the manifest if it's valid; raise `PluginError` listing every problem if not."""
    problems = manifest_problems(manifest)
    if problems or not isinstance(manifest, PluginManifest):
        plugin_id = manifest.id if isinstance(manifest, PluginManifest) else "?"
        raise PluginError(plugin_id, problems)
    return manifest

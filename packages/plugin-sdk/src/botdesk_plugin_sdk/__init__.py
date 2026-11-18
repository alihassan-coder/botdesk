"""The BotDesk plugin SDK: everything a plugin needs, and nothing of the app.

A plugin is a Python package with one function that returns a `PluginManifest` listing its
tools, registered under the `botdesk.plugins` entry-point group. The README has a
five-minute walkthrough; `botdesk_plugin_sdk.testing` runs tools in tests.
"""

from botdesk_plugin_sdk.auth import (
    AccountHandler,
    AccountIdentity,
    ApiKeyAuth,
    Auth,
    ConnectionInfo,
    OAuth2Auth,
    OwnerKind,
)
from botdesk_plugin_sdk.characters import describe_character, hidden_characters, show_hidden
from botdesk_plugin_sdk.http import (
    HostNotAllowed,
    HttpClient,
    HttpError,
    HttpResponse,
    NoHttp,
    NotConnected,
    ResponseTooLarge,
)
from botdesk_plugin_sdk.manifest import ENTRY_POINT_GROUP, MANIFEST_VERSION, PluginManifest, manifest_json
from botdesk_plugin_sdk.outcome import NotDone
from botdesk_plugin_sdk.risk import EGRESS_KINDS, RISK_CLASSES, Egress, RiskClass
from botdesk_plugin_sdk.tool import NoArgs, ToolContext, ToolHandler, ToolResult, ToolSpec
from botdesk_plugin_sdk.trigger import TriggerEvent, TriggerPoll, TriggerPollResult, TriggerSpec
from botdesk_plugin_sdk.validation import PluginError, manifest_problems, validate_manifest

__version__ = "0.1.0"  # x-release-please-version

__all__ = [
    "EGRESS_KINDS",
    "ENTRY_POINT_GROUP",
    "MANIFEST_VERSION",
    "RISK_CLASSES",
    "AccountHandler",
    "AccountIdentity",
    "ApiKeyAuth",
    "Auth",
    "ConnectionInfo",
    "Egress",
    "HostNotAllowed",
    "HttpClient",
    "HttpError",
    "HttpResponse",
    "NoArgs",
    "NoHttp",
    "NotConnected",
    "NotDone",
    "OAuth2Auth",
    "OwnerKind",
    "PluginError",
    "PluginManifest",
    "ResponseTooLarge",
    "RiskClass",
    "ToolContext",
    "ToolHandler",
    "ToolResult",
    "ToolSpec",
    "TriggerEvent",
    "TriggerPoll",
    "TriggerPollResult",
    "TriggerSpec",
    "describe_character",
    "hidden_characters",
    "manifest_json",
    "manifest_problems",
    "show_hidden",
    "validate_manifest",
]

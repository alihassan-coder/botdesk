"""The BotDesk plugin SDK: everything a plugin needs, and nothing of the app.

A plugin is a Python package with one function that returns a `PluginManifest` listing its
tools, registered under the `botdesk.plugins` entry-point group. The README has a
five-minute walkthrough; `botdesk_plugin_sdk.testing` runs tools in tests.
"""

from botdesk_plugin_sdk.manifest import ENTRY_POINT_GROUP, MANIFEST_VERSION, PluginManifest
from botdesk_plugin_sdk.risk import EGRESS_KINDS, RISK_CLASSES, Egress, RiskClass
from botdesk_plugin_sdk.tool import NoArgs, ToolContext, ToolHandler, ToolResult, ToolSpec
from botdesk_plugin_sdk.validation import PluginError, manifest_problems, validate_manifest

__version__ = "0.1.0"

__all__ = [
    "EGRESS_KINDS",
    "ENTRY_POINT_GROUP",
    "MANIFEST_VERSION",
    "RISK_CLASSES",
    "Egress",
    "NoArgs",
    "PluginError",
    "PluginManifest",
    "RiskClass",
    "ToolContext",
    "ToolHandler",
    "ToolResult",
    "ToolSpec",
    "manifest_problems",
    "validate_manifest",
]

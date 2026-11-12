"""The seam between BotDesk and a plugin (agents-and-plugins.md §10.1).

Everything a plugin needs to declare its tools lives here and nowhere else: no database, no
web framework. Build step 3 lifts this file into `packages/plugin-sdk` as it is, so plugins
written against it today keep working.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

RiskClass = Literal[
    "read",
    "write-internal",
    "write-external",
    "external-send",
    "spend",
    "destructive",
    "credential",
]
# Least to most dangerous. The policy table (ADR 0004) uses this order.
RISK_CLASSES: tuple[RiskClass, ...] = (
    "read",
    "write-internal",
    "write-external",
    "external-send",
    "spend",
    "destructive",
    "credential",
)

# `fixed`: always talks to the same service. `open`: can reach any address, so in a tainted
# run it could carry data out in a URL, and counts as `external-send` (§5).
Egress = Literal["fixed", "open"]


@dataclass(frozen=True)
class ToolContext:
    """What a tool gets to work with, and nothing more: no database session, no tokens of
    other organizations. `idempotency_key` is stable across retries of the same call, so a
    tool whose service accepts one (Stripe, for example) can pass it on."""

    org_id: uuid.UUID
    bot_id: uuid.UUID
    run_id: uuid.UUID
    tool_call_id: str
    idempotency_key: str
    logger: logging.Logger


ToolHandler = Callable[[Any, ToolContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    """One thing a bot can do.

    `handler` gets the validated `args_model` instance and returns JSON-friendly data.
    `untrusted_output` marks tools that return outside text (an email body, a web page):
    reading it taints the run. `idempotent` tools may run again after a crash; the rest
    stop and ask a person (ADR 0004 §2).
    """

    name: str  # "create_note"; the registry adds the plugin id: "demo.create_note"
    title: str  # what people read on an approval card: "Create a note"
    description: str  # what the model reads
    args_model: type[BaseModel]
    risk: RiskClass
    handler: ToolHandler
    egress: Egress = "fixed"
    idempotent: bool = False
    untrusted_output: bool = False
    # A one-line summary of a call, for the approval card. Default: the title.
    summarize: Callable[[Any], str] | None = None

    def summary(self, args: BaseModel) -> str:
        return self.summarize(args) if self.summarize else self.title


@dataclass(frozen=True)
class PluginManifest:
    """A plugin: who it is and the tools it adds."""

    id: str  # "demo", "gmail". Lowercase letters, digits and dashes.
    name: str
    version: str
    description: str
    tools: tuple[ToolSpec, ...] = field(default_factory=tuple)
    runtime: Literal["builtin"] = "builtin"

    def to_json(self) -> dict[str, Any]:
        """The manifest as plain JSON: stored, diffed between versions, shown on consent screens."""
        return {
            "manifestVersion": 1,
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

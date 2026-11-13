"""Risk classes and egress: how dangerous a tool is, declared by the plugin author.

BotDesk's policy table (ADR 0004) turns a tool's risk class, the bot's security level and
whether the run has read outside text into "run it", "ask a person" or "refuse". The author
only says what the tool *does*; the app decides what that means.

`RiskClass` is a `Literal`, not an `enum.Enum`, on purpose: plugin code writes plain strings
(`risk="read"`), the strings go straight into JSON manifests and the database, and mypy still
rejects a typo. `RISK_CLASSES` is the runtime list, for checks and for ordering.
"""

from typing import Literal, get_args

RiskClass = Literal[
    "read",  # looks something up, changes nothing
    "write-internal",  # changes something inside BotDesk (a note, a task)
    "write-external",  # a reversible change in another app (a draft, a label)
    "external-send",  # something leaves: an email, a message, a post
    "spend",  # costs money
    "destructive",  # deletes or overwrites, can't be undone
    "credential",  # touches passwords, tokens or keys
]

# Least to most dangerous. The policy table uses this order.
RISK_CLASSES: tuple[RiskClass, ...] = get_args(RiskClass)

Egress = Literal["fixed", "open"]
"""Where a tool's requests can go.

`fixed`: always the same service (Gmail's API). `open`: any address (a "fetch this URL" tool).
An `open` tool could carry data out inside a URL, so in a run that has read untrusted text the
policy treats it as `external-send`, whatever its declared risk.
"""

EGRESS_KINDS: tuple[Egress, ...] = get_args(Egress)

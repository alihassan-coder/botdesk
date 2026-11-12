"""The policy: security level and risk class → auto, ask or deny (ADR 0004 §4 and §5).

A pure function, no database: inputs in, decision out, so a table of cases can test it.
Every decision comes with a trace that says why, e.g.
`level=Ask before acting · risk=external-send · tainted=no → ask`.
"""

from dataclasses import dataclass
from typing import Literal

from src.models.bot import SecurityLevel
from src.plugins.sdk import RISK_CLASSES, Egress, RiskClass

Decision = Literal["auto", "ask", "deny"]

LEVELS: tuple[SecurityLevel, ...] = ("read-only", "ask-before-acting", "autonomous")  # strictest first
LEVEL_NAMES: dict[SecurityLevel, str] = {
    "read-only": "Read only",
    "ask-before-acting": "Ask before acting",
    "autonomous": "Autonomous within limits",
}


def _row(*decisions: Decision) -> dict[RiskClass, Decision]:
    return dict(zip(RISK_CLASSES, decisions, strict=True))


# The table from ADR 0004. Columns: read, write-internal, write-external, external-send,
# spend, destructive, credential.
POLICY: dict[SecurityLevel, dict[RiskClass, Decision]] = {
    "read-only": _row("auto", "auto", "deny", "deny", "deny", "deny", "deny"),
    "ask-before-acting": _row("auto", "auto", "ask", "ask", "ask", "ask", "ask"),
    "autonomous": _row("auto", "auto", "auto", "auto", "ask", "ask", "ask"),
}

# Above this, a tainted run always asks (§5).
_TAINT_FREE: frozenset[RiskClass] = frozenset({"read", "write-internal"})


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    risk: RiskClass  # after taint rules (an open read in a tainted run counts as external-send)
    trace: str


def strictest_level(*levels: SecurityLevel) -> SecurityLevel:
    """The effective level: the strictest of the organization's, the bot's and the routine's."""
    return min(levels, key=LEVELS.index)


def effective_risk(risk: RiskClass, *, egress: Egress, tainted: bool) -> RiskClass:
    """A tool that can reach any address could leak data in the URL, so once the run has read
    outside text an `open` read is treated as sending something out."""
    if tainted and egress == "open" and RISK_CLASSES.index(risk) < RISK_CLASSES.index("external-send"):
        return "external-send"
    return risk


def decide(level: SecurityLevel, risk: RiskClass, *, tainted: bool, egress: Egress = "fixed") -> PolicyDecision:
    """Look up the table, then apply the stricter-only taint rule."""
    risk = effective_risk(risk, egress=egress, tainted=tainted)
    decision = POLICY[level][risk]
    if tainted and decision == "auto" and risk not in _TAINT_FREE:
        decision = "ask"
    trace = f"level={LEVEL_NAMES[level]} · risk={risk} · tainted={'yes' if tainted else 'no'} → {decision}"
    return PolicyDecision(decision=decision, risk=risk, trace=trace)

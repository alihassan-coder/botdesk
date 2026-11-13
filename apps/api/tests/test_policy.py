"""The policy table from ADR 0004, cell by cell, plus the taint rules. Pure: no database."""

import pytest
from botdesk_plugin_sdk import RISK_CLASSES, RiskClass

from src.models.bot import SecurityLevel
from src.runtime.policy import Decision, decide, effective_risk, strictest_level

# Exactly the table in ADR 0004 §4. Columns: read, write-internal, write-external,
# external-send, spend, destructive, credential.
TABLE: dict[SecurityLevel, list[Decision]] = {
    "read-only": ["auto", "auto", "deny", "deny", "deny", "deny", "deny"],
    "ask-before-acting": ["auto", "auto", "ask", "ask", "ask", "ask", "ask"],
    "autonomous": ["auto", "auto", "auto", "auto", "ask", "ask", "ask"],
}
CASES = [(level, risk, decisions[i]) for level, decisions in TABLE.items() for i, risk in enumerate(RISK_CLASSES)]


def test_there_are_seven_risk_classes_in_order() -> None:
    assert RISK_CLASSES == (
        "read",
        "write-internal",
        "write-external",
        "external-send",
        "spend",
        "destructive",
        "credential",
    )


@pytest.mark.parametrize(("level", "risk", "expected"), CASES)
def test_untainted_runs_follow_the_table(level: SecurityLevel, risk: RiskClass, expected: Decision) -> None:
    assert decide(level, risk, tainted=False).decision == expected


# After reading outside text, anything above write-internal asks (or stays denied).
TAINTED: dict[SecurityLevel, list[Decision]] = {
    "read-only": ["auto", "auto", "deny", "deny", "deny", "deny", "deny"],
    "ask-before-acting": ["auto", "auto", "ask", "ask", "ask", "ask", "ask"],
    "autonomous": ["auto", "auto", "ask", "ask", "ask", "ask", "ask"],
}
TAINTED_CASES = [(level, risk, row[i]) for level, row in TAINTED.items() for i, risk in enumerate(RISK_CLASSES)]


@pytest.mark.parametrize(("level", "risk", "expected"), TAINTED_CASES)
def test_tainted_runs_ask_for_anything_above_write_internal(
    level: SecurityLevel, risk: RiskClass, expected: Decision
) -> None:
    assert decide(level, risk, tainted=True).decision == expected


@pytest.mark.parametrize("level", list(TABLE))
@pytest.mark.parametrize("tainted", [False, True])
def test_credential_and_destructive_are_never_automatic(level: SecurityLevel, tainted: bool) -> None:
    assert decide(level, "credential", tainted=tainted).decision != "auto"
    assert decide(level, "destructive", tainted=tainted).decision != "auto"


def test_an_open_read_in_a_tainted_run_counts_as_sending_something_out() -> None:
    assert effective_risk("read", egress="open", tainted=True) == "external-send"
    assert effective_risk("read", egress="open", tainted=False) == "read"
    assert effective_risk("read", egress="fixed", tainted=True) == "read"
    assert effective_risk("destructive", egress="open", tainted=True) == "destructive"  # never lowered
    assert decide("autonomous", "read", tainted=True, egress="open").decision == "ask"


def test_the_trace_says_why() -> None:
    result = decide("autonomous", "external-send", tainted=True)
    assert result.trace == "level=Autonomous within limits · risk=external-send · tainted=yes → ask"


def test_the_effective_level_is_the_strictest() -> None:
    assert strictest_level("autonomous", "ask-before-acting") == "ask-before-acting"
    assert strictest_level("autonomous", "read-only", "ask-before-acting") == "read-only"
    assert strictest_level("autonomous") == "autonomous"

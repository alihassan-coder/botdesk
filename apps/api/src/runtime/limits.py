"""Limits on every run (agents-and-plugins.md §4.2). A run stops with a clear message at any of them."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunLimits:
    max_steps: int
    max_seconds: int


def _duration(seconds: int) -> str:
    minutes = seconds // 60
    if minutes and seconds % 60 == 0:
        return f"{minutes} minute" + ("s" if minutes > 1 else "")
    return f"{seconds} seconds"


def time_limit_message(max_seconds: int) -> str:
    return f"This run reached its time limit of {_duration(max_seconds)}."


def limit_reached(limits: RunLimits, *, steps_used: int, elapsed_seconds: float) -> str | None:
    """Checked before each model call. Returns why the run must stop, or None to carry on."""
    if steps_used >= limits.max_steps:
        return f"This run reached its limit of {limits.max_steps} model steps."
    if elapsed_seconds > limits.max_seconds:
        return time_limit_message(limits.max_seconds)
    return None

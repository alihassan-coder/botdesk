"""How a tool that failed says it changed nothing (ADR 0004 §2).

A tool that isn't `idempotent` and changes something outside BotDesk (an email, a payment) must
never run twice. When such a call fails, BotDesk has to know whether it may still have happened:

- A plugin that declares `egress` reaches other apps only through `ctx.http`, so BotDesk sees
  every request it makes. If none that could change something (anything but GET, HEAD or
  OPTIONS) may have reached the other app, the call failed cleanly. A 4xx answer is a refusal,
  and a request that never connected never left; a 5xx, a dropped connection or a timeout after
  the request was sent may have been acted on.
- Anything else (a plugin with no `egress`, or a timeout BotDesk can't place) counts as "may have
  happened" unless the tool raised `NotDone`.

A call that may have happened isn't reported to the model as failed (it would try again): the run
stops, and a person checks.
"""


class NotDone(Exception):
    """Raise this (or a subclass) from a tool when it stopped before changing anything: a check
    failed, the other app refused, nothing was sent. The message is shown to the model and to
    people. BotDesk then marks the call failed and the model may try again; any other exception
    from a tool that isn't idempotent stops the run for a person, because it may have half
    happened. `ctx.http` raises `HostNotAllowed` and `NotConnected` (both `NotDone`) before a
    request leaves."""

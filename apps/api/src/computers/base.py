"""What BotDesk needs from a cloud computer provider (ADR 0020 §1): make, start, stop and delete a
bot's computer, run shell commands on it, see its screen, click and type for people taking over,
long-running apps, and preview links. Orgo is the first (`orgo.py`); another provider is another
class with these methods.

Errors say what happened in words for people and bots, and never hold the organization's key:
- `ComputerError` (a `NotDone`): the provider refused or couldn't be reached, nothing happened.
- `MayHaveRun`: a command was sent and its answer was lost (a timeout, a dropped connection, a
  server error), so it may have run. Not a `NotDone` on purpose: the tool pipeline then stops a
  `computer.run` for a person instead of letting the model run it again (ADR 0004 §2).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from botdesk_plugin_sdk import NotDone

# BotDesk's own words for where a computer is; a provider's are mapped onto these.
ComputerStatus = Literal["creating", "starting", "running", "stopping", "stopped", "error"]


class ComputerError(NotDone):
    """The provider refused or failed, and nothing happened. The message is for people and bots."""

    code = "failed"


class KeyRefused(ComputerError):
    code = "key_refused"


class OutOfCredit(ComputerError):
    code = "out_of_credit"


class NotAllowed(ComputerError):
    code = "not_allowed"


class Gone(ComputerError):
    """The computer isn't at the provider any more (deleted there): BotDesk forgets it."""

    code = "gone"


class Busy(ComputerError):
    """Another operation holds the computer (starting, stopping, waking): try again shortly."""

    code = "busy"


class NotRunning(ComputerError):
    """The computer must be started before it can do that."""

    code = "not_running"


class NameTaken(ComputerError):
    code = "name_taken"


class RateLimited(ComputerError):
    code = "rate_limited"


class NoRoom(ComputerError):
    code = "no_room"


class Unreachable(ComputerError):
    code = "unreachable"


class MayHaveRun(Exception):  # a state, like NotDone
    """A command was sent and its answer was lost: it may have run. The message is for people."""


@dataclass(frozen=True)
class RemoteComputer:
    """A computer as the provider describes it, field by field (never the provider's whole answer:
    Orgo's holds the machine's root password and raw address)."""

    id: str
    name: str
    status: ComputerStatus | Literal["gone"]
    cpu: float | None = None
    ram: int | None = None
    region: str | None = None


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str


@dataclass(frozen=True)
class App:
    """A long-running process the provider keeps going (Orgo's "services")."""

    id: str
    name: str
    port: int | None
    status: str


@dataclass(frozen=True)
class Preview:
    """A web address for a port on the computer."""

    id: str
    url: str
    port: int
    access: str  # Orgo: team (people in the workspace) | people | link (anyone with it)


class ComputerProvider(Protocol):
    provider: str

    async def check(self) -> None:
        """The key works: `KeyRefused` (or another `ComputerError`) when it doesn't."""
        ...

    async def workspace(self, name: str) -> str:
        """The id of the provider's workspace with this name, made if there's none."""
        ...

    async def create(self, *, workspace_id: str, name: str, idempotency_key: str) -> RemoteComputer: ...
    async def get(self, remote_id: str) -> RemoteComputer: ...
    async def start(self, remote_id: str) -> None: ...
    async def stop(self, remote_id: str) -> None: ...
    async def delete(self, remote_id: str) -> None: ...
    async def bash(self, remote_id: str, command: str, *, seconds: int) -> CommandResult: ...
    async def screenshot(self, remote_id: str, *, image: Literal["jpeg", "png"], quality: int = 80) -> bytes: ...
    async def click(
        self, remote_id: str, x: int, y: int, *, button: Literal["left", "right"], double: bool
    ) -> None: ...
    async def type(self, remote_id: str, text: str) -> None: ...
    async def key(self, remote_id: str, key: str) -> None: ...
    async def scroll(
        self, remote_id: str, x: int, y: int, *, direction: Literal["up", "down"], amount: int
    ) -> None: ...
    async def apps(self, remote_id: str) -> list[App]: ...
    async def add_app(
        self, remote_id: str, *, name: str, command: str, cwd: str | None, port: int | None, restart: str
    ) -> App: ...
    async def app_logs(self, remote_id: str, app_id: str, *, lines: int) -> str: ...
    async def delete_app(self, remote_id: str, app_id: str) -> None: ...
    async def previews(self, remote_id: str) -> list[Preview]: ...
    async def add_preview(self, remote_id: str, port: int) -> Preview: ...

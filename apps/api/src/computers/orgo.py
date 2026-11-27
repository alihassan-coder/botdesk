"""Orgo (https://www.orgo.ai): cloud computers with a REST API (docs/research/orgo-api.md).

Every call goes to Orgo's fixed address (`Settings.orgo_api_url`) with `Authorization: Bearer
<the organization's key>`, never follows a redirect, and reads its answer field by field: a
computer's JSON holds its root (VNC) password and raw address, which never leave this module.
Errors are BotDesk's own words (ADR 0020 §6), plus Orgo's short `error` text where it explains a
refusal, with the key scrubbed out in case it was ever echoed.
"""

import base64
import contextlib
import re
from typing import Any, Literal

import httpx

from src.computers.base import (
    App,
    Busy,
    CommandResult,
    ComputerError,
    ComputerStatus,
    Gone,
    KeyRefused,
    MayHaveRun,
    NameTaken,
    NoRoom,
    NotAllowed,
    NotRunning,
    NotThere,
    OutOfCredit,
    Preview,
    RateLimited,
    RemoteComputer,
    Unreachable,
)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
OS, CPU, RAM = "linux", 2, 8
MODEL_ID = "orgo:linux-2cpu-8gb"  # how its time shows in usage

KEY_REFUSED = "Orgo refused the organization's key. An owner or admin can check it in Settings → Computers."
OUT_OF_CREDIT = "Orgo says the account is out of credit. An owner or admin can add credit at orgo.ai, then try again."
NO_ROOM = "Orgo has no room for a computer right now. Try again later."
GONE = "The computer isn't at Orgo any more."
RATE_LIMITED = "Orgo says that's too many requests for now. Try again in a minute."
UNREACHABLE = "BotDesk couldn't reach Orgo. Try again in a moment."
NOT_REACHABLE_NOW = "Orgo couldn't reach the computer just now. Try again in a moment."
NOT_RUNNING = "The computer isn't running."
NO_APPS = "Orgo can't keep apps on this computer."
NO_SUCH_APP = "Orgo has no such app on the computer (it may have been removed)."
NO_LINKS = "Orgo says this account can't make preview links for this computer."
ANSWER_LOST = (
    "The command was sent to the computer, but its answer was lost ({why}), so it may have run. "
    "Check on the computer before running it again."
)

# Orgo's words for a computer's state → BotDesk's (ADR 0020 §3).
_STATUSES: dict[str, ComputerStatus | Literal["gone"]] = {
    "running": "running",
    "creating": "starting",
    "starting": "starting",
    "restarting": "starting",
    "resuming": "starting",
    "updating": "starting",
    "provisioning": "starting",
    "pending": "starting",
    "stopping": "stopping",
    "suspending": "stopping",
    "stopped": "stopped",
    "suspended": "stopped",
    "frozen": "stopped",
    "asleep": "stopped",
    "error": "error",
    "failed": "error",
    "deleted": "gone",
}
_NOT_RUNNING_CODES = {"resume_required", "COMPUTER_NOT_RUNNING", "computer_not_running"}
# making it (a lost answer may have made it) | starting it | anything else | a shell command
Doing = Literal["create", "make", "act", "run"]


class OrgoComputers:
    provider = "orgo"

    def __init__(self, api_key: str, *, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._key = api_key
        self._base = base_url
        self._transport = transport

    def __repr__(self) -> str:  # never the key
        return f"OrgoComputers({self._base!r})"

    # The account

    async def check(self) -> None:
        await self._call("GET", "/me")

    async def workspace(self, name: str) -> str:
        found = _workspace_named(await self._json("GET", "/workspaces"), name)
        if found:
            return found
        try:
            made = await self._json("POST", "/workspaces", body={"name": name})
        except ComputerError:
            # Made meanwhile (WORKSPACE_NAME_TAKEN): it's there now.
            found = _workspace_named(await self._json("GET", "/workspaces"), name)
            if found:
                return found
            raise
        workspace_id = _text(made, "id") or _text(made.get("workspace") if isinstance(made, dict) else None, "id")
        if not workspace_id:
            raise ComputerError("Orgo made the workspace but didn't say its id. Try again.")
        return workspace_id

    # A computer

    async def create(self, *, workspace_id: str, name: str, idempotency_key: str) -> RemoteComputer:
        body = {"workspace_id": workspace_id, "name": name, "os": OS, "ram": RAM, "cpu": CPU}
        answer = await self._json(
            "POST", "/computers", body=body, headers={"Idempotency-Key": idempotency_key}, doing="create"
        )
        computer = _computer(answer.get("computer") if isinstance(answer, dict) and "id" not in answer else answer)
        if computer is None:
            raise ComputerError("Orgo made the computer but didn't say its id. Try again.")
        return computer

    async def get(self, remote_id: str) -> RemoteComputer:
        computer = _computer(await self._json("GET", f"/computers/{remote_id}"))
        if computer is None:
            raise ComputerError("Orgo answered without the computer.")
        return computer

    async def start(self, remote_id: str) -> None:
        await self._call("POST", f"/computers/{remote_id}/start", body={"async": True}, doing="make")

    async def stop(self, remote_id: str) -> None:
        await self._call("POST", f"/computers/{remote_id}/stop", body={"async": True})

    async def delete(self, remote_id: str) -> None:
        with contextlib.suppress(Gone):  # already gone
            await self._call("DELETE", f"/computers/{remote_id}")

    async def bash(self, remote_id: str, command: str, *, seconds: int) -> CommandResult:
        answer = await self._json(
            "POST",
            f"/computers/{remote_id}/bash",
            body={"command": command, "timeout": seconds},
            limits=httpx.Timeout(seconds + 30.0, connect=10.0),
            doing="run",
        )
        output = answer.get("output") if isinstance(answer, dict) else None
        exit_code = answer.get("exit_code") if isinstance(answer, dict) else None
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            exit_code = 0 if isinstance(answer, dict) and answer.get("success") is True else 1
        return CommandResult(exit_code=exit_code, output=output if isinstance(output, str) else "")

    # Its screen

    async def screenshot(self, remote_id: str, *, image: Literal["jpeg", "png"], quality: int = 80) -> bytes:
        params: dict[str, str | int] = {"response_format": "binary", "format": image}
        if image == "jpeg":
            params["quality"] = quality
        response = await self._call("GET", f"/computers/{remote_id}/screenshot", params=params)
        if response.headers.get("content-type", "").startswith("image/"):
            return response.content
        answer = _json_of(response)  # an older answer: base64 inline
        picture = _text(answer, "image").split(",", 1)[-1]
        try:
            return base64.b64decode(picture, validate=True) if picture else b""
        except ValueError:
            raise ComputerError("Orgo's screenshot couldn't be read.") from None

    async def click(self, remote_id: str, x: int, y: int, *, button: Literal["left", "right"], double: bool) -> None:
        body = {"x": x, "y": y, "button": button, "double": double}
        await self._call("POST", f"/computers/{remote_id}/click", body=body)

    async def type(self, remote_id: str, text: str) -> None:
        await self._call("POST", f"/computers/{remote_id}/type", body={"text": text})

    async def key(self, remote_id: str, key: str) -> None:
        await self._call("POST", f"/computers/{remote_id}/key", body={"key": key})

    async def scroll(self, remote_id: str, x: int, y: int, *, direction: Literal["up", "down"], amount: int) -> None:
        body = {"x": x, "y": y, "direction": direction, "amount": amount}
        await self._call("POST", f"/computers/{remote_id}/scroll", body=body)

    # Apps (Orgo's services) and preview links (its public URLs)

    async def apps(self, remote_id: str) -> list[App]:
        answer = await self._json("GET", f"/computers/{remote_id}/services", missing=NO_APPS)
        items = answer.get("services") if isinstance(answer, dict) else None
        return [app for item in items or [] if (app := _app(item)) is not None]

    async def add_app(
        self, remote_id: str, *, name: str, command: str, cwd: str | None, port: int | None, restart: str
    ) -> App:
        body: dict[str, Any] = {"name": name, "command": command, "restart": restart}
        if cwd:
            body["cwd"] = cwd
        if port is not None:
            body["port"] = port
        app = _app(await self._json("POST", f"/computers/{remote_id}/services", body=body, missing=NO_APPS))
        if app is None:
            raise ComputerError("Orgo added the app but didn't describe it. List the apps to check.")
        return app

    async def app_logs(self, remote_id: str, app_id: str, *, lines: int) -> str:
        answer = await self._json(
            "GET", f"/computers/{remote_id}/services/{app_id}/logs", params={"lines": lines}, missing=NO_SUCH_APP
        )
        return _text(answer, "log")

    async def delete_app(self, remote_id: str, app_id: str) -> None:
        await self._call("DELETE", f"/computers/{remote_id}/services/{app_id}", missing=NO_SUCH_APP)

    async def previews(self, remote_id: str) -> list[Preview]:
        answer = await self._json("GET", f"/computers/{remote_id}/public-urls", missing=NO_LINKS)
        items = answer.get("public_urls") if isinstance(answer, dict) else None
        return [preview for item in items or [] if (preview := _preview(item)) is not None]

    async def add_preview(self, remote_id: str, port: int) -> Preview:
        preview = _preview(
            await self._json("POST", f"/computers/{remote_id}/public-urls", body={"port": port}, missing=NO_LINKS)
        )
        if preview is None:
            raise ComputerError("Orgo made the link but didn't say its address. Try again.")
        return preview

    # Calls

    async def _json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        limits: httpx.Timeout = TIMEOUT,
        doing: Doing = "act",
        missing: str = "",
    ) -> Any:
        response = await self._call(
            method, path, body=body, params=params, headers=headers, limits=limits, doing=doing, missing=missing
        )
        return _json_of(response)

    async def _call(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        limits: httpx.Timeout = TIMEOUT,
        doing: Doing = "act",
        missing: str = "",
    ) -> httpx.Response:
        """`missing`: what a 404 means for something on the computer (an app, a link). Without it
        the call is about the computer itself, and a 404 means the computer is gone."""
        try:
            async with httpx.AsyncClient(
                base_url=self._base,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=limits,
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, json=body, params=params, headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise Unreachable(UNREACHABLE) from None  # it never left
        except httpx.HTTPError as error:
            if doing in ("run", "create"):
                raise MayHaveRun(ANSWER_LOST.format(why=_why(error))) from None
            raise Unreachable(UNREACHABLE) from None
        if response.is_success:
            return response
        raise _refusal(response, doing, missing)


def _refusal(response: httpx.Response, doing: Doing, missing: str) -> Exception:
    """BotDesk's own words, plus Orgo's error code when it has one (a fixed name like
    workspace_read_only). Never Orgo's free text: it could repeat what was sent (a command), and a
    tool's failure reaches the model as BotDesk's own words."""
    status = response.status_code
    code = _code(response)
    because = f" ({code})" if code else ""
    if status == 401:
        return KeyRefused(KEY_REFUSED)
    if status == 402:
        return OutOfCredit(OUT_OF_CREDIT)
    if status == 403:
        return NotAllowed(f"Orgo didn't allow that{because}.")
    if status == 404:
        return NotThere(missing) if missing else Gone(GONE)
    if status == 409:
        if code in _NOT_RUNNING_CODES:
            return NotRunning(NOT_RUNNING)
        if code == "NAME_TAKEN":
            return NameTaken("That name is taken at Orgo.")
        return Busy(f"Orgo says the computer is busy{because}. Try again in a moment.")
    if status == 429:
        return RateLimited(RATE_LIMITED)
    if status == 503:
        return NoRoom(NO_ROOM) if doing in ("create", "make") else Unreachable(NOT_REACHABLE_NOW)
    if status == 400:
        said = _text(_json_of(response, quiet=True), "error").lower()
        if "not available" in said or "no vm" in said:
            return NotRunning(NOT_RUNNING)
        return ComputerError(f"Orgo refused that{because}.")
    if doing in ("run", "create"):  # it may have been done before failing
        return MayHaveRun(ANSWER_LOST.format(why=f"Orgo answered {status}"))
    return ComputerError(f"Orgo couldn't do that (it answered {status}).")


def _json_of(response: httpx.Response, *, quiet: bool = False) -> Any:
    try:
        return response.json() if response.content else {}
    except ValueError:
        if quiet:
            return {}
        raise ComputerError("Orgo's answer couldn't be read.") from None


def _code(response: httpx.Response) -> str:
    """Orgo's error code, when it is one (letters, digits and _ only, at most 60)."""
    code = _text(_json_of(response, quiet=True), "code")
    return code if re.fullmatch(r"[A-Za-z0-9_]{1,60}", code) else ""


def _why(error: httpx.HTTPError) -> str:
    return "it took too long" if isinstance(error, httpx.TimeoutException) else "the connection dropped"


def _text(body: Any, name: str) -> str:
    value = body.get(name) if isinstance(body, dict) else None
    return value if isinstance(value, str) else ""


def _number(body: dict[str, Any], name: str) -> float | None:
    value = body.get(name)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _workspace_named(answer: Any, name: str) -> str:
    items = answer.get("workspaces", answer.get("projects")) if isinstance(answer, dict) else answer
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("name") == name and _text(item, "id"):
            return _text(item, "id")
    return ""


def _computer(body: Any) -> RemoteComputer | None:
    """Only these fields: never the password, the address or anything else Orgo sends."""
    if not isinstance(body, dict) or not _text(body, "id"):
        return None
    ram = _number(body, "ram")
    return RemoteComputer(
        id=_text(body, "id"),
        name=_text(body, "name"),
        status=_STATUSES.get(_text(body, "status").lower(), "starting"),
        cpu=_number(body, "cpu"),
        ram=int(ram) if ram is not None else None,
        region=_text(body, "region") or None,
    )


def _app(body: Any) -> App | None:
    if not isinstance(body, dict) or not _text(body, "id"):
        return None
    port = body.get("port")
    return App(
        id=_text(body, "id"),
        name=_text(body, "name"),
        port=port if isinstance(port, int) and not isinstance(port, bool) else None,
        status=_text(body, "status") or "unknown",
    )


def _preview(body: Any) -> Preview | None:
    if not isinstance(body, dict) or not _text(body, "url"):
        return None
    port = body.get("port")
    return Preview(
        id=_text(body, "id"),
        url=_text(body, "url"),
        port=port if isinstance(port, int) and not isinstance(port, bool) else 0,
        access=_text(body, "access") or "team",
    )

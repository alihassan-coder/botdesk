"""The Computer plugin's `ComputerAccess` (ADR 0020 §4): each tool makes sure the bot's computer is
running (made or started on demand, `Computers.ensure_running`), does its work through the
provider, and keeps the computer from its idle stop.

Refusals raise `NotDone` (a `ComputerError`, or a refused `computer.inspect` command): nothing
happened, and the bot may try again differently. A command whose answer was lost raises
`MayHaveRun`, so the tool pipeline stops a `computer.run` for a person. Screenshots and
downloads go to the bot's Files through the same service as people's uploads.
"""

import base64
import posixpath
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from botdesk_plugin_sdk import NotDone, ToolContext, ToolResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.computers import commands
from src.computers.base import App, ComputerError, Gone, NotRunning
from src.core.config import Settings
from src.core.errors import AppError
from src.models import Bot
from src.services import file_service, storage_service
from src.services.computer_service import GONE_NOW, Computers, Ready
from src.services.credential_vault import CredentialVault

OUTPUT_PART = 8 * 1024  # bytes of a command's output kept from its start, and from its end
LOG_PART = 16 * 1024
INSPECT_TIMEOUT = 60
QUICK_TIMEOUT = 30
MAX_TRANSFER = 10 * 1024 * 1024
UPLOAD_CHUNK = 96_000  # base64 characters per command: well under Linux's 128 KB for one argument
DOWNLOAD_CHUNK = 768 * 1024  # bytes per command (about 1 MB of base64 back)
TOO_BIG = "{what} is {size:.1f} MB; files up to 10 MB are copied."


class ComputerTools:
    def __init__(
        self,
        computers: Computers,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        vault: CredentialVault,
    ) -> None:
        self._computers = computers
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._vault = vault

    # Commands

    async def inspect(self, ctx: ToolContext, *, command: str, cwd: str) -> ToolResult:
        refusal = commands.check(command)
        if refusal:
            raise NotDone(refusal)
        return await self._shell(ctx, command, cwd, INSPECT_TIMEOUT)

    async def run(self, ctx: ToolContext, *, command: str, cwd: str, seconds: int) -> ToolResult:
        return await self._shell(ctx, command, cwd, seconds)

    async def _shell(self, ctx: ToolContext, command: str, cwd: str, seconds: int) -> ToolResult:
        script = f"{_cd(cwd)} || exit 1\n{command}" if cwd.strip() else command

        async def work(ready: Ready) -> ToolResult:
            began = time.monotonic()
            done = await ready.provider.bash(ready.remote_id, script, seconds=seconds)
            return {
                "exitCode": done.exit_code,
                "output": cut(done.output, OUTPUT_PART),
                "seconds": round(time.monotonic() - began, 1),
                "cwd": cwd.strip() or "~",
            }

        return await self._on(ctx, work)

    # Apps and preview links

    async def start_app(self, ctx: ToolContext, *, name: str, command: str, cwd: str, port: int | None) -> ToolResult:
        async def work(ready: Ready) -> ToolResult:
            old = _named(await ready.provider.apps(ready.remote_id), name)
            if old is not None:  # the same name again replaces it
                await ready.provider.delete_app(ready.remote_id, old.id)
            app = await ready.provider.add_app(
                ready.remote_id, name=name, command=command, cwd=cwd.strip() or None, port=port, restart="on-failure"
            )
            then = "Read its output with computer.app_logs"
            if port is not None:
                then += f"; make a link with computer.preview (port {port}; it must listen on 0.0.0.0)"
            return {"name": app.name, "port": app.port, "status": app.status, "note": f"{then}."}

        return await self._on(ctx, work)

    async def app_logs(self, ctx: ToolContext, *, name: str, lines: int) -> ToolResult:
        async def work(ready: Ready) -> ToolResult:
            app = await self._app(ready, name)
            log = await ready.provider.app_logs(ready.remote_id, app.id, lines=lines)
            return {"name": app.name, "status": app.status, "log": cut(log, LOG_PART // 2)}

        return await self._on(ctx, work)

    async def stop_app(self, ctx: ToolContext, *, name: str) -> ToolResult:
        async def work(ready: Ready) -> ToolResult:
            app = await self._app(ready, name)
            await ready.provider.delete_app(ready.remote_id, app.id)
            return {"stopped": app.name}

        return await self._on(ctx, work)

    async def preview(self, ctx: ToolContext, *, port: int) -> ToolResult:
        async def work(ready: Ready) -> ToolResult:
            made = next((p for p in await ready.provider.previews(ready.remote_id) if p.port == port), None)
            preview = made or await ready.provider.add_preview(ready.remote_id, port)
            who = (
                "anyone with the link"
                if preview.access == "link"
                else "people in the organization's Orgo workspace (they sign in to Orgo)"
            )
            return {
                "url": preview.url,
                "port": preview.port,
                "access": preview.access,
                "note": f"It opens for {who}. Share it in the chat; the app must listen on 0.0.0.0:{port}.",
            }

        return await self._on(ctx, work)

    async def open(self, ctx: ToolContext, *, url: str) -> ToolResult:
        address = shlex.quote(url.strip())
        script = (
            "export DISPLAY=:0\n"
            "if command -v xdg-open >/dev/null 2>&1; then opener=xdg-open; else opener=firefox; fi\n"
            f'setsid "$opener" {address} >/dev/null 2>&1 &'
        )

        async def work(ready: Ready) -> ToolResult:
            done = await ready.provider.bash(ready.remote_id, script, seconds=QUICK_TIMEOUT)
            if done.exit_code != 0:
                raise NotDone(f"The browser didn't open: {cut(done.output, 500)}")
            return {"opened": url.strip(), "note": "People watching your screen see it. Its page isn't read back."}

        return await self._on(ctx, work)

    # The screen and files

    async def screenshot(self, ctx: ToolContext) -> ToolResult:
        async def work(ready: Ready) -> bytes:
            return await ready.provider.screenshot(ready.remote_id, image="png")

        picture, note = await self._on_computer(ctx, work)
        path = f"screenshots/computer-{datetime.now(UTC):%Y-%m-%d-%H%M%S}.png"
        saved = await self._save(ctx, path, picture, "image/png")
        return {**saved, "computer": note} if note else saved

    async def upload(self, ctx: ToolContext, *, path: str, shared: bool, to: str) -> ToolResult:
        data, clean = await self._read_file(ctx, path, shared)
        target = to.strip() or f"~/{posixpath.basename(clean)}"
        encoded = base64.b64encode(data).decode("ascii")
        spool = f"/tmp/botdesk-upload-{uuid.uuid4().hex}.b64"  # noqa: S108  # on the bot's own computer
        place = _shell_path(target)

        async def work(ready: Ready) -> ToolResult:
            await self._bash_ok(ready, f": > {spool}")
            for start in range(0, len(encoded), UPLOAD_CHUNK):
                await self._bash_ok(ready, f"printf %s {encoded[start : start + UPLOAD_CHUNK]} >> {spool}")
            folder = f'"$(dirname -- {place})"'
            written = await self._bash_ok(
                ready, f"mkdir -p -- {folder} && base64 -d {spool} > {place} && rm -f {spool} && wc -c < {place}"
            )
            return {"uploaded": clean, "to": target, "size": _int(written, len(data))}

        return await self._on(ctx, work)

    async def download(self, ctx: ToolContext, *, path: str, to: str) -> ToolResult:
        place = _shell_path(path.strip())

        async def work(ready: Ready) -> bytes:
            size = _int(await self._bash_ok(ready, f"stat -c %s -- {place}", missing=path), -1)
            if size < 0:
                raise NotDone(f"There's no file at {path} on your computer.")
            if size > MAX_TRANSFER:
                raise NotDone(TOO_BIG.format(what=path, size=size / 1024 / 1024))
            parts = []
            for index in range((size + DOWNLOAD_CHUNK - 1) // DOWNLOAD_CHUNK):
                chunk = await self._bash_ok(
                    ready, f"dd if={place} bs={DOWNLOAD_CHUNK} skip={index} count=1 status=none | base64 -w0"
                )
                try:
                    parts.append(base64.b64decode(chunk.strip(), validate=True))
                except ValueError:
                    raise NotDone("The file couldn't be read from the computer. Try again.") from None
            return b"".join(parts)

        data, note = await self._on_computer(ctx, work)
        target = to.strip() or f"downloads/{posixpath.basename(path.strip().rstrip('/')) or 'file'}"
        saved = await self._save(ctx, target, data, None)
        return {**saved, "note": "Read it with files.read.", **({"computer": note} if note else {})}

    # Helpers

    async def _on(self, ctx: ToolContext, work: Callable[[Ready], Awaitable[ToolResult]]) -> ToolResult:
        result, note = await self._on_computer(ctx, work)
        return {**result, "computer": note} if note else result

    async def _on_computer[T](self, ctx: ToolContext, work: Callable[[Ready], Awaitable[T]]) -> tuple[T, str | None]:
        """`work` on the bot's running computer, and a note for the bot when it's a new one (the
        old one was gone). Orgo saying it isn't running (stopped outside BotDesk) starts it and
        tries once more; a computer gone at Orgo is forgotten."""
        computers = self._computers
        for attempt in (1, 2):
            try:
                async with computers.watching(ctx.org_id):
                    ready = await computers.ensure_running(ctx.org_id, ctx.bot_id)
                    try:
                        result = await work(ready)
                    finally:
                        await computers.touch(ctx.bot_id, force=True)
                return result, ready.note
            except NotRunning:
                if attempt == 2:
                    raise
                await computers.mark_stopped(ctx.bot_id)
            except Gone:
                await computers.forget_gone(ctx.bot_id)
                raise ComputerError(GONE_NOW) from None
        raise AssertionError("unreachable")  # pragma: no cover

    async def _bash_ok(self, ready: Ready, script: str, *, missing: str = "") -> str:
        """A helper command of BotDesk's own; its failure is a refusal (nothing to undo)."""
        done = await ready.provider.bash(ready.remote_id, script, seconds=QUICK_TIMEOUT * 2)
        if done.exit_code != 0:
            if missing:
                return ""
            raise NotDone(f"The copy failed on the computer: {cut(done.output, 500) or f'exit {done.exit_code}'}")
        return done.output

    async def _app(self, ready: Ready, name: str) -> App:
        app = _named(await ready.provider.apps(ready.remote_id), name)
        if app is None:
            raise NotDone(f"There's no app called {name}. Start it with computer.start_app.")
        return app

    async def _read_file(self, ctx: ToolContext, path: str, shared: bool) -> tuple[bytes, str]:
        async with self._sessionmaker() as db:
            bot = await self._bot(db, ctx)
            try:
                clean = file_service.clean_path(path)
                file = await file_service.find_by_path(db, ctx.org_id, None if shared else bot.id, clean)
                if file is None:
                    where = "the shared folder" if shared else "your Files"
                    raise NotDone(f"There's no file called {clean} in {where}. List them with files.list.")
                if file.size_bytes > MAX_TRANSFER:
                    raise NotDone(TOO_BIG.format(what=clean, size=file.size_bytes / 1024 / 1024))
                row = await storage_service.find(db, ctx.org_id)
                storage = await storage_service.open_storage(row, ctx.org_id, self._settings, self._vault)
                return await file_service.read(storage, file), clean
            except AppError as error:
                raise NotDone(error.message) from None

    async def _save(self, ctx: ToolContext, path: str, data: bytes, content_type: str | None) -> ToolResult:
        """Into the bot's own Files, by the same rules as everything saved there."""
        async with self._sessionmaker() as db:
            bot = await self._bot(db, ctx)
            try:
                row = await storage_service.find(db, ctx.org_id)
                storage = await storage_service.open_storage(row, ctx.org_id, self._settings, self._vault)
                file = await file_service.save(
                    db,
                    storage,
                    org_id=ctx.org_id,
                    bot=bot,
                    path=path,
                    data=data,
                    content_type=content_type,
                    settings=self._settings,
                    run_id=ctx.run_id,
                )
            except AppError as error:
                raise NotDone(error.message) from None
            await db.commit()
            return {"saved": file.storage_key, "path": file.path, "type": file.content_type, "size": file.size_bytes}

    async def _bot(self, db: AsyncSession, ctx: ToolContext) -> Bot:
        bot = await db.get(Bot, ctx.bot_id)
        if bot is None or bot.org_id != ctx.org_id:
            raise NotDone("This bot isn't there any more.")
        return bot


def cut(text: str, part: int) -> str:
    """The first and last `part` bytes of `text`, with how much was cut between them."""
    data = text.encode("utf-8")
    if len(data) <= 2 * part:
        return text
    head = data[:part].decode("utf-8", errors="ignore")
    tail = data[-part:].decode("utf-8", errors="ignore")
    return f"{head}\n… {len(data) - 2 * part} bytes cut …\n{tail}"


def _shell_path(path: str) -> str:
    """A path for the shell, quoted, with ~ still meaning the home folder."""
    if path == "~":
        return "~"
    if path.startswith("~/"):
        return "~/" + shlex.quote(path[2:])
    return shlex.quote(path)


def _cd(cwd: str) -> str:
    return f"cd -- {_shell_path(cwd.strip())}"


def _named(apps: list[App], name: str) -> App | None:
    return next((app for app in apps if app.name == name), None)


def _int(text: str, default: int) -> int:
    try:
        return int(text.strip())
    except ValueError:
        return default

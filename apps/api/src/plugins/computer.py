"""The Computer plugin (ADR 0020 §4): a bot works on its own cloud computer (Orgo): reads with
read-only commands, runs any command (a person may be asked first), keeps apps running, shares a
preview link, shows pages on its screen, and copies files to and from its Files.

Offered only to bots whose `computer` is "cloud" (and those aren't offered the Browser plugin:
their computer has its own browser; `runtime.toolset`). Every tool's output is outside text, so a
run that used one is tainted and anything above write-internal asks from then on (ADR 0004 §5).
`computer.run` isn't idempotent: a call cut off midway stops the run for a person.

A core plugin like Files; the handlers call `ComputerAccess`, provided by the app
(`services/computer_tools.py`).
"""

from typing import Annotated, Any, Protocol

from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolResult, ToolSpec
from pydantic import AfterValidator, BaseModel, Field

COMPUTER_PLUGIN_ID = "computer"
# The whole call, the computer's start on demand included (up to 5 minutes) and a command's own
# time (up to 5 minutes): the tool pipeline enforces it instead of TOOL_TIMEOUT_SECONDS.
CALL_TIMEOUT_SECONDS = 660.0
RUN_MAX_CHARS = 8000
APP_NAME = r"^[a-z0-9][a-z0-9-]{0,31}$"
# Ports the computer uses itself (Orgo refuses apps and links on them).
RESERVED_PORTS = frozenset({22, 3389, 8080, 9000, *range(5900, 6000), *range(6080, 6100)})

_CWD = "The folder to run it in, like ~/app. Empty: your home folder."


def _app_port(port: int | None) -> int | None:
    if port is not None and port in RESERVED_PORTS:
        raise ValueError(f"Port {port} is the computer's own; use another, like 3000 or 5173.")
    return port


HOME_ONLY = "Copy files into your home folder, like ~/app/data.csv."
NO_HIDDEN = (
    "Not into a hidden file or folder (a name starting with .): those are settings, and some make "
    "programs run (.git/config, .bashrc). Change those with computer.run, which a person approves."
)


def home_path(path: str) -> str:
    """Where a copy may go on the computer: inside the home folder (~/…, a relative path, or
    /root/…), with no hidden file or folder on the way, as ~/<path>. Raises ValueError saying why."""
    path = path.strip()
    if path.startswith("~/"):
        inside = path[2:]
    elif path.startswith("/root/"):
        inside = path[len("/root/") :]
    elif path.startswith(("/", "~")):
        raise ValueError(HOME_ONLY)
    else:
        inside = path
    names = inside.split("/")
    if not inside or any(not name or name == ".." for name in names):
        raise ValueError(HOME_ONLY)
    if any(name.startswith(".") for name in names):
        raise ValueError(NO_HIDDEN)
    return f"~/{inside}"


def _upload_to(path: str) -> str:
    return home_path(path) if path.strip() else ""


class ComputerAccess(Protocol):
    async def inspect(self, ctx: ToolContext, *, command: str, cwd: str) -> ToolResult: ...
    async def run(self, ctx: ToolContext, *, command: str, cwd: str, seconds: int) -> ToolResult: ...
    async def start_app(
        self, ctx: ToolContext, *, name: str, command: str, cwd: str, port: int | None
    ) -> ToolResult: ...
    async def app_logs(self, ctx: ToolContext, *, name: str, lines: int) -> ToolResult: ...
    async def stop_app(self, ctx: ToolContext, *, name: str) -> ToolResult: ...
    async def preview(self, ctx: ToolContext, *, port: int) -> ToolResult: ...
    async def open(self, ctx: ToolContext, *, url: str) -> ToolResult: ...
    async def screenshot(self, ctx: ToolContext) -> ToolResult: ...
    async def upload(self, ctx: ToolContext, *, path: str, shared: bool, to: str) -> ToolResult: ...
    async def download(self, ctx: ToolContext, *, path: str, to: str) -> ToolResult: ...


class InspectArgs(BaseModel):
    command: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "A command that only reads: ls, cat, head, tail, grep, rg, find, wc, du, df, ps, ss, git status/diff/"
            "log/show/branch/ls-files/rev-parse/blame/remote, tool --version…, joined by pipes (|) if you like. "
            "No ;, &&, redirection or $(…)."
        ),
    )
    cwd: str = Field(default="", max_length=500, description=_CWD)


class RunArgs(BaseModel):
    # Long, so the approval card shows the whole command in a box people can edit.
    command: str = Field(
        min_length=1,
        max_length=RUN_MAX_CHARS,
        description="The shell command (bash). Use non-interactive flags (-y, --yes, CI=1); it can't answer prompts.",
    )
    cwd: str = Field(default="", max_length=500, description=_CWD)
    timeout: int = Field(default=120, ge=1, le=300, description="Seconds before it is stopped (1 to 300).")


class StartAppArgs(BaseModel):
    name: str = Field(pattern=APP_NAME, description="A short name: lowercase letters, digits and dashes, like web.")
    command: str = Field(
        min_length=1, max_length=4000, description="What keeps running, like `npm run dev -- --host 0.0.0.0`."
    )
    cwd: str = Field(default="", max_length=500, description=_CWD)
    port: Annotated[int | None, AfterValidator(_app_port)] = Field(
        default=None,
        ge=1,
        le=65535,
        description="The port it listens on (on 0.0.0.0, not 127.0.0.1, for a preview link). Empty: none.",
    )


class AppNameArgs(BaseModel):
    name: str = Field(pattern=APP_NAME, description="The app's name, as given to computer.start_app.")


class AppLogsArgs(AppNameArgs):
    lines: int = Field(default=200, ge=1, le=1000, description="How many of its last lines of output.")


class PreviewArgs(BaseModel):
    port: Annotated[int, AfterValidator(_app_port)] = Field(
        ge=1, le=65535, description="The port the app listens on, like 3000."
    )


class OpenArgs(BaseModel):
    url: str = Field(
        min_length=8,
        max_length=2000,
        pattern=r"^https?://",
        description="The address, like http://localhost:3000 or https://example.com.",
    )


class NoArgs(BaseModel):
    pass


class UploadArgs(BaseModel):
    path: str = Field(min_length=1, max_length=300, description="The file in your Files, like reports/data.csv.")
    shared: bool = Field(default=False, description="True for the organization's shared folder; false for yours.")
    to: Annotated[str, AfterValidator(_upload_to)] = Field(
        default="",
        max_length=500,
        description="Where in your home folder on the computer, like ~/app/data.csv. Empty: ~/<its name>.",
    )


class DownloadArgs(BaseModel):
    path: str = Field(min_length=1, max_length=500, description="The file on the computer, like ~/app/report.pdf.")
    to: str = Field(default="", max_length=300, description="Where in your Files. Empty: downloads/<its name>.")


class _Unavailable:
    async def _refuse(self, *_: Any, **__: Any) -> ToolResult:
        raise RuntimeError("The computer isn't available here.")

    inspect = run = start_app = app_logs = stop_app = preview = open = screenshot = upload = download = _refuse


def manifest(access: ComputerAccess | None = None) -> PluginManifest:
    computer: ComputerAccess = access or _Unavailable()

    async def inspect(args: InspectArgs, ctx: ToolContext) -> ToolResult:
        return await computer.inspect(ctx, command=args.command, cwd=args.cwd)

    async def run(args: RunArgs, ctx: ToolContext) -> ToolResult:
        return await computer.run(ctx, command=args.command, cwd=args.cwd, seconds=args.timeout)

    async def start_app(args: StartAppArgs, ctx: ToolContext) -> ToolResult:
        return await computer.start_app(ctx, name=args.name, command=args.command, cwd=args.cwd, port=args.port)

    async def app_logs(args: AppLogsArgs, ctx: ToolContext) -> ToolResult:
        return await computer.app_logs(ctx, name=args.name, lines=args.lines)

    async def stop_app(args: AppNameArgs, ctx: ToolContext) -> ToolResult:
        return await computer.stop_app(ctx, name=args.name)

    async def preview(args: PreviewArgs, ctx: ToolContext) -> ToolResult:
        return await computer.preview(ctx, port=args.port)

    async def open_url(args: OpenArgs, ctx: ToolContext) -> ToolResult:
        return await computer.open(ctx, url=args.url)

    async def screenshot(args: NoArgs, ctx: ToolContext) -> ToolResult:
        return await computer.screenshot(ctx)

    async def upload(args: UploadArgs, ctx: ToolContext) -> ToolResult:
        return await computer.upload(ctx, path=args.path, shared=args.shared, to=args.to)

    async def download(args: DownloadArgs, ctx: ToolContext) -> ToolResult:
        return await computer.download(ctx, path=args.path, to=args.to)

    started = "Your computer starts by itself if it's stopped (that can take a minute)."
    return PluginManifest(
        id=COMPUTER_PLUGIN_ID,
        name="Computer",
        version="1.0.0",
        description="Work on your own cloud computer: read, run commands, keep apps running and share a preview.",
        tools=(
            ToolSpec(
                name="inspect",
                title="Look on the computer",
                description=(
                    "Run a command that only reads (ls, cat, grep, find, git status…) on your computer, without "
                    f"asking anyone. You get its exit code and output. {started}"
                ),
                args_model=InspectArgs,
                risk="read",
                handler=inspect,
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f"Look: `{_short(args.command)}`",
            ),
            ToolSpec(
                name="run",
                title="Run a command",
                description=(
                    "Run any shell command on your computer (install, build, test, git commit…), up to 5 minutes. "
                    "A person may be asked first, and sees the exact command. You get its exit code, how long it "
                    f"took and its output (the first and last 8 KB). Put long jobs in computer.start_app. {started}"
                ),
                args_model=RunArgs,
                risk="write-external",
                handler=run,
                egress="open",
                untrusted_output=True,
                summarize=lambda args: f"Run `{_short(args.command)}` on the bot's computer",
            ),
            ToolSpec(
                name="start_app",
                title="Start an app",
                description=(
                    "Keep a process running on your computer (a dev server, a worker), started again if it fails. "
                    f"The same name again replaces it. A person may be asked first. {started}"
                ),
                args_model=StartAppArgs,
                risk="write-external",
                handler=start_app,
                egress="open",
                untrusted_output=True,
                summarize=lambda args: f"Start the app {args.name}: `{_short(args.command)}`",
            ),
            ToolSpec(
                name="app_logs",
                title="Read an app's log",
                description="Read the last lines of an app's output (what it printed, errors included).",
                args_model=AppLogsArgs,
                risk="read",
                handler=app_logs,
                idempotent=True,
                untrusted_output=True,
            ),
            ToolSpec(
                name="stop_app",
                title="Stop an app",
                description="Stop an app started with computer.start_app, and remove it and its log.",
                args_model=AppNameArgs,
                risk="write-internal",
                handler=stop_app,
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f"Stop the app {args.name}",
            ),
            ToolSpec(
                name="preview",
                title="Share a preview link",
                description=(
                    "Make a web address for a port on your computer, to show people an app that runs there. It's "
                    "private to the Orgo workspace's members unless the Orgo plan allows opening it wider."
                ),
                args_model=PreviewArgs,
                risk="external-send",
                handler=preview,
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f"Make a preview link for port {args.port}",
            ),
            ToolSpec(
                name="open",
                title="Open on the screen",
                description=(
                    "Open an address in your computer's browser, so people watching your screen see it (an app you "
                    "started, a page). The page isn't read back to you."
                ),
                args_model=OpenArgs,
                risk="read",
                handler=open_url,
                egress="open",
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f"Open {_short(args.url)} on the bot's screen",
            ),
            ToolSpec(
                name="screenshot",
                title="Save a screenshot",
                description="Save a picture of your computer's screen to your Files (screenshots/).",
                args_model=NoArgs,
                risk="read",
                handler=screenshot,
                idempotent=True,
                untrusted_output=True,
            ),
            ToolSpec(
                name="upload",
                title="Copy a file to the computer",
                description=(
                    "Copy a file from your Files (or the shared folder) into your computer's home folder (up to "
                    "10 MB; not into hidden files or folders). A person may be asked first."
                ),
                args_model=UploadArgs,
                risk="write-external",  # what lands on the computer can change what its programs do
                handler=upload,
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f"Copy {args.path} to {args.to or '~/'} on the bot's computer",
            ),
            ToolSpec(
                name="download",
                title="Copy a file from the computer",
                description="Copy a file from your computer into your Files (up to 10 MB), to read with files.read.",
                args_model=DownloadArgs,
                risk="write-internal",
                handler=download,
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f"Copy {args.path} from the computer to Files",
            ),
        ),
        auth=None,
    )


def _short(text: str, limit: int = 80) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else f"{line[: limit - 1]}…"

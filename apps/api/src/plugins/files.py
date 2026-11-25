"""The Files plugin (ADR 0017 §4): a bot lists, reads, saves and deletes files in its own folder
(`botdesk/<its handle>/`) or the organization's shared one (`botdesk/_shared/`).

A core plugin like Team: always loaded, its id reserved, not an app people connect. New bots
have it switched on; the bot's Tools tab can switch it off. The handlers only check arguments
and call `FileAccess`, which the app provides (`services/file_tools.py`): a plugin gets no
database or storage of its own (see `ToolContext`).
"""

from typing import Any, Protocol

from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field

FILES_PLUGIN_ID = "files"
MAX_SAVE_CHARS = 500_000
READ_CHARS = 20_000

_PATH = "Where the file is inside the folder, with folders if you like: reports/march.csv."
_SHARED = "True for the shared folder every bot in the organization can read; false (default) for your own."


class FileAccess(Protocol):
    """What the tools do, provided by the app. Each method raises an exception whose message
    is for the bot when it can't (no such file, a bad path, storage refusing)."""

    async def list(self, ctx: ToolContext, *, shared: bool, folder: str) -> ToolResult: ...
    async def read(self, ctx: ToolContext, *, path: str, shared: bool, start: int) -> ToolResult: ...
    async def save(self, ctx: ToolContext, *, path: str, text: str, shared: bool) -> ToolResult: ...
    async def delete(self, ctx: ToolContext, *, path: str, shared: bool) -> ToolResult: ...


class ListArgs(BaseModel):
    shared: bool = Field(default=False, description=_SHARED)
    folder: str = Field(default="", max_length=300, description="Only files in this folder, like reports. Empty: all.")


class ReadArgs(BaseModel):
    path: str = Field(min_length=1, max_length=300, description=_PATH)
    shared: bool = Field(default=False, description=_SHARED)
    start: int = Field(
        default=0,
        ge=0,
        description=f"For long text files: the character to start from (each read gives {READ_CHARS:,}).",
    )


class SaveArgs(BaseModel):
    path: str = Field(min_length=1, max_length=300, description=_PATH)
    text: str = Field(max_length=MAX_SAVE_CHARS, description="The file's whole content, as text.")
    shared: bool = Field(default=False, description=_SHARED)


class DeleteArgs(BaseModel):
    path: str = Field(min_length=1, max_length=300, description=_PATH)
    shared: bool = Field(default=False, description=_SHARED)


class _Unavailable:
    """Where the app gave no `FileAccess` (a registry built only to read manifests)."""

    async def _refuse(self, *_: Any, **__: Any) -> ToolResult:
        raise RuntimeError("Files aren't available here.")

    list = read = save = delete = _refuse


def manifest(access: FileAccess | None = None) -> PluginManifest:
    files: FileAccess = access or _Unavailable()

    async def list_files(args: ListArgs, ctx: ToolContext) -> ToolResult:
        return await files.list(ctx, shared=args.shared, folder=args.folder)

    async def read_file(args: ReadArgs, ctx: ToolContext) -> ToolResult:
        return await files.read(ctx, path=args.path, shared=args.shared, start=args.start)

    async def save_file(args: SaveArgs, ctx: ToolContext) -> ToolResult:
        return await files.save(ctx, path=args.path, text=args.text, shared=args.shared)

    async def delete_file(args: DeleteArgs, ctx: ToolContext) -> ToolResult:
        return await files.delete(ctx, path=args.path, shared=args.shared)

    return PluginManifest(
        id=FILES_PLUGIN_ID,
        name="Files",
        version="1.0.0",
        description="Keep files in the bot's own folder, and read the organization's shared ones.",
        tools=(
            ToolSpec(
                name="list",
                title="List files",
                description=(
                    "List the files in your folder, or in the shared folder every bot in the organization can read: "
                    "their paths, types and sizes."
                ),
                args_model=ListArgs,
                risk="read",
                handler=list_files,
                idempotent=True,
            ),
            ToolSpec(
                name="read",
                title="Read a file",
                description=(
                    "Read a file from your folder or the shared folder. Text files (txt, md, csv, json, html…) and "
                    f"PDFs come back as text, {READ_CHARS:,} characters at a time; for images, videos and other "
                    "files you get their type and size."
                ),
                args_model=ReadArgs,
                risk="read",
                handler=read_file,
                idempotent=True,
                untrusted_output=True,  # people and web pages put files there
            ),
            ToolSpec(
                name="save",
                title="Save a file",
                description=(
                    "Save text as a file in your folder (or the shared folder): notes, reports, CSV, Markdown, JSON. "
                    "Saving the same path again replaces the file."
                ),
                args_model=SaveArgs,
                risk="write-internal",
                handler=save_file,
                idempotent=True,
                summarize=lambda args: f"Save {args.path}",
            ),
            ToolSpec(
                name="delete",
                title="Delete a file",
                description="Delete a file from your folder or the shared folder.",
                args_model=DeleteArgs,
                risk="destructive",
                handler=delete_file,
                idempotent=True,
                summarize=lambda args: f"Delete {args.path}",
            ),
        ),
        auth=None,
    )

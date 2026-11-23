"""Local storage: a folder on the BotDesk server's own disk (one per organization)."""

import asyncio
import os
import tempfile
from pathlib import Path

from src.storage.base import StorageError, check_key, round_trip


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def __repr__(self) -> str:
        return f"LocalStorage({self.root})"

    def _path(self, key: str) -> Path:
        path = self.root.joinpath(*check_key(key).split("/"))
        # `check_key` already refuses `..`; this catches anything a platform reads differently.
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise StorageError(f"That isn't a usable file path: {key!r}.")
        return path

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(_write, path, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise StorageError("That file isn't there any more.") from None

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    async def check(self) -> None:
        try:
            await round_trip(self)
        except OSError as error:
            raise StorageError(f"BotDesk can't write to its files folder on the server ({error.strerror}).") from None


def _write(path: Path, data: bytes) -> None:
    """Write to a temporary file next to it, then swap it in, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".botdesk-")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

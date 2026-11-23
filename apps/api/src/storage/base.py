"""What every kind of file storage does (ADR 0017 §3). Keys are `/`-separated paths like
`botdesk/inbox-manager/reports/march.csv`; the storage decides where they really live."""

from typing import Protocol

# What `check` writes, reads back and deletes.
CHECK_KEY = "botdesk/.botdesk-check"


class StorageError(Exception):
    """Storage refused or failed. The message is written for people (it ends up in the UI or
    in a bot's tool result), never a provider's raw error."""


class FileStorage(Protocol):
    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """Write the file, replacing one with the same key."""
        ...

    async def get(self, key: str) -> bytes:
        """The file's bytes, or `StorageError` when it isn't there."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the file. One that is already gone is fine."""
        ...

    async def check(self) -> None:
        """Write, read and delete a small file: `StorageError` saying what's wrong, or nothing."""
        ...


def check_key(key: str) -> str:
    """A key that stays inside the storage: relative, `/`-separated, no `.` or `..` parts."""
    parts = key.split("/")
    if not key or key.startswith("/") or "\\" in key or ":" in key or any(p in ("", ".", "..") for p in parts):
        raise StorageError(f"That isn't a usable file path: {key!r}.")
    return key


async def round_trip(storage: FileStorage) -> None:
    """`check` for any storage: write, read back, delete."""
    data = b"BotDesk checks it can write here. You can delete this file."
    await storage.put(CHECK_KEY, data, content_type="text/plain")
    if await storage.get(CHECK_KEY) != data:
        raise StorageError("The storage gave back something different from what was saved.")
    await storage.delete(CHECK_KEY)

"""Bots' files (ADR 0017 §3): where each one goes, the rules for paths and sizes, and the `files`
table that lists them. The bytes go to the organization's storage (`storage_service`).

A bot's files live in `botdesk/<bot handle>/`, shared ones in `botdesk/_shared/` (handles only
hold a-z, 0-9 and "-", so `_shared` can't be a bot's). Both people (uploads) and bots (the
`files` tools) save through `save`, so the rules are the same for both.
"""

import hashlib
import mimetypes
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.errors import BadRequest, NotFound
from src.models import Bot, File
from src.schemas.file import FileOut
from src.services.storage_service import LOCAL, ROOT, OrgStorage
from src.storage import StorageError

SHARED = "_shared"
MAX_PATH = 300
MAX_DEPTH = 6
# Text a bot can read: the first this many characters.
MAX_TEXT_CHARS = 50_000
# Characters no part of a path may hold (Windows refuses them, and they confuse people anyway).
_BAD_PART = re.compile(r'[\x00-\x1f<>:"|?*\\]')

BAD_PATH = (
    "That isn't a usable file path. Use folders and a name like reports/march.csv: "
    'no leading /, no .. and none of < > : " | ? * \\.'
)
NOT_FOUND = "File not found."
ELSEWHERE = "This file is in storage the organization no longer uses, so it can't be opened."

_TEXT_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
    "application/toml",
    "application/sql",
    "image/svg+xml",
}


def clean_path(path: str) -> str:
    """`reports/march.csv`, or `BadRequest`. The same rules for people and bots."""
    path = path.strip()
    parts = path.split("/")
    if not path or len(path) > MAX_PATH or len(parts) > MAX_DEPTH:
        raise BadRequest(BAD_PATH)
    for part in parts:
        if part in ("", ".", "..") or part != part.strip() or part.endswith(".") or _BAD_PART.search(part):
            raise BadRequest(BAD_PATH)
    return path


def folder_of(bot: Bot | None) -> str:
    return f"{ROOT}/{bot.handle if bot else SHARED}"


def content_type_of(path: str, given: str | None = None) -> str:
    if given and given != "application/octet-stream":
        return given
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def is_text(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type.split(";")[0] in _TEXT_TYPES


def view_of(file: File, storage: OrgStorage | None) -> FileOut:
    """`storage`: the organization's storage now (None when it can't be opened), for `available`."""
    folder = file.storage_key.removesuffix(f"/{file.path}")
    return FileOut(
        id=file.id,
        bot_id=file.bot_id,
        path=file.path,
        folder=folder,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        available=storage is not None and storage.name == file.storage,
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


async def list_files(db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID | None) -> list[File]:
    """A bot's files (or the shared ones when `bot_id` is None), by path."""
    owner = File.bot_id == bot_id if bot_id else File.bot_id.is_(None)
    return list((await db.scalars(select(File).where(File.org_id == org_id, owner).order_by(File.path))).all())


async def get_file(db: AsyncSession, org_id: uuid.UUID, file_id: uuid.UUID) -> File:
    file = await db.get(File, file_id)
    if file is None or file.org_id != org_id:
        raise NotFound(NOT_FOUND)
    return file


async def find_by_path(db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID | None, path: str) -> File | None:
    owner = File.bot_id == bot_id if bot_id else File.bot_id.is_(None)
    return await db.scalar(select(File).where(File.org_id == org_id, owner, File.path == path))


async def save(
    db: AsyncSession,
    storage: OrgStorage,
    *,
    org_id: uuid.UUID,
    bot: Bot | None,
    path: str,
    data: bytes,
    content_type: str | None,
    settings: Settings,
    run_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> File:
    """Write the file to storage and record it. Saving a path again replaces the file (same row,
    same place in storage). The caller commits."""
    path = clean_path(path)
    _check_size(len(data), settings)
    bot_id = bot.id if bot else None
    file = await find_by_path(db, org_id, bot_id, path)
    if storage.name == LOCAL:
        await _check_quota(db, org_id, len(data) - (file.size_bytes if file else 0), settings)

    # Replacing a file keeps its place, unless it was in storage the organization left.
    key = file.storage_key if file and file.storage == storage.name else f"{folder_of(bot)}/{path}"
    kind = content_type_of(path, content_type)
    try:
        await storage.files.put(key, data, content_type=kind)
    except StorageError as error:
        raise BadRequest(str(error)) from None

    if file is None:
        file = File(org_id=org_id, bot_id=bot_id, path=path)
        db.add(file)
    file.storage_key, file.storage = key, storage.name
    file.content_type, file.size_bytes = kind, len(data)
    file.sha256 = hashlib.sha256(data).hexdigest()
    file.run_id, file.user_id = run_id, user_id
    await db.flush()
    return file


async def read(storage: OrgStorage | None, file: File) -> bytes:
    if storage is None or storage.name != file.storage:
        raise BadRequest(ELSEWHERE)
    try:
        return await storage.files.get(file.storage_key)
    except StorageError as error:
        raise BadRequest(str(error)) from None


async def delete(db: AsyncSession, storage: OrgStorage | None, file: File) -> None:
    """Remove it from the list, and from storage when it's in the organization's storage now.
    The caller commits."""
    if storage is not None and storage.name == file.storage:
        try:
            await storage.files.delete(file.storage_key)
        except StorageError as error:
            raise BadRequest(str(error)) from None
    await db.delete(file)


def _check_size(size: int, settings: Settings) -> None:
    if size > settings.file_max_mb * 1024 * 1024:
        raise BadRequest(f"That file is too big: files can be up to {settings.file_max_mb} MB.")


async def _check_quota(db: AsyncSession, org_id: uuid.UUID, growth: int, settings: Settings) -> None:
    used = await db.scalar(
        select(func.coalesce(func.sum(File.size_bytes), 0)).where(File.org_id == org_id, File.storage == LOCAL)
    )
    if (used or 0) + growth > settings.local_files_quota_mb * 1024 * 1024:
        raise BadRequest(
            f"This organization has used its {settings.local_files_quota_mb} MB of files on this server. "
            "Delete some, or choose your own storage in Settings → Computers."
        )

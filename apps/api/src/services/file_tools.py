"""The Files plugin's `FileAccess` (ADR 0017 §4): what `files.list/read/save/delete` do for a bot.

Each call opens its own database session and the organization's storage, and goes through
`file_service`, so bots follow the same rules as people's uploads (paths, sizes, quota).
"""

import uuid
from collections.abc import Awaitable

from botdesk_plugin_sdk import ToolContext, ToolResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.errors import AppError
from src.models import Bot, File
from src.plugins.files import READ_CHARS
from src.services import document_text, file_service, storage_service
from src.services.credential_vault import CredentialVault
from src.services.storage_service import OrgStorage

MAX_LISTED = 200


class ToolFailed(Exception):
    """A message for the bot ("There's no file called x."). The tool pipeline shows it as the failure."""


class FileTools:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, vault: CredentialVault
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._vault = vault

    async def list(self, ctx: ToolContext, *, shared: bool, folder: str) -> ToolResult:
        async with self._sessionmaker() as db:
            bot = await self._bot(db, ctx)
            files = await file_service.list_files(db, ctx.org_id, None if shared else bot.id)
        prefix = f"{folder.strip().strip('/')}/" if folder.strip().strip("/") else ""
        matching = [file for file in files if file.path.startswith(prefix)]
        return {
            "folder": file_service.folder_of(None if shared else bot),
            "files": [_entry(file) for file in matching[:MAX_LISTED]],
            "count": len(matching),
            **({"note": f"Only the first {MAX_LISTED} are listed."} if len(matching) > MAX_LISTED else {}),
        }

    async def read(self, ctx: ToolContext, *, path: str, shared: bool, start: int) -> ToolResult:
        async with self._sessionmaker() as db:
            bot = await self._bot(db, ctx)
            file = await self._find(db, ctx.org_id, bot, path, shared)
            storage = await self._storage(db, ctx.org_id)
        entry = _entry(file)
        if not document_text.is_readable(file.content_type):
            return {**entry, "note": "This isn't a text file or a PDF, so its content can't be shown as text."}
        data = await _call(file_service.read(storage, file))
        document = await document_text.text_of(data, file.content_type)
        text = document.text if document else ""
        part = text[start : start + READ_CHARS]
        more = start + READ_CHARS < len(text)
        return {
            **entry,
            "text": part,
            **({"next_start": start + READ_CHARS} if more else {}),
            **({"note": document.note} if document and document.note else {}),
        }

    async def save(self, ctx: ToolContext, *, path: str, text: str, shared: bool) -> ToolResult:
        async with self._sessionmaker() as db:
            bot = await self._bot(db, ctx)
            storage = await self._storage(db, ctx.org_id)
            file = await _call(
                file_service.save(
                    db,
                    storage,
                    org_id=ctx.org_id,
                    bot=None if shared else bot,
                    path=path,
                    data=text.encode("utf-8"),
                    content_type=None,
                    settings=self._settings,
                    run_id=ctx.run_id,
                )
            )
            await db.commit()
            return {"saved": file.storage_key, **_entry(file)}

    async def delete(self, ctx: ToolContext, *, path: str, shared: bool) -> ToolResult:
        async with self._sessionmaker() as db:
            bot = await self._bot(db, ctx)
            file = await self._find(db, ctx.org_id, bot, path, shared)
            storage = await self._storage(db, ctx.org_id)
            await _call(file_service.delete(db, storage, file))
            await db.commit()
        return {"deleted": file.path}

    async def _bot(self, db: AsyncSession, ctx: ToolContext) -> Bot:
        bot = await db.get(Bot, ctx.bot_id)
        if bot is None or bot.org_id != ctx.org_id:
            raise ToolFailed("This bot isn't there any more.")
        return bot

    async def _find(self, db: AsyncSession, org_id: uuid.UUID, bot: Bot, path: str, shared: bool) -> File:
        try:
            clean = file_service.clean_path(path)
        except AppError as error:
            raise ToolFailed(error.message) from None
        file = await file_service.find_by_path(db, org_id, None if shared else bot.id, clean)
        if file is None:
            where = "the shared folder" if shared else "your folder"
            raise ToolFailed(f"There's no file called {clean} in {where}. List the files to see what's there.")
        return file

    async def _storage(self, db: AsyncSession, org_id: uuid.UUID) -> OrgStorage:
        row = await storage_service.find(db, org_id)
        return await _call(storage_service.open_storage(row, org_id, self._settings, self._vault))


async def _call[T](work: Awaitable[T]) -> T:
    """The services' errors, as messages for the bot."""
    try:
        return await work
    except AppError as error:
        raise ToolFailed(error.message) from None


def _entry(file: File) -> dict[str, str | int]:
    updated = file.updated_at.isoformat()
    return {"path": file.path, "type": file.content_type, "size": file.size_bytes, "updated": updated}

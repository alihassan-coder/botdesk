import uuid

import httpx
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.core.errors import AppError
from src.models import File
from src.schemas.file import FileOut, StorageIn, StorageOut
from src.services import bot_service, file_service, storage_service
from src.services.credential_vault import CredentialVault
from src.services.storage_service import OrgStorage


async def get_storage(db: AsyncSession, access: Access, settings: Settings) -> StorageOut:
    return storage_service.view_of(await storage_service.find(db, access.org.id), settings)


async def choose_storage(
    db: AsyncSession,
    access: Access,
    body: StorageIn,
    *,
    settings: Settings,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None = None,
) -> StorageOut:
    """Owners and admins. Checked with a live write before anything changes."""
    access.require_admin()
    bots = await bot_service.list_bots(db, access.org.id)
    row = await storage_service.choose(
        db,
        org_id=access.org.id,
        user_id=access.user.id,
        body=body,
        settings=settings,
        vault=vault,
        bots=bots,
        transport=transport,
    )
    await db.commit()
    return storage_service.view_of(row, settings)


async def list_files(
    db: AsyncSession, access: Access, bot_id: uuid.UUID | None, *, settings: Settings, vault: CredentialVault
) -> list[FileOut]:
    if bot_id is not None:
        await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another organization's bot
    files = await file_service.list_files(db, access.org.id, bot_id)
    storage = await _storage_if_open(db, access, settings, vault)
    return [file_service.view_of(file, storage) for file in files]


async def upload(
    db: AsyncSession,
    access: Access,
    *,
    bot_id: uuid.UUID | None,
    path: str | None,
    upload: UploadFile,
    settings: Settings,
    vault: CredentialVault,
    keep_both: bool = False,
) -> FileOut:
    """Any member may give a bot (or the shared folder) a file. Same path: replaced."""
    bot = await bot_service.get_bot(db, access.org.id, bot_id) if bot_id else None
    storage = await _open(db, access, settings, vault)
    # One byte over the limit is enough to refuse it; never read more than that.
    data = await upload.read(settings.file_max_mb * 1024 * 1024 + 1)
    file = await file_service.save(
        db,
        storage,
        org_id=access.org.id,
        bot=bot,
        path=path or upload.filename or "",
        data=data,
        content_type=upload.content_type,
        settings=settings,
        user_id=access.user.id,
        keep_both=keep_both,
    )
    await db.commit()
    return file_service.view_of(file, storage)


async def content(
    db: AsyncSession, access: Access, file_id: uuid.UUID, *, settings: Settings, vault: CredentialVault
) -> tuple[File, bytes]:
    file = await file_service.get_file(db, access.org.id, file_id)
    storage = await _storage_if_open(db, access, settings, vault)
    return file, await file_service.read(storage, file)


async def delete(
    db: AsyncSession, access: Access, file_id: uuid.UUID, *, settings: Settings, vault: CredentialVault
) -> None:
    file = await file_service.get_file(db, access.org.id, file_id)
    storage = await _storage_if_open(db, access, settings, vault)
    await file_service.delete(db, storage, file)
    await db.commit()


async def _open(db: AsyncSession, access: Access, settings: Settings, vault: CredentialVault) -> OrgStorage:
    row = await storage_service.find(db, access.org.id)
    return await storage_service.open_storage(row, access.org.id, settings, vault)


async def _storage_if_open(
    db: AsyncSession, access: Access, settings: Settings, vault: CredentialVault
) -> OrgStorage | None:
    """The organization's storage, or None when it can't be opened now (Local turned off, an
    address that became private): files are still listed, just not available."""
    try:
        return await _open(db, access, settings, vault)
    except AppError:
        return None

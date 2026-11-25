import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Response, UploadFile, status

from src.api.deps import AppSettings, Db, OrgAccess, Outbound, Vault
from src.controllers import file_controller
from src.schemas.file import FileOut, StorageIn, StorageOut

router = APIRouter(prefix="/orgs/{org_id}", tags=["files"])

# Shown in the browser; everything else downloads. Never HTML or SVG: these come from the API's
# own address, where a page could use the member's session.
_INLINE = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/avif",
    "text/plain",
    "text/csv",
    "text/markdown",
)


@router.get("/storage")
async def get_storage(access: OrgAccess, db: Db, settings: AppSettings) -> StorageOut:
    """Where the organization's files are kept: Local (this server) or its own S3-compatible bucket."""
    return await file_controller.get_storage(db, access, settings)


@router.put("/storage")
async def choose_storage(
    body: StorageIn, access: OrgAccess, db: Db, settings: AppSettings, vault: Vault, outbound: Outbound
) -> StorageOut:
    """Choose the organization's storage (owners and admins): Local, an S3-compatible bucket, or
    Cloudinary. It is checked with a live write, then `botdesk/` gets a folder per bot and
    `_shared`. Files saved before stay where they were."""
    return await file_controller.choose_storage(db, access, body, settings=settings, vault=vault, transport=outbound)


@router.get("/files")
async def list_files(
    access: OrgAccess,
    db: Db,
    settings: AppSettings,
    vault: Vault,
    bot_id: Annotated[uuid.UUID | None, Query(alias="botId")] = None,
) -> list[FileOut]:
    """A bot's files, or the shared ones without `botId`."""
    return await file_controller.list_files(db, access, bot_id, settings=settings, vault=vault)


@router.post("/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    access: OrgAccess,
    db: Db,
    settings: AppSettings,
    vault: Vault,
    bot_id: Annotated[uuid.UUID | None, Form(alias="botId")] = None,
    path: Annotated[str | None, Form()] = None,
    keep_both: Annotated[bool, Form(alias="keepBoth")] = False,
) -> FileOut:
    """Give a bot a file (or the shared folder, without `botId`). `path` defaults to the file's
    name; saving the same path again replaces it, unless `keepBoth` (files attached in chat): then
    the new one gets a free name next to it, "q3 (2).pdf"."""
    return await file_controller.upload(
        db, access, bot_id=bot_id, path=path, upload=file, settings=settings, vault=vault, keep_both=keep_both
    )


@router.get("/files/{file_id}/content")
async def file_content(file_id: uuid.UUID, access: OrgAccess, db: Db, settings: AppSettings, vault: Vault) -> Response:
    file, data = await file_controller.content(db, access, file_id, settings=settings, vault=vault)
    name = quote(file.path.rsplit("/", 1)[-1])
    shown = file.content_type in _INLINE or file.content_type.startswith(("video/", "audio/"))
    headers = {
        "Content-Disposition": f"{'inline' if shown else 'attachment'}; filename*=UTF-8''{name}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "private, no-store",
    }
    return Response(content=data, media_type=file.content_type, headers=headers)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: uuid.UUID, access: OrgAccess, db: Db, settings: AppSettings, vault: Vault) -> None:
    await file_controller.delete(db, access, file_id, settings=settings, vault=vault)

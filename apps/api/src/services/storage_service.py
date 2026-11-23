"""The organization's storage provider (ADR 0017 §2): which storage it uses, opening it for a
request or a run, and switching to another (checked with a live write first).

No row means Local: a folder on this server, `FILES_DIR/<organization id>/`, unless the operator
turned Local off (`LOCAL_FILES=false`). S3-compatible storage keeps its keys sealed by the vault.
"""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import BadRequest, Unavailable
from src.core.url_guard import PRIVATE_NETWORK, UnsafeUrl, check_base_url
from src.models import Bot, ComputerProvider
from src.schemas.file import S3In, S3Out, StorageIn, StorageOut
from src.services.credential_vault import CredentialVault
from src.storage import FileStorage, LocalStorage, S3Location, S3Storage, StorageError

STORAGE = "storage"
LOCAL = "local"
S3 = "s3"
ROOT = "botdesk"

LOCAL_OFF = "This server doesn't keep files itself. An owner or admin can choose storage in Settings → Computers."
PRIVATE_STORAGE = (
    "That address is on a private network, which this server doesn't allow. "
    "Self-hosting? Set ALLOW_PRIVATE_STORAGE_URLS=true."
)
HTTPS_ONLY = "Use an address that starts with https://."
NEEDS_S3 = "Fill in the bucket's details."
NEEDS_SECRET = "Add the secret access key."  # noqa: S105 - a message, not a password

ROOT_README = (
    "Files your BotDesk bots keep. Each bot has its own folder, named after its @handle; "
    "_shared holds files every bot in the organization can read.\n"
)


@dataclass(frozen=True)
class OrgStorage:
    """An organization's storage, open. `name` tells files' storage apart (`File.storage`)."""

    files: FileStorage
    name: str


async def find(db: AsyncSession, org_id: uuid.UUID) -> ComputerProvider | None:
    return await db.scalar(
        select(ComputerProvider).where(ComputerProvider.org_id == org_id, ComputerProvider.kind == STORAGE)
    )


def view_of(row: ComputerProvider | None, settings: Settings) -> StorageOut:
    if row is None or row.provider == LOCAL:
        return StorageOut(provider="local", s3=None, local_available=settings.local_files, checked_at=None)
    location = _location(row)
    s3 = S3Out(
        endpoint=location.endpoint,
        region=location.region,
        bucket=location.bucket,
        prefix=location.prefix,
        access_key_hint=row.secret_hint,
    )
    return StorageOut(provider="s3", s3=s3, local_available=settings.local_files, checked_at=row.checked_at)


async def open_storage(
    row: ComputerProvider | None, org_id: uuid.UUID, settings: Settings, vault: CredentialVault
) -> OrgStorage:
    """The organization's storage, ready to use. `Unavailable` when it's Local and Local is off."""
    if row is None or row.provider == LOCAL:
        if not settings.local_files:
            raise Unavailable(LOCAL_OFF)
        return OrgStorage(LocalStorage(Path(settings.files_dir) / str(org_id)), LOCAL)
    location = _location(row)
    await _check_endpoint(location.endpoint, settings)  # again: where a name points can change
    keys = json.loads(vault.unseal(row.encrypted_secret))
    return OrgStorage(_s3(location, keys["access_key_id"], keys["secret_access_key"], settings), _s3_name(location))


async def choose(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: StorageIn,
    settings: Settings,
    vault: CredentialVault,
    bots: list[Bot],
) -> ComputerProvider | None:
    """Switch the organization to this storage once a live write, read and delete works, and lay
    out its folders (`botdesk/`, one per bot, `_shared`). The caller commits. Returns the row, or
    None for Local (no row)."""
    existing = await find(db, org_id)
    if body.provider == LOCAL:
        storage = await open_storage(None, org_id, settings, vault)
        await _prepare(storage.files, bots)
        if existing is not None:
            await db.delete(existing)
        return None

    if body.s3 is None:
        raise BadRequest(NEEDS_S3)
    secret = body.s3.secret_access_key or _saved_secret(existing, vault)
    location = S3Location(
        bucket=body.s3.bucket, region=body.s3.region, endpoint=body.s3.endpoint.rstrip("/"), prefix=body.s3.prefix
    )
    await _check_endpoint(location.endpoint, settings)
    await _prepare(_s3(location, body.s3.access_key_id, secret, settings), bots)

    row = existing or ComputerProvider(org_id=org_id, kind=STORAGE, created_by=user_id)
    row.provider = S3
    row.config = _config(body.s3)
    row.encrypted_secret = vault.seal(json.dumps({"access_key_id": body.s3.access_key_id, "secret_access_key": secret}))
    row.secret_hint = body.s3.access_key_id[-4:]
    row.checked_at = utcnow()
    db.add(row)
    return row


async def _prepare(storage: FileStorage, bots: list[Bot]) -> None:
    """Check it works, then make the folders people will see: `botdesk/`, one per bot, `_shared`."""
    try:
        await storage.check()
        await storage.put(f"{ROOT}/README.txt", ROOT_README.encode(), content_type="text/plain")
        for bot in bots:
            readme = f"Files {bot.name} (@{bot.handle}) keeps.\n"
            await storage.put(f"{ROOT}/{bot.handle}/README.txt", readme.encode(), content_type="text/plain")
        shared = b"Files every bot in the organization can read.\n"
        await storage.put(f"{ROOT}/_shared/README.txt", shared, content_type="text/plain")
    except StorageError as error:
        raise BadRequest(str(error)) from None


def _saved_secret(existing: ComputerProvider | None, vault: CredentialVault) -> str:
    if existing is None or existing.provider != S3:
        raise BadRequest(NEEDS_SECRET)
    secret: str = json.loads(vault.unseal(existing.encrypted_secret))["secret_access_key"]
    return secret


async def _check_endpoint(endpoint: str, settings: Settings) -> None:
    """Empty is AWS itself. Anything else: https, and public unless ALLOW_PRIVATE_STORAGE_URLS."""
    if not endpoint:
        return
    allow_private = settings.allow_private_storage_urls
    if not allow_private and httpx.URL(endpoint).scheme != "https":
        raise BadRequest(HTTPS_ONLY)
    try:
        await check_base_url(endpoint, allow_private=allow_private)
    except UnsafeUrl as error:
        raise BadRequest(PRIVATE_STORAGE if error.message == PRIVATE_NETWORK else error.message) from None


def _s3(location: S3Location, access_key_id: str, secret_access_key: str, settings: Settings) -> S3Storage:
    return S3Storage(
        location,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        allow_http=settings.allow_private_storage_urls,
    )


def _location(row: ComputerProvider) -> S3Location:
    config = row.config
    return S3Location(
        bucket=config["bucket"],
        region=config["region"],
        endpoint=config.get("endpoint", ""),
        prefix=config.get("prefix", ""),
    )


def _config(s3: S3In) -> dict[str, str]:
    return {"endpoint": s3.endpoint.rstrip("/"), "region": s3.region, "bucket": s3.bucket, "prefix": s3.prefix}


def _s3_name(location: S3Location) -> str:
    return f"s3:{location.describe()}"

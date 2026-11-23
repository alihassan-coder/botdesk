"""The organization's browser provider (ADR 0017 §2): Local or a cloud provider with its key, where
a bot's browser starts (`launch_for`), and each bot's profile there.

No row means Local, unless the operator turned Local off (`LOCAL_BROWSER=false`): then bots
have no browser until an owner or admin chooses a provider in Settings → Computers.
"""

import json
import uuid

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.browser.browsers import LOCAL, Launch
from src.browser.cloud import CloudBrowserError, CloudProviderId, cloud_browser
from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import BadRequest
from src.models import BrowserProfile, ComputerProvider
from src.schemas.browser import BrowserProviderIn, BrowserProviderOut
from src.services.credential_vault import CredentialVault

BROWSER = "browser"
LOCAL_OFF = "This server doesn't run browsers itself. Choose a cloud browser provider."
NEEDS_KEY = "Add the provider's API key."


async def find(db: AsyncSession, org_id: uuid.UUID) -> ComputerProvider | None:
    return await db.scalar(
        select(ComputerProvider).where(ComputerProvider.org_id == org_id, ComputerProvider.kind == BROWSER)
    )


def view_of(row: ComputerProvider | None, settings: Settings) -> BrowserProviderOut:
    if row is None:
        return BrowserProviderOut(
            provider="local", key_hint=None, project_id="", local_available=settings.local_browser, checked_at=None
        )
    return BrowserProviderOut(
        provider=row.provider,
        key_hint=row.secret_hint,
        project_id=str(row.config.get("project_id", "")),
        local_available=settings.local_browser,
        checked_at=row.checked_at,
    )


async def launch_for(
    db: AsyncSession,
    org_id: uuid.UUID,
    bot_id: uuid.UUID,
    settings: Settings,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Launch | None:
    """Where this bot's browser starts: Local, the organization's cloud provider with the bot's
    profile there, or None when there's no browser (Local is off and nothing was chosen)."""
    row = await find(db, org_id)
    if row is None:
        return LOCAL if settings.local_browser else None
    provider: CloudProviderId = row.provider  # type: ignore[assignment]
    key = json.loads(vault.unseal(row.encrypted_secret))["api_key"]
    cloud = cloud_browser(provider, key, str(row.config.get("project_id", "")), transport=transport)
    profile = await db.scalar(
        select(BrowserProfile.ref).where(BrowserProfile.bot_id == bot_id, BrowserProfile.provider == provider)
    )
    return Launch(cloud=cloud, profile=profile)


async def remember_profile(
    db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID, provider: str, ref: str | None
) -> None:
    """Keep the bot's profile at the provider (a new one the provider just made). The caller commits."""
    if not ref:
        return
    row = await db.scalar(
        select(BrowserProfile).where(BrowserProfile.bot_id == bot_id, BrowserProfile.provider == provider)
    )
    if row is None:
        db.add(BrowserProfile(org_id=org_id, bot_id=bot_id, provider=provider, ref=ref))
    elif row.ref != ref:
        row.ref = ref


async def forget_profiles(db: AsyncSession, bot_id: uuid.UUID) -> None:
    """Forget sign-ins at every cloud provider: the bot's next browser gets a fresh profile."""
    await db.execute(delete(BrowserProfile).where(BrowserProfile.bot_id == bot_id))


async def choose(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: BrowserProviderIn,
    settings: Settings,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ComputerProvider | None:
    """Switch the organization's bots to this browser provider once a browser starts and stops
    there. The caller commits. Returns the row, or None for Local (no row)."""
    existing = await find(db, org_id)
    if body.provider == "local":
        if not settings.local_browser:
            raise BadRequest(LOCAL_OFF)
        if existing is not None:
            await db.delete(existing)
        return None

    key = body.api_key or _saved_key(existing, body.provider, vault)
    try:
        await cloud_browser(body.provider, key, body.project_id.strip(), transport=transport).check()
    except CloudBrowserError as error:
        raise BadRequest(str(error)) from None

    row = existing or ComputerProvider(org_id=org_id, kind=BROWSER, created_by=user_id)
    row.provider = body.provider
    row.config = {"project_id": body.project_id.strip()} if body.project_id.strip() else {}
    row.encrypted_secret = vault.seal(json.dumps({"api_key": key}))
    row.secret_hint = key[-4:]
    row.checked_at = utcnow()
    db.add(row)
    return row


def _saved_key(existing: ComputerProvider | None, provider: str, vault: CredentialVault) -> str:
    if existing is None or existing.provider != provider:
        raise BadRequest(NEEDS_KEY)
    key: str = json.loads(vault.unseal(existing.encrypted_secret))["api_key"]
    return key

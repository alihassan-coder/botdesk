"""The organization's memory key (Settings → Memory): a key used only for its bots' memory.

Checked with a live call before it's saved (the provider lists its models), sealed by the vault,
shown as its last 4 characters. Saving or removing it makes the organization's memory start
over with the new key (`OrgMemory.forget`).
"""

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utcnow
from src.core.errors import BadRequest
from src.model_providers import ProviderError, adapter_for
from src.models import MemoryKey
from src.runtime.memory import MemoryProvider
from src.schemas.memory import MemoryKeyIn, MemoryKeyOut
from src.services.credential_vault import CredentialVault

TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def find(db: AsyncSession, org_id: uuid.UUID) -> MemoryKey | None:
    return await db.scalar(select(MemoryKey).where(MemoryKey.org_id == org_id))


def view_of(row: MemoryKey | None) -> MemoryKeyOut:
    if row is None:
        return MemoryKeyOut(provider=None, key_hint=None, checked_at=None)
    return MemoryKeyOut(provider=row.provider, key_hint=row.key_hint, checked_at=row.checked_at)


async def check(provider: MemoryProvider, api_key: str, transport: httpx.AsyncBaseTransport | None) -> None:
    """The provider accepts the key: `BadRequest` with its reason otherwise."""
    async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport, follow_redirects=False) as http:
        try:
            await adapter_for(provider).list_models(http, api_key, None)
        except ProviderError as error:
            raise BadRequest(f"That key didn't work: {error}") from None


async def save(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemoryKeyIn,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MemoryKey:
    """Check the key live, then keep it. The caller commits."""
    key = body.api_key.strip()
    await check(body.provider, key, transport)
    row = await find(db, org_id) or MemoryKey(org_id=org_id, created_by=user_id)
    row.provider = body.provider
    row.encrypted_key = vault.seal(key)
    row.key_hint = key[-4:]
    row.checked_at = utcnow()
    db.add(row)
    return row

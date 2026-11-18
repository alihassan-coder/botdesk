"""Handles Models & keys requests. Everyone in the organization sees the providers and models;
owners and admins add, replace, test and remove the organization's keys. Every member manages
their own keys ("My keys", built-in providers only): only they see them (last 4 characters), and
they serve only runs that member is the requester of.

Calls to providers can take seconds, so every handler here ends its database transaction
(`db.commit()`, which also returns the connection to the pool) before calling out, and opens a
short new one afterwards to save the result.
"""

import uuid
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import AppError, BadRequest, NotFound
from src.core.secrets import SecretBox
from src.model_providers import ProviderError
from src.models import ProviderCredential
from src.schemas.provider import ModelListOut, ProviderKeyIn, ProviderOut, ProviderProblem, ProviderTestOut
from src.services import provider_service
from src.services.model_catalog import ModelCatalog


async def list_providers(db: AsyncSession, access: Access, settings: Settings) -> list[ProviderOut]:
    credentials = await provider_service.list_credentials(db, access.org.id)
    return provider_service.provider_views(credentials, settings)


async def save_key(
    db: AsyncSession,
    access: Access,
    provider_id: str,
    body: ProviderKeyIn,
    *,
    secrets: SecretBox,
    catalog: ModelCatalog,
) -> ProviderOut:
    """Check the key with a live call to the provider, and save it only if it works."""
    access.require_admin()
    org_id, user_id = access.org.id, access.user.id
    target = provider_service.parse_target(provider_id)
    existing = await provider_service.find_credential(db, org_id, target)
    if target.custom_id and existing is None:
        raise NotFound(provider_service.NOT_CONNECTED)
    draft = provider_service.draft_connection(target, body, existing, secrets)
    await db.commit()  # nothing held open while the provider answers

    try:
        models = await catalog.fetch(draft)
    except ProviderError as error:
        raise BadRequest(f"That key didn't work: {error}") from error

    credential = await provider_service.save_credential(
        db, org_id=org_id, user_id=user_id, connection=draft, secrets=secrets, verified_at=utcnow()
    )
    await db.commit()
    catalog.remember(org_id, draft, models)  # the next model list is instant
    return provider_service.view_of(credential)


async def test_key(
    db: AsyncSession, access: Access, provider_id: str, *, secrets: SecretBox, catalog: ModelCatalog
) -> ProviderTestOut:
    access.require_admin()
    org_id = access.org.id
    credential = await provider_service.find_credential(db, org_id, provider_service.parse_target(provider_id))
    if credential is None:
        raise NotFound(provider_service.NOT_CONNECTED)
    credential_id = credential.id
    await db.commit()
    problem = await _check(catalog, org_id, credential, secrets)

    saved = await provider_service.record_check(db, credential_id, ok=problem is None)
    await db.commit()
    if saved is None:
        raise NotFound(provider_service.NOT_CONNECTED)
    return ProviderTestOut(ok=problem is None, error=problem, provider=provider_service.view_of(saved))


async def _check(
    catalog: ModelCatalog, org_id: uuid.UUID, credential: ProviderCredential, secrets: SecretBox
) -> str | None:
    """None when the saved key works; otherwise what's wrong, ready to show."""
    try:
        connection = provider_service.connection_of(credential, secrets)
        await catalog.models(org_id, connection, refresh=True)
    except ProviderError as error:
        return f"That key didn't work: {error}"
    except AppError as error:  # e.g. the custom server's address isn't allowed any more
        return error.message
    return None


async def remove_key(db: AsyncSession, access: Access, provider_id: str, *, catalog: ModelCatalog) -> None:
    access.require_admin()
    target = provider_service.parse_target(provider_id)
    await provider_service.delete_credential(db, access.org.id, target)
    await db.commit()
    catalog.forget(access.org.id, provider_id)


async def list_models(
    db: AsyncSession,
    access: Access,
    *,
    provider: str | None,
    refresh: bool,
    settings: Settings,
    secrets: SecretBox,
    catalog: ModelCatalog,
) -> ModelListOut:
    org_id = access.org.id
    connections, unreadable = await provider_service.connections(
        db, org_id, settings, secrets, member_id=access.user.id
    )
    await db.commit()
    if provider:
        connections = [c for c in connections if c.provider_id == provider]
        unreadable = {p: message for p, message in unreadable.items() if p == provider}
    result = await catalog.merged(org_id, connections, refresh=refresh)
    result.errors.extend(ProviderProblem(provider=p, message=message) for p, message in unreadable.items())
    return result


# My keys: a member's own, for the runs they're the requester of. Any member; nobody sees another's,
# owners and admins included.


async def list_my_keys(db: AsyncSession, access: Access) -> list[ProviderOut]:
    credentials = await provider_service.list_credentials(db, access.org.id, member_id=access.user.id)
    return provider_service.member_views(credentials)


async def save_my_key(
    db: AsyncSession,
    access: Access,
    provider_id: str,
    body: ProviderKeyIn,
    *,
    secrets: SecretBox,
    catalog: ModelCatalog,
) -> ProviderOut:
    """Checked with a live call first, like the organization's keys."""
    org_id, user_id = access.org.id, access.user.id
    target = provider_service.member_target(provider_id)
    draft = provider_service.draft_connection(target, body, None, secrets)
    await db.commit()  # nothing held open while the provider answers

    try:
        models = await catalog.fetch(draft)
    except ProviderError as error:
        raise BadRequest(f"That key didn't work: {error}") from error

    credential = await provider_service.save_credential(
        db, org_id=org_id, user_id=user_id, member_id=user_id, connection=draft, secrets=secrets, verified_at=utcnow()
    )
    await db.commit()
    # Your next model list is instant (cached apart from the organization's).
    catalog.remember(org_id, replace(draft, source="member", credential_id=credential.id), models)
    return provider_service.view_of(credential)


async def remove_my_key(db: AsyncSession, access: Access, provider_id: str, *, catalog: ModelCatalog) -> None:
    target = provider_service.member_target(provider_id)
    removed = await provider_service.delete_credential(db, access.org.id, target, member_id=access.user.id)
    await db.commit()
    catalog.forget(access.org.id, provider_id, member_key=removed)

"""Model provider keys: saving, listing, removing, and finding the key a run uses.

Rules:
- A built-in provider has at most one key per organization; custom servers may have several.
- A member may add their own key per built-in provider in an organization (`member_id`); those
  are listed, found and removed only for that member. No `member_id` means the organization's keys.
- Keys are encrypted with the app's SecretBox and decrypted only into a `ProviderAccess`, right
  before a call to the provider. A `ProviderAccess` never prints its key.
- A run's key: its requester's own, then the organization's, then the server's environment key
  (self-hosting). One member's key never serves another member's run.

Nothing here calls a provider: that's `model_catalog`, so no transaction waits on the network.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import ColumnElement, and_, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import BadRequest, NotFound
from src.core.secrets import SecretBox, SecretUnreadable
from src.model_providers import (
    BUILT_IN,
    CUSTOM_PREFIX,
    ProviderError,
    ProviderKind,
    custom_id_of,
    env_key,
    spec_for,
)
from src.models import ProviderCredential
from src.schemas.provider import ProviderKeyIn, ProviderOut

UNKNOWN_PROVIDER = "We don't support that provider."
MEMBER_KEYS_BUILT_IN_ONLY = (
    "Your own keys are for the built-in providers. Custom servers are added for the whole organization."
)
NOT_CONNECTED = "That provider isn't connected."
KEY_FOR_NEW_URL = (
    "You changed the base URL, so paste the API key again (or choose No key). "
    "A saved key is never sent to a new address."
)


@dataclass(frozen=True)
class ProviderAccess:
    """A provider ready to call: its decrypted key and where it lives. Lives for one request or one run.

    Not a *connection*: that word means an authorised account on a connector (GLOSSARY, ADR 0010)."""

    provider_id: str
    kind: ProviderKind
    name: str
    api_key: str = field(repr=False)
    base_url: str | None = None
    source: Literal["org", "member", "env"] = "org"
    credential_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Target:
    """What a URL's provider names: a built-in kind, a custom server ("custom-<id>"), or "custom" for a new one."""

    kind: ProviderKind
    custom_id: uuid.UUID | None = None

    @property
    def is_new_custom(self) -> bool:
        return self.kind == "custom" and self.custom_id is None


def parse_target(provider_id: str) -> Target:
    if provider_id in BUILT_IN:
        return Target(BUILT_IN[provider_id].kind)
    if provider_id == "custom":
        return Target("custom")
    if custom_id := custom_id_of(provider_id):
        return Target("custom", custom_id)
    raise NotFound(UNKNOWN_PROVIDER)


def provider_id_of(credential: ProviderCredential) -> str:
    return f"{CUSTOM_PREFIX}{credential.id}" if credential.provider == "custom" else credential.provider


def key_hint(api_key: str) -> str:
    """The last 4 characters, only for keys long enough that 4 characters give nothing away."""
    return api_key[-4:] if len(api_key) >= 12 else ""


# Reading


def _owned_by(org_id: uuid.UUID, member_id: uuid.UUID | None) -> ColumnElement[bool]:
    """The organization's keys (no member), or one member's own keys there."""
    owner = ProviderCredential.user_id.is_(None) if member_id is None else ProviderCredential.user_id == member_id
    return and_(ProviderCredential.org_id == org_id, owner)


async def list_credentials(
    db: AsyncSession, org_id: uuid.UUID, *, member_id: uuid.UUID | None = None
) -> list[ProviderCredential]:
    query = select(ProviderCredential).where(_owned_by(org_id, member_id))
    return list(await db.scalars(query.order_by(ProviderCredential.created_at)))


async def find_credential(
    db: AsyncSession, org_id: uuid.UUID, target: Target, *, member_id: uuid.UUID | None = None
) -> ProviderCredential | None:
    if target.is_new_custom:
        return None
    query = select(ProviderCredential).where(_owned_by(org_id, member_id))
    if target.custom_id:
        query = query.where(ProviderCredential.id == target.custom_id, ProviderCredential.provider == "custom")
    else:
        query = query.where(ProviderCredential.provider == target.kind)
    found: ProviderCredential | None = await db.scalar(query)
    return found


def view_of(credential: ProviderCredential) -> ProviderOut:
    kind: ProviderKind = credential.provider  # type: ignore[assignment]  # only valid kinds are saved
    spec = spec_for(kind)
    return ProviderOut(
        id=provider_id_of(credential),
        kind=kind,
        name=credential.label or spec.name,
        hint=spec.hint,
        connected=True,
        source="org" if credential.user_id is None else "member",
        key_hint=credential.key_hint or None,
        status="invalid" if credential.status == "invalid" else "ok",
        last_verified_at=credential.last_verified_at,
        base_url=credential.base_url,
    )


def provider_views(credentials: Sequence[ProviderCredential], settings: Settings) -> list[ProviderOut]:
    """Every built-in provider (connected or not), then the organization's custom servers."""
    saved = {credential.provider: credential for credential in credentials if credential.provider != "custom"}
    views: list[ProviderOut] = []
    for kind, spec in BUILT_IN.items():
        if credential := saved.get(kind):
            views.append(view_of(credential))
        else:
            from_env = bool(env_key(settings, kind))
            views.append(
                ProviderOut(
                    id=kind,
                    kind=spec.kind,
                    name=spec.name,
                    hint=spec.hint,
                    connected=from_env,
                    source="env" if from_env else None,
                )
            )
    views.extend(view_of(credential) for credential in credentials if credential.provider == "custom")
    return views


def member_views(credentials: Sequence[ProviderCredential]) -> list[ProviderOut]:
    """Your keys: every built-in provider, with the member's own key where they added one."""
    saved = {credential.provider: credential for credential in credentials}
    return [
        view_of(saved[kind])
        if kind in saved
        else ProviderOut(id=kind, kind=spec.kind, name=spec.name, hint=spec.hint, connected=False)
        for kind, spec in BUILT_IN.items()
    ]


def member_target(provider_id: str) -> Target:
    """The provider a member's own key is for: built-in providers only."""
    target = parse_target(provider_id)
    if target.kind == "custom":
        raise BadRequest(MEMBER_KEYS_BUILT_IN_ONLY)
    return target


def connection_of(credential: ProviderCredential, secrets: SecretBox) -> ProviderAccess:
    kind: ProviderKind = credential.provider  # type: ignore[assignment]
    name = credential.label or spec_for(kind).name
    try:
        api_key = secrets.decrypt(credential.encrypted_key) if credential.encrypted_key else ""
    except SecretUnreadable as error:
        raise ProviderError(
            "its saved key can't be read (did SECRET_KEY change?). Add the key again in Settings → Models & keys."
        ) from error
    source: Literal["org", "member"] = "org" if credential.user_id is None else "member"
    return ProviderAccess(provider_id_of(credential), kind, name, api_key, credential.base_url, source, credential.id)


def env_connection(settings: Settings, kind: str) -> ProviderAccess | None:
    spec = BUILT_IN.get(kind)
    api_key = env_key(settings, kind)
    return ProviderAccess(spec.kind, spec.kind, spec.name, api_key, source="env") if spec and api_key else None


async def connection_for(
    db: AsyncSession,
    org_id: uuid.UUID,
    provider_id: str,
    settings: Settings,
    secrets: SecretBox,
    *,
    requester_id: uuid.UUID | None = None,
) -> ProviderAccess | None:
    """The key a call to this provider uses: the requester's own (built-in providers only), else
    the organization's, else the environment's, else None. No requester (say, a run nobody asked
    for) skips members' keys. Raises `ProviderError` when the chosen saved key can't be decrypted."""
    try:
        target = parse_target(provider_id)
    except NotFound:
        return None
    if target.is_new_custom:
        return None
    own = (
        await find_credential(db, org_id, target, member_id=requester_id)
        if requester_id is not None and target.kind != "custom"
        else None
    )
    if own is not None:
        return connection_of(own, secrets)
    if credential := await find_credential(db, org_id, target):
        return connection_of(credential, secrets)
    return env_connection(settings, target.kind)


async def connections(
    db: AsyncSession,
    org_id: uuid.UUID,
    settings: Settings,
    secrets: SecretBox,
    *,
    member_id: uuid.UUID | None = None,
) -> tuple[list[ProviderAccess], dict[str, str]]:
    """Every connected provider, the way a run of `member_id` would reach it: that member's own
    key first for a built-in provider, then the organization's, then the server's. Plus
    {provider id: problem} for saved keys that can't be read. No `member_id`: no member's keys."""
    credentials = await list_credentials(db, org_id)
    own = await list_credentials(db, org_id, member_id=member_id) if member_id is not None else []
    mine = {credential.provider: credential for credential in own}
    found: list[ProviderAccess] = []
    problems: dict[str, str] = {}

    def add(credential: ProviderCredential) -> None:
        try:
            found.append(connection_of(credential, secrets))
        except ProviderError as error:
            problems[provider_id_of(credential)] = str(error)

    for credential in credentials:  # the organization's, oldest first (custom servers are never a member's)
        add(mine.get(credential.provider, credential))
    saved = {credential.provider for credential in credentials}
    for kind in BUILT_IN:
        if kind in saved:
            continue
        if kind in mine:
            add(mine[kind])
        elif env := env_connection(settings, kind):
            found.append(env)
    return found, problems


async def require_usable_model(
    db: AsyncSession, org_id: uuid.UUID, model_id: str, settings: Settings, *, member_id: uuid.UUID | None = None
) -> None:
    """A bot may only name a model of a provider that is connected (here, in the environment, or
    by the own key of `member_id`, whoever picks the model).
    The model itself isn't checked against the live list: lists change, and the run says so if it's gone."""
    if not model_id:
        return
    provider_id = model_id.partition(":")[0]
    try:
        target = parse_target(provider_id)
    except NotFound:
        target = None
    if target is None or target.is_new_custom:
        raise BadRequest(f'"{provider_id}" isn\'t a model provider we know.')
    if await find_credential(db, org_id, target) is not None or env_key(settings, target.kind):
        return
    if member_id is not None and await find_credential(db, org_id, target, member_id=member_id) is not None:
        return
    name = "That custom server" if target.kind == "custom" else spec_for(target.kind).name
    raise BadRequest(f"{name} isn't connected. Add a key in Settings → Models & keys first.")


# Changing


def draft_connection(
    target: Target, body: ProviderKeyIn, existing: ProviderCredential | None, secrets: SecretBox
) -> ProviderAccess:
    """What the request asks to save, checked for completeness (the live check comes next)."""
    api_key = body.api_key.strip()
    if target.kind != "custom":
        if not api_key:
            raise BadRequest("Paste the API key.")
        spec = BUILT_IN[target.kind]
        return ProviderAccess(spec.kind, spec.kind, spec.name, api_key)
    label = (body.label or "").strip() or (existing.label if existing else "")
    base_url = ((body.base_url or "").strip() or (existing.base_url if existing else "") or "").rstrip("/")
    if not label:
        raise BadRequest("Give this server a name.")
    if not base_url:
        raise BadRequest("Add the server's base URL, like http://localhost:11434/v1.")
    if not api_key and not body.no_key and existing is not None and existing.encrypted_key:
        api_key = _kept_key(existing, base_url, secrets)
    credential_id = existing.id if existing else uuid.uuid4()
    return ProviderAccess(f"{CUSTOM_PREFIX}{credential_id}", "custom", label, api_key, base_url, "org", credential_id)


def _kept_key(existing: ProviderCredential, base_url: str, secrets: SecretBox) -> str:
    """Editing a custom server with the key field left empty keeps its saved key, so renaming a
    server doesn't silently wipe it. Only for the same address, though: the key was given for
    that server, and reusing it for a new URL would hand it to whoever runs the new one (an
    admin could point the URL at their own server and collect the key)."""
    if base_url != (existing.base_url or "").rstrip("/"):
        raise BadRequest(KEY_FOR_NEW_URL)
    try:
        return secrets.decrypt(existing.encrypted_key)
    except SecretUnreadable as error:
        raise BadRequest("The saved key can't be read (did SECRET_KEY change?). Paste the key again.") from error


async def save_credential(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    connection: ProviderAccess,
    secrets: SecretBox,
    verified_at: datetime,
    member_id: uuid.UUID | None = None,
) -> ProviderCredential:
    """Insert or replace the key. Call only after the key passed the live check.

    Two admins can save the first key for the same built-in provider at the same moment: both
    find no row, both insert, and the unique index (one key per built-in provider per
    organization) refuses the second. That insert runs in a savepoint, so the loser rolls back
    only the insert and updates the winner's row instead (last write wins, as with any replace)
    rather than failing with a 500."""
    target = Target(connection.kind, connection.credential_id if connection.kind == "custom" else None)
    credential = await find_credential(db, org_id, target, member_id=member_id)
    if credential is None:
        credential = ProviderCredential(
            id=connection.credential_id or uuid.uuid4(), org_id=org_id, user_id=member_id, created_by=user_id
        )
        _fill(credential, connection, secrets, verified_at)
        try:
            async with db.begin_nested():
                db.add(credential)
        except IntegrityError:
            credential = await find_credential(db, org_id, target, member_id=member_id)
            if credential is None:  # not the race we know how to settle
                raise
            _fill(credential, connection, secrets, verified_at)
    else:
        _fill(credential, connection, secrets, verified_at)
    await db.flush()
    return credential


def _fill(
    credential: ProviderCredential, connection: ProviderAccess, secrets: SecretBox, verified_at: datetime
) -> None:
    """Every key is encrypted with the current SECRET_KEY, so saving also finishes a rotation."""
    credential.provider = connection.kind
    credential.label = connection.name if connection.kind == "custom" else ""
    credential.base_url = connection.base_url
    credential.encrypted_key = secrets.encrypt(connection.api_key) if connection.api_key else ""
    credential.key_hint = key_hint(connection.api_key)
    credential.status = "ok"
    credential.last_verified_at = verified_at


async def record_check(db: AsyncSession, credential_id: uuid.UUID, *, ok: bool) -> ProviderCredential | None:
    """Save how a key's test went. None if the key was removed meanwhile."""
    await db.execute(
        update(ProviderCredential)
        .where(ProviderCredential.id == credential_id)
        .values(status="ok" if ok else "invalid", last_verified_at=utcnow())
    )
    found: ProviderCredential | None = await db.get(ProviderCredential, credential_id, populate_existing=True)
    return found


async def delete_member_keys(db: AsyncSession, org_id: uuid.UUID, member_id: uuid.UUID) -> None:
    """Someone leaving an organization takes their own keys there with them."""
    await db.execute(
        delete(ProviderCredential).where(ProviderCredential.org_id == org_id, ProviderCredential.user_id == member_id)
    )


async def delete_credential(
    db: AsyncSession, org_id: uuid.UUID, target: Target, *, member_id: uuid.UUID | None = None
) -> uuid.UUID:
    """Remove the organization's key (or, with `member_id`, that member's own). Returns its id."""
    credential = await find_credential(db, org_id, target, member_id=member_id)
    if credential is None:
        raise NotFound(NOT_CONNECTED)
    credential_id = credential.id
    await db.execute(delete(ProviderCredential).where(ProviderCredential.id == credential_id))
    return credential_id

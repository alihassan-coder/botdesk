"""Connections: authorised accounts on connectors (ADR 0010). Who may create, see and disconnect
which (§3), the 5.1 rule for which connection a run's tool call uses, and the audit log (§9).
OAuth's sign-in, token refresh and its lease (§5-§6) live in `oauth_flow.py`.

Secrets go in and out only through the credential vault. Nothing here calls a provider, so no
transaction waits on the network. Every function filters by organization.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from botdesk_plugin_sdk import ApiKeyAuth, PluginManifest
from pydantic import SecretStr
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import BadRequest, Conflict, Forbidden, NotFound
from src.models import AuditEntry, Bot, BotTool, Connection
from src.schemas.connection import ApiKeyConnectionIn
from src.services.credential_vault import CredentialVault, api_key_secret

NOT_FOUND = "Connection not found."
UNKNOWN_CONNECTOR = "There's no such app on this server."
ADMIN_ROLES = ("owner", "admin")


@dataclass(frozen=True)
class Actor:
    """The signed-in member and their role in the organization."""

    org_id: uuid.UUID
    user_id: uuid.UUID
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES


# Who may do what (ADR 0010 §3)


def can_see(actor: Actor, connection: Connection) -> bool:
    """A member-owned connection: its member, and owners/admins (who learn it exists, never its
    secret: no one does). Bot- and org-owned ones: every member."""
    if connection.org_id != actor.org_id:
        return False
    return connection.owner_kind != "member" or connection.owner_user_id == actor.user_id or actor.is_admin


def can_disconnect(actor: Actor, connection: Connection, bot: Bot | None) -> bool:
    if connection.owner_kind == "member":
        return connection.owner_user_id == actor.user_id or actor.is_admin  # admins: for safety
    if connection.owner_kind == "bot":
        return actor.is_admin or (bot is not None and bot.created_by == actor.user_id)
    return actor.is_admin


async def _owner_bot(db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID | None) -> Bot | None:
    if bot_id is None:
        return None
    bot: Bot | None = await db.scalar(select(Bot).where(Bot.id == bot_id, Bot.org_id == org_id))
    return bot


# Reading


async def list_visible(db: AsyncSession, actor: Actor) -> list[Connection]:
    """The organization's connections this member may see, oldest first. Revoked ones included
    (they show as disconnected)."""
    query = select(Connection).where(Connection.org_id == actor.org_id)
    if not actor.is_admin:
        query = query.where(or_(Connection.owner_kind != "member", Connection.owner_user_id == actor.user_id))
    return list(await db.scalars(query.order_by(Connection.created_at, Connection.id)))


async def get_visible(db: AsyncSession, actor: Actor, connection_id: uuid.UUID) -> Connection:
    """404 for another organization's connection and for one this member may not see."""
    connection = await db.get(Connection, connection_id)
    if connection is None or not can_see(actor, connection):
        raise NotFound(NOT_FOUND)
    return connection


# Changing


async def connect_api_key(
    db: AsyncSession, actor: Actor, connector: PluginManifest, body: ApiKeyConnectionIn, vault: CredentialVault
) -> Connection:
    """Create an API-key connection, or replace the key of the same account (same connector,
    owner and label). The caller has found `connector` among the loaded plugins."""
    auth = connector.auth
    if not isinstance(auth, ApiKeyAuth):
        raise BadRequest(f"{connector.name} doesn't connect with an API key.")
    secret = api_key_secret(body.api_key.get_secret_value(), auth)
    owner = await owner_for_create(db, actor, body.owner_kind, body.bot_id)
    label = body.account_label.strip() or connector.name
    return await save_account(
        db,
        actor,
        connector.id,
        owner,
        auth_type="api_key",
        label=label,
        ref=label.casefold(),
        scopes=[],
        save_secret=lambda connection: vault.save(connection, secret),
    )


@dataclass(frozen=True)
class Owner:
    """Whose account a new connection is (ADR 0010 §2): a member's, a bot's, or the organization's."""

    kind: str  # OwnerKind
    user_id: uuid.UUID | None = None
    bot_id: uuid.UUID | None = None


async def save_account(
    db: AsyncSession,
    actor: Actor,
    connector_id: str,
    owner: Owner,
    *,
    auth_type: str,
    label: str,
    ref: str,
    scopes: list[str],
    save_secret: Callable[[Connection], None],
    details: dict[str, Any] | None = None,
) -> Connection:
    """Create a connection, or update the one for the same account (same connector, owner and
    `ref`): connecting an account again is a reconnect, never a second row. `save_secret` puts the
    credential in through the vault, given the existing row when there is one. Audited as
    `connection.created` or `connection.reconnected`."""
    existing = await db.scalar(
        select(Connection).where(
            Connection.org_id == actor.org_id,
            Connection.connector_id == connector_id,
            Connection.owner_kind == owner.kind,
            Connection.owner_user_id.is_(None) if owner.user_id is None else Connection.owner_user_id == owner.user_id,
            Connection.owner_bot_id.is_(None) if owner.bot_id is None else Connection.owner_bot_id == owner.bot_id,
            Connection.account_ref == ref,
        )
    )
    connection = existing or Connection(
        org_id=actor.org_id,
        connector_id=connector_id,
        owner_kind=owner.kind,
        owner_user_id=owner.user_id,
        owner_bot_id=owner.bot_id,
        auth_type=auth_type,
        account_ref=ref,
        created_by=actor.user_id,
    )
    connection.account_label = label
    connection.auth_type = auth_type
    connection.scopes = scopes
    save_secret(connection)
    try:
        async with db.begin_nested():  # two people connecting the same account at once
            db.add(connection)
    except IntegrityError as error:
        raise Conflict("That account was connected a moment ago. Refresh and try again.") from error
    action = "connection.reconnected" if existing else "connection.created"
    audit(
        db,
        actor.org_id,
        actor.user_id,
        action,
        connection,
        {"connector": connector_id, "owner": owner.kind, **(details or {})},
    )
    return connection


async def owner_for_create(db: AsyncSession, actor: Actor, owner_kind: str, bot_id: uuid.UUID | None) -> Owner:
    """The owner of a new connection, if this member may create it (ADR 0010 §3). The same rule
    for API keys, for starting an OAuth sign-in, and again when the sign-in comes back."""
    if owner_kind == "member":
        return Owner("member", user_id=actor.user_id)
    if owner_kind == "org":
        if not actor.is_admin:
            raise Forbidden("Only owners and admins can connect an account for the whole organization.")
        return Owner("org")
    if bot_id is None:
        raise BadRequest("Choose the bot this account is for.")
    bot = await _owner_bot(db, actor.org_id, bot_id)
    if bot is None:
        raise NotFound("Bot not found.")
    if not (actor.is_admin or bot.created_by == actor.user_id):
        raise Forbidden("Only owners, admins and the bot's creator can connect an account for this bot.")
    return Owner("bot", bot_id=bot.id)


async def disconnect(
    db: AsyncSession, actor: Actor, connection_id: uuid.UUID, vault: CredentialVault
) -> tuple[Connection, SecretStr | None]:
    """Forget the credential and mark the connection revoked (the row stays for the audit log).
    Disconnecting an already disconnected connection does nothing.

    Returns the connection and, for OAuth, the token to revoke at the provider: the caller does
    that after committing (`oauth_flow.revoke`), so no transaction waits on the network."""
    connection = await get_visible(db, actor, connection_id)
    bot = await _owner_bot(db, actor.org_id, connection.owner_bot_id)
    if not can_disconnect(actor, connection, bot):
        raise Forbidden("You can't disconnect this account.")
    if connection.status == "revoked":
        return connection, None
    token = vault.revocation_token(connection)
    vault.revoke(connection, reason="Disconnected")
    # Its bindings keep their plugin on, with no account: tools that need one say "connect it first".
    await db.execute(update(BotTool).where(BotTool.connection_id == connection.id).values(connection_id=None))
    await db.flush()
    audit(
        db, actor.org_id, actor.user_id, "connection.disconnected", connection, {"connector": connection.connector_id}
    )
    return connection, token


def audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    connection: Connection,
    details: dict[str, Any],
) -> None:
    """Append one line to the audit log, in the caller's transaction. Never pass a secret."""
    audit_line(db, org_id, actor_user_id, action, connection.id, details)


def audit_line(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    connection_id: uuid.UUID,
    details: dict[str, Any],
) -> None:
    """`audit`, by the connection's id."""
    db.add(
        AuditEntry(
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            target_kind="connection",
            target_id=connection_id,
            details=details,
        )
    )


# Runs


async def for_tool_call(db: AsyncSession, org_id: uuid.UUID, connection_id: uuid.UUID) -> Connection | None:
    """The connection a tool call was given by the run's toolset (`runtime.toolset`), which has
    already decided that the run may use it. None if it's gone or in another organization."""
    connection = await db.get(Connection, connection_id, populate_existing=True)
    return connection if connection is not None and connection.org_id == org_id else None


async def record_use(db: AsyncSession, connection_id: uuid.UUID, *, when: datetime) -> None:
    """A tool call went through this connection: note when. (The call's own record already
    names the connection: `tool_pipeline.record` saves it.)"""
    await db.execute(update(Connection).where(Connection.id == connection_id).values(last_used_at=when))

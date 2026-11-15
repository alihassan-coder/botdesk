"""Connections: authorised accounts on connectors (ADR 0010). Who may create, see and disconnect
which (§3), the 5.1 rule for which connection a run's tool call uses, and the audit log (§9).
Token refresh and its lease (§6) come with OAuth (slice 5.3).

Secrets go in and out only through the credential vault. Nothing here calls a provider, so no
transaction waits on the network. Every function filters by organization.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from botdesk_plugin_sdk import ApiKeyAuth, PluginManifest
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import BadRequest, Conflict, Forbidden, NotFound
from src.models import AuditEntry, Bot, Connection, ToolExecution
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
    if not isinstance(connector.auth, ApiKeyAuth):
        raise BadRequest(f"{connector.name} doesn't connect with an API key.")
    owner_user_id, owner_bot_id = await _owner_for_create(db, actor, body)
    label = body.account_label.strip() or connector.name
    ref = label.casefold()
    existing = await db.scalar(
        select(Connection).where(
            Connection.org_id == actor.org_id,
            Connection.connector_id == connector.id,
            Connection.owner_kind == body.owner_kind,
            Connection.owner_user_id.is_(None) if owner_user_id is None else Connection.owner_user_id == owner_user_id,
            Connection.owner_bot_id.is_(None) if owner_bot_id is None else Connection.owner_bot_id == owner_bot_id,
            Connection.account_ref == ref,
        )
    )
    connection = existing or Connection(
        org_id=actor.org_id,
        connector_id=connector.id,
        owner_kind=body.owner_kind,
        owner_user_id=owner_user_id,
        owner_bot_id=owner_bot_id,
        auth_type="api_key",
        account_ref=ref,
        scopes=[],
        created_by=actor.user_id,
    )
    connection.account_label = label
    vault.save(connection, api_key_secret(body.api_key.get_secret_value(), connector.auth))
    try:
        async with db.begin_nested():  # two people connecting the same account at once
            db.add(connection)
    except IntegrityError as error:
        raise Conflict("That account was connected a moment ago. Refresh and try again.") from error
    action = "connection.reconnected" if existing else "connection.created"
    audit(db, actor.org_id, actor.user_id, action, connection, {"connector": connector.id, "owner": body.owner_kind})
    return connection


async def _owner_for_create(
    db: AsyncSession, actor: Actor, body: ApiKeyConnectionIn
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """(owner_user_id, owner_bot_id) for a new connection, if this member may create it."""
    if body.owner_kind == "member":
        return actor.user_id, None
    if body.owner_kind == "org":
        if not actor.is_admin:
            raise Forbidden("Only owners and admins can connect an account for the whole organization.")
        return None, None
    if body.bot_id is None:
        raise BadRequest("Choose the bot this account is for.")
    bot = await _owner_bot(db, actor.org_id, body.bot_id)
    if bot is None:
        raise NotFound("Bot not found.")
    if not (actor.is_admin or bot.created_by == actor.user_id):
        raise Forbidden("Only owners, admins and the bot's creator can connect an account for this bot.")
    return None, bot.id


async def disconnect(db: AsyncSession, actor: Actor, connection_id: uuid.UUID, vault: CredentialVault) -> None:
    """Forget the credential and mark the connection revoked (the row stays for the audit log).
    Disconnecting an already disconnected connection does nothing."""
    connection = await get_visible(db, actor, connection_id)
    bot = await _owner_bot(db, actor.org_id, connection.owner_bot_id)
    if not can_disconnect(actor, connection, bot):
        raise Forbidden("You can't disconnect this account.")
    if connection.status == "revoked":
        return
    vault.revoke(connection, reason="Disconnected")
    await db.flush()
    audit(
        db, actor.org_id, actor.user_id, "connection.disconnected", connection, {"connector": connection.connector_id}
    )


def audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    connection: Connection,
    details: dict[str, Any],
) -> None:
    """Append one line to the audit log, in the caller's transaction. Never pass a secret."""
    db.add(
        AuditEntry(
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            target_kind="connection",
            target_id=connection.id,
            details=details,
        )
    )


# Runs


async def usable_for_run(
    db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID, connector_id: str
) -> Connection | None:
    """The connection a run of this bot uses for a connector, until bindings arrive (slice 5.2):
    an active connection owned by this bot, else an active one owned by the organization (oldest
    first). Member-owned connections are never used yet: they need the run's requester and a DM
    with that member (ADR 0010 §3), which come with bindings."""
    query = (
        select(Connection)
        .where(
            Connection.org_id == org_id,
            Connection.connector_id == connector_id,
            Connection.status == "active",
            or_(
                (Connection.owner_kind == "bot") & (Connection.owner_bot_id == bot_id),
                Connection.owner_kind == "org",
            ),
        )
        .order_by((Connection.owner_kind == "org").asc(), Connection.created_at, Connection.id)
    )
    connection: Connection | None = (await db.scalars(query.limit(1))).first()
    return connection


async def record_use(
    db: AsyncSession, connection_id: uuid.UUID, *, run_id: uuid.UUID, tool_call_id: str, when: datetime
) -> None:
    """A tool call went through this connection: note when, and put it on the call's record."""
    await db.execute(update(Connection).where(Connection.id == connection_id).values(last_used_at=when))
    await db.execute(
        update(ToolExecution)
        .where(ToolExecution.run_id == run_id, ToolExecution.tool_call_id == tool_call_id)
        .values(connection_id=connection_id)
    )

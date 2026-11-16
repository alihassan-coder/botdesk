"""Bindings: each bot's Tools (slice 5.2). Which plugins a bot may use, and through which
connection. Read by the Tools tab and, through `runtime.toolset`, by every run.

Who may change what (the contract, ADR 0010 §3): any member may switch a plugin on or off (the
same rule as editing a bot). Choosing a connection follows who may use it: a member's own only
by that member; a bot's by owners, admins and the bot's creator; the organization's by owners
and admins. Leaving the connection as it is is never refused. Callers own the transaction.
"""

import uuid
from collections.abc import Iterable, Sequence

from botdesk_plugin_sdk import OAuth2Auth, PluginManifest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import BadRequest, Conflict, Forbidden, NotFound
from src.models import Bot, BotTool, Connection, Run, Thread
from src.plugins.registry import ToolRegistry
from src.schemas.bot_tool import BotToolChange, BotToolOut, BotToolsOut
from src.schemas.plugin import PluginToolOut
from src.services import connection_service
from src.services.connection_service import Actor

UNKNOWN_PLUGIN = "There's no such app on this server."
OTHER_CONNECTOR = "That account is for another app."
DISCONNECTED = "That account was disconnected. Connect it again in Connect apps."
DUPLICATE = "Send each app once."


# Reading


async def bindings_of(db: AsyncSession, bot_id: uuid.UUID) -> dict[str, BotTool]:
    return {row.plugin_id: row for row in await db.scalars(select(BotTool).where(BotTool.bot_id == bot_id))}


def tools_out(registry: ToolRegistry, bindings: dict[str, BotTool]) -> BotToolsOut:
    """One entry per loaded plugin. A plugin with no binding is off, with no connection."""
    return BotToolsOut(plugins=[_plugin_out(plugin, bindings.get(plugin.id)) for plugin in registry.plugins()])


def _plugin_out(plugin: PluginManifest, binding: BotTool | None) -> BotToolOut:
    auth = plugin.auth
    return BotToolOut(
        plugin_id=plugin.id,
        name=plugin.name,
        description=plugin.description,
        auth_type=None if auth is None else "oauth2" if isinstance(auth, OAuth2Auth) else "api_key",
        enabled=binding.enabled if binding else False,
        connection_id=binding.connection_id if binding else None,
        tools=[
            PluginToolOut(
                name=f"{plugin.id}.{tool.name}", title=tool.title, description=tool.description, risk=tool.risk
            )
            for tool in plugin.tools
        ],
    )


async def run_bindings(
    db: AsyncSession, run_id: uuid.UUID
) -> tuple[Run, Thread, list[tuple[BotTool, Connection | None]]] | None:
    """A run, its chat, and its bot's enabled bindings with their connections (two queries).
    None when the run is gone."""
    row = (
        await db.execute(select(Run, Thread).join(Thread, Thread.id == Run.thread_id).where(Run.id == run_id))
    ).first()
    if row is None:
        return None
    run, thread = row
    bindings = await db.execute(
        select(BotTool, Connection)
        .outerjoin(Connection, (Connection.id == BotTool.connection_id) & (Connection.org_id == BotTool.org_id))
        .where(BotTool.bot_id == run.bot_id, BotTool.enabled.is_(True))
    )
    return run, thread, [(binding, connection) for binding, connection in bindings.tuples()]


# Changing


def add_defaults(db: AsyncSession, bot: Bot, plugins: Iterable[PluginManifest]) -> None:
    """A new bot's bindings: every loaded plugin that doesn't sign in with OAuth, switched on,
    with no connection yet (an API-key plugin's tools that need no key work at once)."""
    db.add_all(
        BotTool(org_id=bot.org_id, bot_id=bot.id, plugin_id=plugin.id, enabled=True, created_by=bot.created_by)
        for plugin in plugins
        if not isinstance(plugin.auth, OAuth2Auth)
    )


async def update_bindings(
    db: AsyncSession, actor: Actor, bot: Bot, registry: ToolRegistry, changes: Sequence[BotToolChange]
) -> dict[str, BotTool]:
    """Apply the changes sent (other plugins stay as they are), with `connection.bound` and
    `connection.unbound` audit lines. Checks everything before changing anything."""
    if len({change.plugin_id for change in changes}) != len(changes):
        raise BadRequest(DUPLICATE)
    for change in changes:
        if registry.plugin(change.plugin_id) is None:
            raise NotFound(UNKNOWN_PLUGIN)
    current = await bindings_of(db, bot.id)
    moved = [change for change in changes if change.connection_id != _connection_of(current.get(change.plugin_id))]
    outgoing = {_connection_of(current.get(change.plugin_id)) for change in moved} - {None}
    incoming = {change.connection_id for change in moved} - {None}
    found = await _connections(db, actor.org_id, outgoing | incoming)  # type: ignore[arg-type]
    for change in moved:
        before = _connection_of(current.get(change.plugin_id))
        if before is not None:
            _check_can_unbind(actor, bot, found.get(before))
        if change.connection_id is not None:
            _check_can_bind(actor, bot, change.plugin_id, found.get(change.connection_id))

    for change in changes:
        binding = current.get(change.plugin_id)
        before = _connection_of(binding)
        if binding is None:
            binding = BotTool(org_id=bot.org_id, bot_id=bot.id, plugin_id=change.plugin_id, created_by=actor.user_id)
            db.add(binding)
            current[change.plugin_id] = binding
        binding.enabled = change.enabled
        binding.connection_id = change.connection_id
        if before != change.connection_id:
            details = {"connector": change.plugin_id, "botId": str(bot.id)}
            if before is not None:
                connection_service.audit_line(db, actor.org_id, actor.user_id, "connection.unbound", before, details)
            if change.connection_id is not None:
                connection_service.audit_line(
                    db, actor.org_id, actor.user_id, "connection.bound", change.connection_id, details
                )
    try:
        await db.flush()
    except IntegrityError as error:  # two people adding the same plugin at once
        raise Conflict("This bot's Tools changed a moment ago. Refresh and try again.") from error
    return current


def _connection_of(binding: BotTool | None) -> uuid.UUID | None:
    return binding.connection_id if binding else None


async def _connections(db: AsyncSession, org_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Connection]:
    if not ids:
        return {}
    rows = await db.scalars(select(Connection).where(Connection.org_id == org_id, Connection.id.in_(ids)))
    return {row.id: row for row in rows}


def _check_can_unbind(actor: Actor, bot: Bot, connection: Connection | None) -> None:
    """Replacing or clearing the account a bot works through needs the right to that account,
    so a member can't take an app away from everyone else's runs. Owners and admins always may
    (offboarding); an account that's gone or disconnected holds nothing and is free to replace."""
    if connection is None or connection.status == "revoked" or actor.is_admin:
        return
    if connection.owner_kind == "member" and connection.owner_user_id == actor.user_id:
        return
    if connection.owner_kind == "bot" and bot.created_by == actor.user_id:
        return
    raise Forbidden("Only whoever may choose this account (or an owner or admin) can change it.")


def _check_can_bind(actor: Actor, bot: Bot, plugin_id: str, connection: Connection | None) -> None:
    if connection is None or not connection_service.can_see(actor, connection):
        raise NotFound(connection_service.NOT_FOUND)
    if connection.connector_id != plugin_id:
        raise BadRequest(OTHER_CONNECTOR)
    if connection.status == "revoked":
        raise BadRequest(DISCONNECTED)
    if connection.owner_kind == "member":
        if connection.owner_user_id != actor.user_id:
            raise Forbidden("Only its member can give a bot their own account.")
    elif connection.owner_kind == "bot":
        if connection.owner_bot_id != bot.id:
            raise BadRequest("That account belongs to another bot.")
        if not (actor.is_admin or bot.created_by == actor.user_id):
            raise Forbidden("Only owners, admins and the bot's creator can choose this bot's own account.")
    elif not actor.is_admin:
        raise Forbidden("Only owners and admins can give a bot the organization's account.")

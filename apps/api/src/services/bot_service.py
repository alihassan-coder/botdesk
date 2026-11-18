"""Bots in an organization: hire (create), list, edit, remove."""

import uuid
from collections.abc import Iterable
from typing import cast

from botdesk_plugin_sdk import PluginManifest
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFound
from src.core.handles import handle_prefix, make_handle
from src.models import Bot, Organization, Routine, Run, Thread, ThreadParticipant
from src.models.bot import SecurityLevel
from src.models.run import FINISHED_STATUSES
from src.runtime.policy import looser_than, strictest_level
from src.schemas.bot import BotIn, BotUpdate
from src.services import binding_service
from src.services.organization_service import require_under_ceiling

# What a routine whose bot was removed says (it stays, switched off).
BOT_REMOVED = "Its bot was removed."


async def list_bots(db: AsyncSession, org_id: uuid.UUID) -> list[Bot]:
    return list(await db.scalars(select(Bot).where(Bot.org_id == org_id).order_by(Bot.created_at)))


async def get_bot(db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID) -> Bot:
    """The bot, if it belongs to this organization."""
    bot = await db.get(Bot, bot_id)
    if bot is None or bot.org_id != org_id:
        raise NotFound("Bot not found.")
    return bot


async def _taken_handles(
    db: AsyncSession, org_id: uuid.UUID, name: str, *, except_bot: uuid.UUID | None = None
) -> set[str]:
    query = select(Bot.handle).where(Bot.org_id == org_id, Bot.handle.like(handle_prefix(name)))
    if except_bot:
        query = query.where(Bot.id != except_bot)
    return set(await db.scalars(query))


async def create_bot(
    db: AsyncSession, *, org: Organization, created_by: uuid.UUID, data: BotIn, plugins: Iterable[PluginManifest]
) -> Bot:
    """A bot hired without a security level gets the organization's default for new bots (kept
    under the ceiling); one hired with a level above the ceiling isn't hired. It gets a binding
    for each of `plugins` (the loaded ones) that doesn't sign in with OAuth."""
    if data.security_level:
        require_under_ceiling(org, data.security_level)
    ceiling = cast("SecurityLevel", org.max_security_level)
    level = data.security_level or strictest_level(cast("SecurityLevel", org.default_security_level), ceiling)
    handle = make_handle(data.name, await _taken_handles(db, org.id, data.name))
    fields = data.model_dump() | {"security_level": level}
    bot = Bot(**fields, org_id=org.id, handle=handle, created_by=created_by)
    db.add(bot)
    await db.flush()
    binding_service.add_defaults(db, bot, plugins)
    await db.flush()
    return bot


async def update_bot(db: AsyncSession, org: Organization, bot: Bot, changes: BotUpdate) -> Bot:
    """Renaming a bot gives it a matching @handle (unique in the organization). Its level may not
    be raised above the organization's ceiling. Lowering it is always fine, and so is sending back
    the level it already has (the editor sends every field), even if the ceiling was lowered
    under it since."""
    current = cast("SecurityLevel", bot.security_level)
    if changes.security_level and looser_than(changes.security_level, current):
        require_under_ceiling(org, changes.security_level)
    fields = changes.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if fields["name"] != bot.name:
            bot.handle = make_handle(
                fields["name"], await _taken_handles(db, bot.org_id, fields["name"], except_bot=bot.id)
            )
    for field, value in fields.items():
        setattr(bot, field, value)
    return bot


async def runs_going_with(db: AsyncSession, bot_id: uuid.UUID) -> list[uuid.UUID]:
    """The live runs that removing this bot would delete: its own, and every run in its DMs
    (guests' too). The caller stops them first, so none carries on into rows that are gone."""
    in_its_dms = select(Thread.id).where(Thread.bot_id == bot_id)
    query = (
        select(Run.id)
        .where(Run.status.not_in(FINISHED_STATUSES), or_(Run.bot_id == bot_id, Run.thread_id.in_(in_its_dms)))
        .order_by(Run.created_at, Run.id)
    )
    return list(await db.scalars(query))


async def delete_bot(db: AsyncSession, bot: Bot) -> None:
    """Its DMs and runs go with it (stop them first: `runs_going_with`, and end its handoffs with
    `task_service.bot_removed`), and it leaves its groups. Tasks it was part of stay, without it.
    Its routines stay, switched off, saying why."""
    await db.execute(
        update(Routine)
        .where(Routine.bot_id == bot.id)
        .values(enabled=False, next_run_at=None, disabled_reason=BOT_REMOVED)
    )
    # It leaves its groups (a group's lead points at it with ON DELETE SET NULL). Those groups are
    # locked first, in id order, as a group change locks its group before changing who's in it,
    # so the two wait for each other in turn instead of in a circle (a deadlock on Postgres).
    in_its_groups = select(ThreadParticipant.thread_id).where(
        ThreadParticipant.participant_type == "bot", ThreadParticipant.participant_id == bot.id
    )
    groups = select(Thread.id).where(
        Thread.kind == "group", or_(Thread.id.in_(in_its_groups), Thread.lead_bot_id == bot.id)
    )
    await db.execute(groups.order_by(Thread.id).with_for_update())
    await db.execute(
        delete(ThreadParticipant).where(
            ThreadParticipant.participant_type == "bot", ThreadParticipant.participant_id == bot.id
        )
    )
    await db.delete(bot)

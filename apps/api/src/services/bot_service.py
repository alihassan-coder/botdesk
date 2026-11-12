"""Bots in an organization: hire (create), list, edit, remove."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFound
from src.core.handles import make_handle
from src.models import Bot
from src.schemas.bot import BotIn, BotUpdate


async def list_bots(db: AsyncSession, org_id: uuid.UUID) -> list[Bot]:
    return list(await db.scalars(select(Bot).where(Bot.org_id == org_id).order_by(Bot.created_at)))


async def get_bot(db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID) -> Bot:
    """The bot, if it belongs to this organization."""
    bot = await db.get(Bot, bot_id)
    if bot is None or bot.org_id != org_id:
        raise NotFound("Bot not found.")
    return bot


async def _taken_handles(db: AsyncSession, org_id: uuid.UUID, *, except_bot: uuid.UUID | None = None) -> set[str]:
    query = select(Bot.handle).where(Bot.org_id == org_id)
    if except_bot:
        query = query.where(Bot.id != except_bot)
    return set(await db.scalars(query))


async def create_bot(db: AsyncSession, *, org_id: uuid.UUID, created_by: uuid.UUID, data: BotIn) -> Bot:
    handle = make_handle(data.name, await _taken_handles(db, org_id))
    bot = Bot(**data.model_dump(), org_id=org_id, handle=handle, created_by=created_by)
    db.add(bot)
    await db.flush()
    return bot


async def update_bot(db: AsyncSession, bot: Bot, changes: BotUpdate) -> Bot:
    """Renaming a bot gives it a matching @handle (unique in the organization)."""
    fields = changes.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if fields["name"] != bot.name:
            bot.handle = make_handle(fields["name"], await _taken_handles(db, bot.org_id, except_bot=bot.id))
    for field, value in fields.items():
        setattr(bot, field, value)
    return bot


async def delete_bot(db: AsyncSession, bot: Bot) -> None:
    await db.delete(bot)

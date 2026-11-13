"""Handles bot requests. Any member can hire and edit bots; removing one takes an admin.
A bot's model must belong to a connected provider (Settings → Models & keys, or the server's env)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.schemas.bot import BotIn, BotOut, BotUpdate
from src.services import bot_service, provider_service


async def list_bots(db: AsyncSession, access: Access) -> list[BotOut]:
    return [BotOut.model_validate(bot) for bot in await bot_service.list_bots(db, access.org.id)]


async def get_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> BotOut:
    return BotOut.model_validate(await bot_service.get_bot(db, access.org.id, bot_id))


async def create_bot(db: AsyncSession, access: Access, body: BotIn, settings: Settings) -> BotOut:
    await provider_service.require_usable_model(db, access.org.id, body.model_id, settings)
    bot = await bot_service.create_bot(db, org_id=access.org.id, created_by=access.user.id, data=body)
    await db.commit()
    return BotOut.model_validate(bot)


async def update_bot(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, body: BotUpdate, settings: Settings
) -> BotOut:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    if body.model_id and body.model_id != bot.model_id:  # a model picked earlier stays valid
        await provider_service.require_usable_model(db, access.org.id, body.model_id, settings)
    await bot_service.update_bot(db, bot, body)
    await db.commit()
    return BotOut.model_validate(bot)


async def delete_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> None:
    access.require_admin()
    await bot_service.delete_bot(db, await bot_service.get_bot(db, access.org.id, bot_id))
    await db.commit()

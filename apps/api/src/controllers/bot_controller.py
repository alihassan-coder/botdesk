"""Handles bot requests. Any member can hire and edit bots; removing one takes an admin."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.schemas.bot import BotIn, BotOut, BotUpdate
from src.services import bot_service


async def list_bots(db: AsyncSession, access: Access) -> list[BotOut]:
    return [BotOut.model_validate(bot) for bot in await bot_service.list_bots(db, access.org.id)]


async def get_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> BotOut:
    return BotOut.model_validate(await bot_service.get_bot(db, access.org.id, bot_id))


async def create_bot(db: AsyncSession, access: Access, body: BotIn) -> BotOut:
    bot = await bot_service.create_bot(db, org_id=access.org.id, created_by=access.user.id, data=body)
    await db.commit()
    return BotOut.model_validate(bot)


async def update_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID, body: BotUpdate) -> BotOut:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    await bot_service.update_bot(db, bot, body)
    await db.commit()
    return BotOut.model_validate(bot)


async def delete_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> None:
    access.require_admin()
    await bot_service.delete_bot(db, await bot_service.get_bot(db, access.org.id, bot_id))
    await db.commit()

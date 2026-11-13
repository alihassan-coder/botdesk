"""Handles usage requests. Any member can see what the organization and its bots spent."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.database import utcnow
from src.schemas.usage import BotUsageOut, UsageOut
from src.services import bot_service, usage_service


async def org_usage(db: AsyncSession, access: Access, days: int) -> UsageOut:
    bots = await bot_service.list_bots(db, access.org.id)
    return await usage_service.org_report(db, access.org, bots, days, utcnow())


async def bot_usage(db: AsyncSession, access: Access, bot_id: uuid.UUID, days: int) -> BotUsageOut:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    return await usage_service.bot_report(db, access.org.id, bot, days, utcnow())

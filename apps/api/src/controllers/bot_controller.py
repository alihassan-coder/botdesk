"""Handles bot requests. Any member can hire and edit bots; removing one, or changing its monthly
budget, takes an admin (members may hire a bot with a budget up to the default). A bot's model must
belong to a connected provider (Settings → Models & keys, or the server's env)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.core.errors import Forbidden
from src.schemas.bot import BotIn, BotOut, BotUpdate
from src.services import bot_service, provider_service


async def list_bots(db: AsyncSession, access: Access) -> list[BotOut]:
    return [BotOut.model_validate(bot) for bot in await bot_service.list_bots(db, access.org.id)]


async def get_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> BotOut:
    return BotOut.model_validate(await bot_service.get_bot(db, access.org.id, bot_id))


BUDGET_ADMINS_ONLY = "Only owners and admins can change budgets."
DEFAULT_BOT_BUDGET_USD: int = BotIn.model_fields["monthly_budget_usd"].default


def _is_admin(access: Access) -> bool:
    return access.role in ("owner", "admin")


async def create_bot(db: AsyncSession, access: Access, body: BotIn, settings: Settings) -> BotOut:
    # Budgets are money. A member hiring a bot may pick a budget up to the default (templates
    # come with smaller ones), but not a bigger one, and not 0 (no limit).
    if not _is_admin(access) and not 0 < body.monthly_budget_usd <= DEFAULT_BOT_BUDGET_USD:
        raise Forbidden(BUDGET_ADMINS_ONLY)
    await provider_service.require_usable_model(db, access.org.id, body.model_id, settings)
    bot = await bot_service.create_bot(db, org_id=access.org.id, created_by=access.user.id, data=body)
    await db.commit()
    return BotOut.model_validate(bot)


async def update_bot(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, body: BotUpdate, settings: Settings
) -> BotOut:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    budget = body.monthly_budget_usd
    if budget is not None and budget != bot.monthly_budget_usd and not _is_admin(access):
        raise Forbidden(BUDGET_ADMINS_ONLY)
    if body.model_id and body.model_id != bot.model_id:  # a model picked earlier stays valid
        await provider_service.require_usable_model(db, access.org.id, body.model_id, settings)
    await bot_service.update_bot(db, bot, body)
    await db.commit()
    return BotOut.model_validate(bot)


async def delete_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> None:
    access.require_admin()
    await bot_service.delete_bot(db, await bot_service.get_bot(db, access.org.id, bot_id))
    await db.commit()

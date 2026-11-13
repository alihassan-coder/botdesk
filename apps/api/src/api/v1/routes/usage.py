import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.api.deps import Db, OrgAccess
from src.controllers import usage_controller
from src.schemas.usage import BotUsageOut, UsageOut
from src.services.usage_service import MAX_DAYS

router = APIRouter(prefix="/orgs/{org_id}", tags=["usage"])

Days = Annotated[int, Query(ge=1, le=MAX_DAYS, description="How many UTC days of daily totals, today included.")]


@router.get("/usage")
async def org_usage(access: OrgAccess, db: Db, days: Days = 14) -> UsageOut:
    """Daily spend, this month's total, and each bot's spend against its budget. Any member."""
    return await usage_controller.org_usage(db, access, days)


@router.get("/bots/{bot_id}/usage")
async def bot_usage(bot_id: uuid.UUID, access: OrgAccess, db: Db, days: Days = 14) -> BotUsageOut:
    """One bot's spend this month against its budget, with daily totals. Any member."""
    return await usage_controller.bot_usage(db, access, bot_id, days)

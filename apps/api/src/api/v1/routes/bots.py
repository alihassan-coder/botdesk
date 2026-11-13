import uuid

from fastapi import APIRouter, BackgroundTasks, status

from src.api.deps import AppSettings, Db, OrgAccess, Runs
from src.controllers import bot_controller
from src.schemas.bot import BotIn, BotOut, BotUpdate

router = APIRouter(prefix="/orgs/{org_id}/bots", tags=["bots"])


@router.get("")
async def list_bots(access: OrgAccess, db: Db) -> list[BotOut]:
    return await bot_controller.list_bots(db, access)


def _warm_price(background: BackgroundTasks, runs: Runs, access: OrgAccess, bot: BotOut) -> None:
    """OpenRouter's prices come from its model list: fetch it after the response, not in the bot's first run."""
    if bot.model_id.startswith("openrouter:"):
        background.add_task(runs.warm_price, access.org.id, bot.model_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_bot(
    body: BotIn, access: OrgAccess, db: Db, settings: AppSettings, runs: Runs, background: BackgroundTasks
) -> BotOut:
    """Hire a bot. Its @handle comes from its name. A `modelId` must name a connected provider.
    Only owners and admins may set a budget other than the default."""
    bot = await bot_controller.create_bot(db, access, body, settings)
    _warm_price(background, runs, access, bot)
    return bot


@router.get("/{bot_id}")
async def get_bot(bot_id: uuid.UUID, access: OrgAccess, db: Db) -> BotOut:
    return await bot_controller.get_bot(db, access, bot_id)


@router.patch("/{bot_id}")
async def update_bot(
    bot_id: uuid.UUID,
    body: BotUpdate,
    access: OrgAccess,
    db: Db,
    settings: AppSettings,
    runs: Runs,
    background: BackgroundTasks,
) -> BotOut:
    """Only the fields sent change. Changing `monthlyBudgetUsd` takes an owner or admin."""
    bot = await bot_controller.update_bot(db, access, bot_id, body, settings)
    if body.model_id:
        _warm_price(background, runs, access, bot)
    return bot


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(bot_id: uuid.UUID, access: OrgAccess, db: Db) -> None:
    """Remove a bot. Owners and admins only."""
    await bot_controller.delete_bot(db, access, bot_id)

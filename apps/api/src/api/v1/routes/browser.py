import uuid

from fastapi import APIRouter, Response, status

from src.api.deps import AppSettings, Db, OrgAccess, Runs
from src.controllers import browser_controller
from src.schemas.browser import BrowserOut, PersonInputIn

router = APIRouter(prefix="/orgs/{org_id}/bots/{bot_id}/browser", tags=["browser"])


@router.get("")
async def browser_state(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs, settings: AppSettings) -> BrowserOut:
    """Whether the bot's browser is open, and on which page."""
    return await browser_controller.state(db, access, bot_id, runs, settings)


@router.get("/screen")
async def browser_screen(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs, settings: AppSettings) -> Response:
    """What the bot's browser shows now (JPEG). The live view asks about once a second."""
    picture = await browser_controller.screen(db, access, bot_id, runs, settings)
    return Response(content=picture, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/input")
async def browser_input(
    bot_id: uuid.UUID, body: PersonInputIn, access: OrgAccess, db: Db, runs: Runs, settings: AppSettings
) -> BrowserOut:
    """Take over: click (page pixels), type, press a key, scroll, or open an address in the bot's
    browser, for example to sign in. What you type goes to the page; BotDesk never stores it."""
    return await browser_controller.take_over(db, access, bot_id, body, runs, settings)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def forget_sign_ins(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs, settings: AppSettings) -> None:
    """Close the bot's browser and forget every site it was signed in to."""
    await browser_controller.forget(db, access, bot_id, runs, settings)

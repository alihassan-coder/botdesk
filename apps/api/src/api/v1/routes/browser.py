import uuid

from fastapi import APIRouter, Response, status

from src.api.deps import AppSettings, Db, OrgAccess, Outbound, Runs, Vault
from src.controllers import browser_controller
from src.schemas.browser import BrowserOut, BrowserProviderIn, BrowserProviderOut, PersonInputIn

router = APIRouter(prefix="/orgs/{org_id}/bots/{bot_id}/browser", tags=["browser"])
provider_router = APIRouter(prefix="/orgs/{org_id}", tags=["browser"])


@provider_router.get("/browser-provider")
async def get_browser_provider(access: OrgAccess, db: Db, settings: AppSettings) -> BrowserProviderOut:
    """Where the organization's bots get a browser: Local (this server) or a cloud provider."""
    return await browser_controller.get_provider(db, access, settings)


@provider_router.put("/browser-provider")
async def choose_browser_provider(
    body: BrowserProviderIn,
    access: OrgAccess,
    db: Db,
    runs: Runs,
    settings: AppSettings,
    vault: Vault,
    outbound: Outbound,
) -> BrowserProviderOut:
    """Choose it (owners and admins): `{provider: "local"}`, or `{provider: "steel" | "browserbase" |
    "kernel", apiKey, projectId?}`. A cloud provider is checked by starting and stopping a browser
    there (a few seconds of its browser time). Leave `apiKey` out to keep the saved one."""
    return await browser_controller.choose_provider(
        db, access, body, runs=runs, settings=settings, vault=vault, transport=outbound
    )


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
    bot_id: uuid.UUID, body: PersonInputIn, access: OrgAccess, db: Db, runs: Runs, settings: AppSettings, vault: Vault
) -> BrowserOut:
    """Take over: click (page pixels), type, press a key, scroll, or open an address in the bot's
    browser, for example to sign in. What you type goes to the page; BotDesk never stores it.
    Opening starts the browser where the organization's provider is."""
    return await browser_controller.take_over(db, access, bot_id, body, runs, settings, vault)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def forget_sign_ins(
    bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs, settings: AppSettings, vault: Vault, outbound: Outbound
) -> None:
    """Close the bot's browser and forget every site it was signed in to (here and at cloud providers)."""
    await browser_controller.forget(db, access, bot_id, runs, settings, vault, outbound)

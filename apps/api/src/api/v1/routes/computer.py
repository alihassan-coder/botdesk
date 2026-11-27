import uuid

from fastapi import APIRouter, Response, status

from src.api.deps import AppSettings, Db, OrgAccess, Outbound, Runs, Vault
from src.controllers import computer_controller
from src.schemas.computer import ComputerInputIn, ComputerOut, ComputerProviderIn, ComputerProviderOut

router = APIRouter(prefix="/orgs/{org_id}/bots/{bot_id}/computer", tags=["computer"])
provider_router = APIRouter(prefix="/orgs/{org_id}", tags=["computer"])


@provider_router.get("/computer-provider")
async def get_computer_provider(access: OrgAccess, db: Db) -> ComputerProviderOut:
    """Where the organization's bots get a cloud computer: Orgo with its key, or none."""
    return await computer_controller.get_provider(db, access)


@provider_router.put("/computer-provider")
async def choose_computer_provider(
    body: ComputerProviderIn, access: OrgAccess, db: Db, settings: AppSettings, vault: Vault, outbound: Outbound
) -> ComputerProviderOut:
    """Owners and admins: `{provider: "orgo", apiKey}`. The key is checked live at Orgo and the
    bots' computers go in its workspace "BotDesk" (made if missing). Leave `apiKey` out to check
    the saved key again."""
    return await computer_controller.choose_provider(
        db, access, body, settings=settings, vault=vault, transport=outbound
    )


@provider_router.delete("/computer-provider", status_code=status.HTTP_204_NO_CONTENT)
async def remove_computer_provider(access: OrgAccess, db: Db, runs: Runs) -> None:
    """Owners and admins: stop the bots' computers (best effort), then forget the key."""
    await computer_controller.remove_provider(db, access, runs)


@router.get("")
async def computer_state(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> ComputerOut:
    """The bot's computer: none yet, starting, running (with its apps and preview links)…"""
    return await computer_controller.state(db, access, bot_id, runs)


@router.post("/start")
async def start_computer(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> ComputerOut:
    """Make it (first time) or start it. Answers at once (creating or starting); then poll."""
    return await computer_controller.start(db, access, bot_id, runs)


@router.post("/stop")
async def stop_computer(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> ComputerOut:
    """Stop it: its disk is kept, and its running time is recorded as usage."""
    return await computer_controller.stop(db, access, bot_id, runs)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_computer(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> None:
    """Delete it at Orgo with everything on it (the bot's next use makes a new one)."""
    await computer_controller.delete(db, access, bot_id, runs)


@router.get("/screen")
async def computer_screen(bot_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> Response:
    """What the computer shows now (JPEG). The live view asks about once a second; 409 when it
    isn't running."""
    picture = await computer_controller.screen(db, access, bot_id, runs)
    return Response(content=picture, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/input", status_code=status.HTTP_204_NO_CONTENT)
async def computer_input(bot_id: uuid.UUID, body: ComputerInputIn, access: OrgAccess, db: Db, runs: Runs) -> None:
    """Take over: `{kind: "click" | "double_click" | "right_click", x, y}`, `{kind: "type", text}`,
    `{kind: "key", key}` (Enter, Tab, Escape, BackSpace, Delete, arrows, Home, End, Page_Up,
    Page_Down, ctrl+c, ctrl+v, ctrl+a, ctrl+l) or `{kind: "scroll", direction, x?, y?}`."""
    await computer_controller.take_over(db, access, bot_id, body, runs)

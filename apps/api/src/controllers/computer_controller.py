"""Bots' cloud computers for people (ADR 0020 §1, §3, §5): the organization's Orgo key, and each
bot's computer in its Computer tab: its state, start and stop, delete, the live screen and taking
over. Saving or removing the key takes an owner or admin. Watching takes any member who can see
the bot; starting, stopping, deleting and taking over take whoever may edit it (any member, as
editing a bot). The Orgo key and the computer's root password never leave the API.
"""

import uuid
from collections.abc import Awaitable
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.computers.base import ComputerError, ComputerProvider, Gone, MayHaveRun, NotRunning
from src.core.config import Settings
from src.core.errors import BadRequest, Conflict
from src.runtime.runner import RunManager
from src.schemas.computer import KEYS, ComputerInputIn, ComputerOut, ComputerProviderIn, ComputerProviderOut
from src.services import bot_service, computer_service
from src.services.computer_service import GONE_NOW, NOT_FOUND_NOW, NOT_RUNNING, Computers
from src.services.credential_vault import CredentialVault

SCREEN_QUALITY = 60
SCROLL_CLICKS = 3
STILL_ON = (
    "These computers are still on at Orgo, so the key stays: {names}. Try again in a minute, or "
    "stop them at orgo.ai first."
)
OLD_ACCOUNT_ON = (
    "These computers at the old Orgo account couldn't be stopped, so the old key stays: {names}. "
    "Try again in a minute, or stop them at orgo.ai first."
)


# The organization's provider


async def get_provider(db: AsyncSession, access: Access) -> ComputerProviderOut:
    row = await computer_service.find_provider(db, access.org.id)
    await db.commit()
    return computer_service.provider_view(row)


async def choose_provider(
    db: AsyncSession,
    access: Access,
    body: ComputerProviderIn,
    *,
    runs: RunManager,
    settings: Settings,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None,
) -> ComputerProviderOut:
    """The key is checked live, with no transaction open. Another Orgo account than before: the
    bots' computers there are stopped (and removed bots' deleted) with the old key first, or the
    new key isn't saved (409)."""
    access.require_admin()
    existing = await computer_service.find_provider(db, access.org.id)
    key = computer_service.key_to_check(existing, body, vault)
    old_key = computer_service.key_of(existing, vault) if existing is not None else None
    old_workspace = existing.config.get("workspace_id") if existing is not None else None
    await db.commit()  # nothing held open while Orgo is called
    workspace_id = await computer_service.check_key(key, settings, transport)
    if old_key is not None and old_workspace != workspace_id:
        old = computer_service.provider_for(old_key, settings, transport)
        still_on = await runs.computers.leave_workspace(access.org.id, old)
        if still_on:
            raise Conflict(OLD_ACCOUNT_ON.format(names=", ".join(still_on)))
    row = computer_service.save_provider(
        db,
        existing=await computer_service.find_provider(db, access.org.id),
        org_id=access.org.id,
        user_id=access.user.id,
        key=key,
        workspace_id=workspace_id,
        vault=vault,
    )
    await db.commit()
    return computer_service.provider_view(row)


async def remove_provider(db: AsyncSession, access: Access, runs: RunManager) -> None:
    """The bots' computers are stopped first, and removed bots' deleted; while any is still on at
    Orgo the key stays (409), so none keeps running where BotDesk can't reach it. Stopped ones'
    rows stay: the same key again finds them; another account's computers are made anew."""
    access.require_admin()
    await db.commit()  # nothing held open while Orgo is called
    still_on = await runs.computers.release_all(access.org.id)
    if still_on:
        raise Conflict(STILL_ON.format(names=", ".join(still_on)))
    row = await computer_service.find_provider(db, access.org.id)
    if row is not None:
        await db.delete(row)
    await db.commit()


# A bot's computer


async def state(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager) -> ComputerOut:
    await _bot(db, access, bot_id)
    return await runs.computers.view(access.org.id, bot_id)


async def start(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager) -> ComputerOut:
    await _bot(db, access, bot_id)
    await _call(runs.computers, access, runs.computers.start_soon(access.org.id, bot_id))
    return await runs.computers.view(access.org.id, bot_id)


async def stop(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager) -> ComputerOut:
    await _bot(db, access, bot_id)
    await _call(runs.computers, access, runs.computers.stop(access.org.id, bot_id))
    return await runs.computers.view(access.org.id, bot_id)


async def delete(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager) -> None:
    await _bot(db, access, bot_id)
    await _call(runs.computers, access, runs.computers.delete(access.org.id, bot_id))


async def screen(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager) -> bytes:
    """Orgo's screenshot as a JPEG (full size). Watching keeps the computer from its idle stop."""
    await _bot(db, access, bot_id)
    computers = runs.computers
    provider, remote_id = await _call(computers, access, computers.running(access.org.id, bot_id))
    picture = await _call(
        computers,
        access,
        provider.screenshot(remote_id, image="jpeg", quality=SCREEN_QUALITY),
        on=(bot_id, provider, remote_id),
    )
    await computers.touch(bot_id)
    return picture


async def take_over(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, body: ComputerInputIn, runs: RunManager
) -> None:
    """A person's click, text, key or scroll, through Orgo. What's typed is never stored."""
    await _bot(db, access, bot_id)
    computers = runs.computers
    provider, remote_id = await _call(computers, access, computers.running(access.org.id, bot_id))
    x, y = body.x or 0, body.y or 0
    match body.kind:
        case "click" | "double_click" | "right_click":
            button: Literal["left", "right"] = "right" if body.kind == "right_click" else "left"
            work = provider.click(remote_id, x, y, button=button, double=body.kind == "double_click")
        case "type":
            work = provider.type(remote_id, body.text or "")
        case "key":
            work = provider.key(remote_id, KEYS[body.key or "Enter"])
        case "scroll":
            # Orgo moves the pointer there first; without a point, the middle of a 1280x720 screen.
            point = (x, y) if body.x is not None and body.y is not None else (640, 360)
            work = provider.scroll(remote_id, *point, direction=body.direction or "down", amount=SCROLL_CLICKS)
    await _call(computers, access, work, on=(bot_id, provider, remote_id))
    await computers.touch(bot_id, force=True)


async def _bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> None:
    await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another organization's bot
    await db.commit()  # nothing held open while Orgo is called


async def _call[T](
    computers: Computers,
    access: Access,
    work: Awaitable[T],
    *,
    on: tuple[uuid.UUID, ComputerProvider, str] | None = None,
) -> T:
    """Orgo's refusals as 400s with their message; not running as 409. `on`: the bot's computer
    the call works on. Orgo saying it isn't running marks it stopped; a 404 forgets it once Orgo
    confirms the computer itself is gone (the next start makes a new one)."""
    try:
        async with computers.watching(access.org.id):
            return await work
    except NotRunning:
        if on is not None:
            await computers.mark_stopped(on[0])
        raise Conflict(NOT_RUNNING) from None
    except Gone:
        if on is not None and await computers.confirm_gone(*on):
            raise Conflict(GONE_NOW) from None
        raise BadRequest(NOT_FOUND_NOW) from None
    except (ComputerError, MayHaveRun) as refused:
        raise BadRequest(str(refused)) from None

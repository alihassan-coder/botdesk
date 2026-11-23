"""Bots' browsers for people (ADR 0017 §2, §5): the organization's browser provider, and watching
and taking over a bot's browser. Any member may take over: a bot's browser is bot-owned, like
its own mailbox, so whoever can talk to the bot can sign it in somewhere. Choosing the provider
takes an owner or admin.

Take over works where the bot's browser runs: in the API process (WORKER_MODE=embedded, the
default). With a separate worker the browser lives there, so this says it isn't available.
"""

import uuid
from collections.abc import Awaitable

import httpx
from botdesk_plugin_sdk import NotDone
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.browser.browsers import BotKey, Browsers, PersonInput
from src.core.config import Settings
from src.core.errors import BadRequest, Unavailable
from src.runtime.runner import RunManager
from src.schemas.browser import (
    BrowserOut,
    BrowserProviderIn,
    BrowserProviderOut,
    ClickIn,
    KeyIn,
    OpenIn,
    PersonInputIn,
    ScrollIn,
    TypeIn,
)
from src.services import bot_service, browser_service
from src.services.browser_tools import NO_BROWSER
from src.services.credential_vault import CredentialVault

NOT_HERE = "Taking over a bot's browser needs the bots to run in the API (WORKER_MODE=embedded)."


# The organization's browser provider


async def get_provider(db: AsyncSession, access: Access, settings: Settings) -> BrowserProviderOut:
    return browser_service.view_of(await browser_service.find(db, access.org.id), settings)


async def choose_provider(
    db: AsyncSession,
    access: Access,
    body: BrowserProviderIn,
    *,
    settings: Settings,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None,
) -> BrowserProviderOut:
    """Owners and admins. A cloud provider is checked by starting and stopping a browser there."""
    access.require_admin()
    row = await browser_service.choose(
        db, org_id=access.org.id, user_id=access.user.id, body=body, settings=settings, vault=vault, transport=transport
    )
    await db.commit()
    return browser_service.view_of(row, settings)


# A bot's browser


async def state(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager, settings: Settings
) -> BrowserOut:
    key = await _key(db, access, bot_id)
    browsers = _browsers(runs, settings)
    chosen = settings.local_browser or await browser_service.find(db, access.org.id) is not None
    await db.commit()
    if browsers is None or not chosen:
        return BrowserOut(available=False, open=False, url=None, title=None)
    seen = await browsers.state(key)
    return BrowserOut(
        available=True, open=seen is not None, url=seen[0] if seen else None, title=seen[1] if seen else None
    )


async def screen(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager, settings: Settings) -> bytes:
    key = await _key(db, access, bot_id)
    return await _call(_required(runs, settings).screen(key))


async def take_over(
    db: AsyncSession,
    access: Access,
    bot_id: uuid.UUID,
    body: PersonInputIn,
    runs: RunManager,
    settings: Settings,
    vault: CredentialVault,
) -> BrowserOut:
    key = await _key(db, access, bot_id)
    browsers = _required(runs, settings)
    person = _person(body)
    if person.kind != "open":
        await _call(browsers.take_over(key, person))
        return await state(db, access, bot_id, runs, settings)

    launch = await browser_service.launch_for(db, access.org.id, bot_id, settings, vault)
    await db.commit()  # nothing held open while the browser starts
    if launch is None:
        raise BadRequest(NO_BROWSER)
    await _call(browsers.take_over(key, person, launch))
    if launch.cloud is not None:
        await browser_service.remember_profile(
            db, access.org.id, bot_id, launch.provider, await browsers.profile_of(key)
        )
        await db.commit()
    return await state(db, access, bot_id, runs, settings)


async def forget(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager, settings: Settings) -> None:
    """Close the bot's browser and forget its sign-ins, on this server and at cloud providers."""
    key = await _key(db, access, bot_id)
    await _call(_required(runs, settings).forget(key))
    await browser_service.forget_profiles(db, bot_id)
    await db.commit()


async def _key(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> BotKey:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another organization's bot
    await db.commit()  # nothing held open while the browser works
    return (access.org.id, bot.id)


def _browsers(runs: RunManager, settings: Settings) -> Browsers | None:
    return runs.browsers if settings.worker_mode == "embedded" else None


def _required(runs: RunManager, settings: Settings) -> Browsers:
    browsers = _browsers(runs, settings)
    if browsers is None:
        raise Unavailable(NOT_HERE)
    return browsers


async def _call[T](work: Awaitable[T]) -> T:
    """The browser's refusals (`BrowserUnavailable`: nothing happened) as 400s with their message."""
    try:
        return await work
    except NotDone as refused:
        raise BadRequest(str(refused)) from None


def _person(body: PersonInputIn) -> PersonInput:
    match body:
        case ClickIn():
            return PersonInput("click", x=body.x, y=body.y)
        case TypeIn():
            return PersonInput("type", text=body.text)
        case KeyIn():
            return PersonInput("key", text=body.key)
        case ScrollIn():
            return PersonInput("scroll", y=body.dy)
        case OpenIn():
            return PersonInput("open", text=body.url.strip())

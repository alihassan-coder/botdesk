"""Watching and taking over a bot's browser (ADR 0017 §5). Any member: a bot's browser is
bot-owned, like its own mailbox, so whoever can talk to the bot can sign it in somewhere.

Take over works where the bot's browser runs: in the API process (WORKER_MODE=embedded, the
default). With a separate worker the browser lives there, so this says it isn't available.
"""

import uuid
from collections.abc import Awaitable

from botdesk_plugin_sdk import NotDone
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.browser.local import BotKey, LocalBrowsers, PersonInput
from src.core.config import Settings
from src.core.errors import BadRequest, Unavailable
from src.runtime.runner import RunManager
from src.schemas.browser import BrowserOut, ClickIn, KeyIn, OpenIn, PersonInputIn, ScrollIn, TypeIn
from src.services import bot_service

NOT_HERE = "Taking over a bot's browser needs the bots to run in the API (WORKER_MODE=embedded)."


async def state(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager, settings: Settings
) -> BrowserOut:
    key = await _key(db, access, bot_id)
    browsers = _browsers(runs, settings)
    if browsers is None:
        return BrowserOut(available=False, open=False, url=None, title=None)
    seen = await browsers.state(key)
    return BrowserOut(
        available=True, open=seen is not None, url=seen[0] if seen else None, title=seen[1] if seen else None
    )


async def screen(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager, settings: Settings) -> bytes:
    key = await _key(db, access, bot_id)
    return await _call(_required(runs, settings).screen(key))


async def take_over(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, body: PersonInputIn, runs: RunManager, settings: Settings
) -> BrowserOut:
    key = await _key(db, access, bot_id)
    await _call(_required(runs, settings).take_over(key, _person(body)))
    return await state(db, access, bot_id, runs, settings)


async def forget(db: AsyncSession, access: Access, bot_id: uuid.UUID, runs: RunManager, settings: Settings) -> None:
    key = await _key(db, access, bot_id)
    await _call(_required(runs, settings).forget(key))


async def _key(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> BotKey:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another organization's bot
    await db.commit()  # nothing held open while the browser works
    return (access.org.id, bot.id)


def _browsers(runs: RunManager, settings: Settings) -> LocalBrowsers | None:
    return runs.browsers if settings.worker_mode == "embedded" else None


def _required(runs: RunManager, settings: Settings) -> LocalBrowsers:
    browsers = _browsers(runs, settings)
    if browsers is None:
        raise Unavailable(NOT_HERE if settings.local_browser else "This server has no browser for bots.")
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

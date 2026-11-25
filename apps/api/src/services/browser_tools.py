"""The Browser plugin's `BrowserAccess` (ADR 0017 §4): each tool checks the element is what the tool
says (a link for `follow`, a search box for `search`, the label people approved for `click`),
then acts in the bot's browser and returns the page as it is now.

Refusals raise `NotDone` (through `BrowserUnavailable`): nothing happened, and the bot may try
again differently. Screenshots go to the bot's files.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from botdesk_plugin_sdk import NotDone, ToolContext, ToolResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.browser.browsers import BotKey, Browsers
from src.browser.page import Element
from src.core.config import Settings
from src.core.errors import AppError
from src.models import Bot
from src.services import browser_service, file_service, storage_service
from src.services.credential_vault import CredentialVault

NO_BROWSER = "There's no browser for bots here yet. An owner or admin can choose one in Settings → Computers."
SIGN_IN_NEEDED = (
    "That's a password field. Bots never type passwords: ask a person to sign in to this site for you "
    "(they open your Computer tab and take over your browser), then carry on."
)


class BrowserTools:
    def __init__(
        self,
        browsers: Browsers | None,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        vault: CredentialVault,
    ) -> None:
        self._browsers = browsers
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._vault = vault

    async def open(self, ctx: ToolContext, *, url: str) -> ToolResult:
        async with self._sessionmaker() as db:
            launch = await browser_service.launch_for(db, ctx.org_id, ctx.bot_id, self._settings, self._vault)
        if launch is None:
            raise NotDone(NO_BROWSER)
        view = await self._local().open(_key(ctx), url.strip(), launch)
        if launch.cloud is not None:  # a provider may have just made the bot's profile there
            made = await self._local().profile_of(_key(ctx))
            if made and made != launch.profile:
                async with self._sessionmaker() as db:
                    await browser_service.remember_profile(db, ctx.org_id, ctx.bot_id, launch.provider, made)
                    await db.commit()
        return view.result()

    async def read(self, ctx: ToolContext, *, start: int) -> ToolResult:
        return (await self._local().view(_key(ctx))).result(start=start)

    async def follow(self, ctx: ToolContext, *, ref: int) -> ToolResult:
        def link_only(element: Element) -> None:
            if not element.is_link:
                raise NotDone(f"[{ref}] is a {element.kind}, not a link. Use browser.click for it.")

        return (await self._local().act(_key(ctx), ref, link_only, "click")).result()

    async def search(self, ctx: ToolContext, *, ref: int, text: str) -> ToolResult:
        def search_box_only(element: Element) -> None:
            if not element.is_search_box:
                raise NotDone(f"[{ref}] is a {element.kind}, not a search box. Use browser.type for it.")

        return (await self._local().act(_key(ctx), ref, search_box_only, "submit", text)).result()

    async def click(self, ctx: ToolContext, *, ref: int, what: str) -> ToolResult:
        return (await self._local().act(_key(ctx), ref, _labelled(ref, what), "click")).result()

    async def type(self, ctx: ToolContext, *, ref: int, text: str, field: str, submit: bool) -> ToolResult:
        def field_not_password(element: Element) -> None:
            if element.is_password:
                raise NotDone(SIGN_IN_NEEDED)
            _labelled(ref, field)(element)

        action = "submit" if submit else "fill"
        return (await self._local().act(_key(ctx), ref, field_not_password, action, text)).result()

    async def choose(self, ctx: ToolContext, *, ref: int, option: str, field: str) -> ToolResult:
        return (await self._local().act(_key(ctx), ref, _labelled(ref, field), "select", option)).result()

    async def back(self, ctx: ToolContext) -> ToolResult:
        return (await self._local().back(_key(ctx))).result()

    async def screenshot(self, ctx: ToolContext, *, path: str) -> ToolResult:
        picture = await self._local().screenshot(_key(ctx))
        path = path.strip() or f"screenshots/{datetime.now(UTC):%Y-%m-%d-%H%M%S}.png"
        return await self._save(ctx, path, picture, "image/png")

    async def download(self, ctx: ToolContext, *, ref: int, path: str) -> ToolResult:
        max_bytes = self._settings.file_max_mb * 1024 * 1024
        got = await self._local().download(_key(ctx), ref, max_bytes)
        saved = await self._save(ctx, path.strip() or f"downloads/{got.name}", got.data, got.type or None)
        return {**saved, "note": "Read it with files.read."}

    async def _save(self, ctx: ToolContext, path: str, data: bytes, content_type: str | None) -> ToolResult:
        """Into the bot's own files, by the same rules as everything saved there."""
        async with self._sessionmaker() as db:
            bot = await db.get(Bot, ctx.bot_id)
            if bot is None or bot.org_id != ctx.org_id:
                raise NotDone("This bot isn't there any more.")
            try:
                row = await storage_service.find(db, ctx.org_id)
                storage = await storage_service.open_storage(row, ctx.org_id, self._settings, self._vault)
                file = await file_service.save(
                    db,
                    storage,
                    org_id=ctx.org_id,
                    bot=bot,
                    path=path,
                    data=data,
                    content_type=content_type,
                    settings=self._settings,
                    run_id=ctx.run_id,
                )
            except AppError as error:
                raise NotDone(error.message) from None
            await db.commit()
            return {"saved": file.storage_key, "path": file.path, "type": file.content_type, "size": file.size_bytes}

    def _local(self) -> Browsers:
        if self._browsers is None:
            raise NotDone(NO_BROWSER)
        return self._browsers


def _key(ctx: ToolContext) -> BotKey:
    return (ctx.org_id, ctx.bot_id)


def _labelled(ref: int, words: str) -> Callable[[Element], None]:
    """The approval card shows `words`; refuse when the element is something else."""

    def check(element: Element) -> None:
        if not element.name:
            raise NotDone(
                f"[{ref}] is a {element.kind} with no label on the page, so people couldn't tell what they'd "
                "approve. Use another element, or ask a person to do it by taking over your browser."
            )
        if not element.matches(words):
            raise NotDone(
                f'[{ref}] is the {element.kind} "{element.name}", not {words}. '
                "Read the page again and use the right number."
            )

    return check

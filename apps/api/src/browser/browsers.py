"""Bots' browsers (ADR 0017 §3), one per bot, driven by Playwright: **Local** (Chromium on the
BotDesk server, with a profile folder per bot so its sign-ins last) or a **cloud** provider's
(`browser.cloud`: Steel, Browserbase, Kernel), reached over the Chrome DevTools Protocol with the
bot's profile there. Every tool and the live view work the same on both.

Playwright starts the browser as a subprocess, which the API's event loop can't do on Windows
(it is a selector loop, for psycopg). So every browser lives on one thread of its own with its
own event loop (a proactor loop on Windows), and the API's code awaits it through `_call`.

A session closes after `BROWSER_IDLE_MINUTES` without a tool call (a cloud one is released, so it
stops using the organization's browser time); at most `BROWSER_MAX_SESSIONS` Local ones are open
at once on this server. Only opening a page starts a browser (`open`, or a person's `open`): it
starts where the `Launch` says.
"""

import asyncio
import contextlib
import logging
import shutil
import sys
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from botdesk_plugin_sdk import NotDone
from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route, WebSocketRoute, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from src.browser.cloud import NAMES, CloudBrowser, CloudBrowserError
from src.browser.guard import PRIVATE, AddressGuard
from src.browser.page import INSPECT_JS, MAX_ELEMENTS, SNAPSHOT_JS, Element, PageView
from src.core.config import Settings

logger = logging.getLogger(__name__)

NAVIGATION_MS = 20_000
ACTION_MS = 8_000
SETTLE_MS = 600
VIEWPORT = {"width": 1280, "height": 800}

NOT_INSTALLED = (
    "The browser isn't installed on this server. In apps/api run `uv run playwright install chromium`, "
    "or set LOCAL_BROWSER_CHANNEL=chrome to use the Chrome installed on it."
)
BUSY = "Every browser on this server is in use. Try again in a few minutes."
NO_PAGE = "The browser has no page open. Open one first with browser.open."
NOT_OPEN = "The bot's browser isn't open. Open a page to start it."
GONE = "There's no element [{ref}] on the page now. Read the page again to get the current numbers."


class BrowserUnavailable(NotDone):
    """The browser couldn't do it and nothing changed: the message is for the bot and people."""


@dataclass(frozen=True)
class LocalBrowserSettings:
    profiles_dir: Path
    channel: str  # "" = Playwright's Chromium; "chrome" or "msedge" = the installed browser
    allow_private: bool
    idle_minutes: int
    max_sessions: int


@dataclass(frozen=True)
class Launch:
    """Where a bot's browser starts: `cloud` None is Local; else that provider, with the bot's
    `profile` there (None the first time: the provider makes one)."""

    cloud: CloudBrowser | None = None
    profile: str | None = None

    @property
    def provider(self) -> str:
        return self.cloud.provider if self.cloud else "local"


LOCAL = Launch()


@dataclass
class _Session:
    context: BrowserContext
    guard: AddressGuard
    provider: str = "local"
    profile: str | None = None  # the bot's profile at a cloud provider
    browser: Browser | None = None  # a cloud browser's connection
    release: Callable[[], Awaitable[None]] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)

    @property
    def page(self) -> Page | None:
        """The newest tab: a link that opens a new tab moves the bot there."""
        pages = [page for page in self.context.pages if not page.is_closed()]
        return pages[-1] if pages else None


BotKey = tuple[uuid.UUID, uuid.UUID]  # (organization, bot)

# Keys a person may press on the live view (letters and digits arrive as `type`).
KEYS = (
    "Enter",
    "Tab",
    "Shift+Tab",
    "Backspace",
    "Delete",
    "Escape",
    "Space",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "PageUp",
    "PageDown",
)


@dataclass(frozen=True)
class PersonInput:
    """One thing a person did on the live view. `x`, `y`: a click in page pixels (the screen is
    `VIEWPORT`); `y` alone: how far to scroll. `text`: what they typed, the key, or the address."""

    kind: Literal["click", "type", "key", "scroll", "open"]
    x: int = 0
    y: int = 0
    text: str = ""


class Browsers:
    def __init__(self, settings: LocalBrowserSettings) -> None:
        self.settings = settings
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Lock()
        # Only touched on the browsers' own thread:
        self._playwright: Playwright | None = None
        self._sessions: dict[BotKey, _Session] = {}
        self._opening: asyncio.Lock | None = None
        self._reaper: asyncio.Task[None] | None = None

    # What the tools call (from the API's or worker's event loop)

    async def open(self, key: BotKey, url: str, launch: Launch = LOCAL) -> PageView:
        async def go(session: _Session) -> PageView:
            why_not = await session.guard.why_not(url)
            if why_not:
                raise BrowserUnavailable(why_not)
            page = session.page or await session.context.new_page()
            with contextlib.suppress(PlaywrightTimeout):  # a slow page still shows what has loaded
                await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_MS)
            return await _view(page)

        return await self._call(self._with_session(key, go, launch))

    async def view(self, key: BotKey) -> PageView:
        return await self._call(self._with_open_session(key, lambda session: _view(_page(session)), NO_PAGE))

    async def act(
        self, key: BotKey, ref: int, check: Callable[[Element], None], action: str, value: str = ""
    ) -> PageView:
        """Find element `ref`, let `check` refuse it (raising `NotDone`), then click it, fill it
        with `value` (press Enter after when `action` is "submit"), or pick the option `value`."""

        async def do(session: _Session) -> PageView:
            page = _page(session)
            raw = await page.evaluate(INSPECT_JS, ref)
            if raw is None:
                raise BrowserUnavailable(GONE.format(ref=ref))
            check(Element.from_js(raw))
            target = page.locator(f'[data-botdesk-ref="{ref}"]').first
            if action == "click":
                await target.click(timeout=ACTION_MS)
            elif action in ("fill", "submit"):
                await target.fill(value, timeout=ACTION_MS)
                if action == "submit":
                    await target.press("Enter", timeout=ACTION_MS)
            elif action == "select":
                await target.select_option(label=value, timeout=ACTION_MS)
            await _settle(session)
            return await _view(_page(session))

        return await self._call(self._with_open_session(key, do, NO_PAGE))

    async def back(self, key: BotKey) -> PageView:
        async def go_back(session: _Session) -> PageView:
            page = _page(session)
            with contextlib.suppress(PlaywrightTimeout):
                await page.go_back(wait_until="domcontentloaded", timeout=NAVIGATION_MS)
            return await _view(page)

        return await self._call(self._with_open_session(key, go_back, NO_PAGE))

    async def screenshot(self, key: BotKey) -> bytes:
        async def shoot(session: _Session) -> bytes:
            return await _page(session).screenshot(type="png", timeout=ACTION_MS)

        return await self._call(self._with_open_session(key, shoot, NO_PAGE))

    # Take over: a person watches the bot's browser and uses it (to sign in), ADR 0017 §5

    async def state(self, key: BotKey) -> tuple[str, str] | None:
        """The open page's (address, title), or None when the bot's browser isn't open."""

        async def look() -> tuple[str, str] | None:
            session = self._sessions.get(key)
            page = session.page if session else None
            return (page.url, await page.title()) if page else None

        return await self._call(look())

    async def screen(self, key: BotKey) -> bytes:
        """What the browser shows now, as a JPEG (the live view polls this)."""

        async def shoot(session: _Session) -> bytes:
            return await _page(session).screenshot(type="jpeg", quality=60, timeout=ACTION_MS)

        return await self._call(self._with_open_session(key, shoot))

    async def take_over(self, key: BotKey, person: PersonInput, launch: Launch = LOCAL) -> None:
        """Do what the person did on the live view. `open` starts the browser if it isn't open."""

        async def do(session: _Session) -> None:
            if person.kind == "open":
                why_not = await session.guard.why_not(person.text)
                if why_not:
                    raise BrowserUnavailable(why_not)
                page = session.page or await session.context.new_page()
                with contextlib.suppress(PlaywrightTimeout):
                    await page.goto(person.text, wait_until="domcontentloaded", timeout=NAVIGATION_MS)
                return
            page = _page(session)
            if person.kind == "click":
                await page.mouse.click(person.x, person.y)
            elif person.kind == "type":
                await page.keyboard.type(person.text)
            elif person.kind == "key":
                await page.keyboard.press(person.text)
            elif person.kind == "scroll":
                await page.mouse.wheel(0, person.y)
            await page.wait_for_timeout(SETTLE_MS // 2)

        if person.kind == "open":
            await self._call(self._with_session(key, do, launch))
        else:
            await self._call(self._with_open_session(key, do))

    async def profile_of(self, key: BotKey) -> str | None:
        """The bot's profile at the cloud provider its open browser runs on (to remember it)."""

        async def look() -> str | None:
            session = self._sessions.get(key)
            return session.profile if session else None

        return await self._call(look())

    async def forget(self, key: BotKey) -> None:
        """Close the bot's browser and delete its Local profile: every site it was signed in to
        forgets it. (A cloud profile is forgotten by not using it again: see `browser_service`.)"""
        await self._call(self._close_session(key))
        org_id, bot_id = key
        profile = self.settings.profiles_dir / str(org_id) / str(bot_id)
        await asyncio.to_thread(shutil.rmtree, profile, True)

    async def close(self) -> None:
        """Close every browser and the thread. Safe to call when nothing was ever opened."""
        if self._loop is None:
            return
        with contextlib.suppress(Exception):
            await self._call(self._shutdown())
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join, 5)
        self._loop = None

    # The bridge to the browsers' thread

    async def _call[T](self, work: Coroutine[Any, Any, T]) -> T:
        loop = self._ensure_thread()
        future = asyncio.run_coroutine_threadsafe(work, loop)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            raise

    def _ensure_thread(self) -> asyncio.AbstractEventLoop:
        with self._started:
            if self._loop is None:
                ready = threading.Event()

                def run() -> None:
                    loop = _new_loop()
                    asyncio.set_event_loop(loop)
                    self._loop = loop
                    ready.set()
                    loop.run_forever()
                    loop.close()

                self._thread = threading.Thread(target=run, name="local-browsers", daemon=True)
                self._thread.start()
                ready.wait()
            assert self._loop is not None
            return self._loop

    # On the browsers' thread

    async def _with_session[T](
        self, key: BotKey, work: Callable[[_Session], Awaitable[T]], launch: Launch | None = LOCAL
    ) -> T:
        """Run `work` on the bot's browser, one action at a time. `launch` None: the browser that's
        open, whichever provider it runs on; else one started there (replacing one elsewhere)."""
        session = await self._session(key, launch)
        async with session.lock:  # one action at a time per bot
            session.last_used = time.monotonic()
            try:
                return await work(session)
            except PlaywrightTimeout:
                raise BrowserUnavailable("The page didn't answer in time.") from None
            except PlaywrightError as error:
                raise BrowserUnavailable(_explain(error)) from None
            finally:
                session.last_used = time.monotonic()

    async def _with_open_session[T](
        self, key: BotKey, work: Callable[[_Session], Awaitable[T]], closed: str = NOT_OPEN
    ) -> T:
        """Like `_with_session`, but never starts a browser: only opening a page does."""
        session = self._sessions.get(key)
        if session is None:
            raise BrowserUnavailable(closed)
        return await self._with_session(key, work, None)

    async def _session(self, key: BotKey, launch: Launch | None) -> _Session:
        self._opening = self._opening or asyncio.Lock()
        async with self._opening:
            open_now = self._sessions.get(key)
            if open_now is not None and (launch is None or open_now.provider == launch.provider):
                return open_now
            if launch is None:
                raise BrowserUnavailable(NOT_OPEN)
            if open_now is not None:  # the organization chose another provider since
                await self._close_session(key)
            local_open = sum(1 for session in self._sessions.values() if session.provider == "local")
            if launch.cloud is None and local_open >= self.settings.max_sessions:
                raise BrowserUnavailable(BUSY)
            playwright = await self._start()
            session = await (
                self._launch(playwright, key) if launch.cloud is None else _connect(playwright, key, launch)
            )
            self._sessions[key] = session
            return session

    async def _start(self) -> Playwright:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._reaper = asyncio.create_task(self._reap())
        return self._playwright

    async def _launch(self, playwright: Playwright, key: BotKey) -> _Session:
        org_id, bot_id = key
        profile = self.settings.profiles_dir / str(org_id) / str(bot_id)
        profile.mkdir(parents=True, exist_ok=True)
        try:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                channel=self.settings.channel or None,
                headless=True,
                viewport=VIEWPORT,  # type: ignore[arg-type]
                accept_downloads=False,
                service_workers="block",  # their requests would skip the address check
                args=["--disable-dev-shm-usage"],
            )
        except PlaywrightError as error:
            if "Executable doesn't exist" in str(error) or "is not found" in str(error):
                raise BrowserUnavailable(NOT_INSTALLED) from None
            logger.exception("The browser for bot %s didn't start", bot_id)
            raise BrowserUnavailable("The browser didn't start on this server.") from None

        guard = AddressGuard(allow_private=self.settings.allow_private)
        if not guard.allow_private:

            async def check(route: Route) -> None:
                if await guard.allows(route.request.url):
                    await route.continue_()
                else:
                    await route.abort("blockedbyclient")

            async def check_socket(socket: WebSocketRoute) -> None:
                if await guard.allows(socket.url.replace("ws", "http", 1)):
                    socket.connect_to_server()
                else:
                    await socket.close()

            await context.route("**/*", check)
            await context.route_web_socket("**/*", check_socket)
        return _Session(context=context, guard=guard)

    async def _close_session(self, key: BotKey) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            return
        with contextlib.suppress(Exception):
            await (session.browser.close() if session.browser else session.context.close())
        if session.release is not None:
            try:
                await session.release()
            except Exception:  # it ends by itself at the provider's timeout anyway
                logger.warning("Couldn't release a %s browser", session.provider, exc_info=True)

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(60)
            idle = time.monotonic() - self.settings.idle_minutes * 60
            for key in [key for key, session in self._sessions.items() if session.last_used < idle]:
                if not self._sessions[key].lock.locked():
                    await self._close_session(key)

    async def _shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
        for key in list(self._sessions):
            await self._close_session(key)
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


async def _connect(playwright: Playwright, key: BotKey, launch: Launch) -> _Session:
    """A cloud provider's browser for the bot, over CDP, with its profile there."""
    assert launch.cloud is not None
    name = NAMES[launch.cloud.provider]
    try:
        cloud = await launch.cloud.start(key[1], launch.profile)
    except CloudBrowserError as error:
        raise BrowserUnavailable(str(error)) from None
    try:
        browser = await playwright.chromium.connect_over_cdp(cloud.cdp_url, timeout=NAVIGATION_MS)
    except PlaywrightError:
        with contextlib.suppress(Exception):
            await cloud.release()
        raise BrowserUnavailable(f"BotDesk couldn't connect to the {name} browser. Try again in a moment.") from None
    context = browser.contexts[0] if browser.contexts else await browser.new_context(viewport=VIEWPORT)  # type: ignore[arg-type]
    # The page runs on the provider's network, not this server's: no address check needed.
    return _Session(
        context=context,
        guard=AddressGuard(allow_private=True),
        provider=launch.cloud.provider,
        profile=cloud.profile,
        browser=browser,
        release=cloud.release,
    )


def _explain(error: PlaywrightError) -> str:
    """Playwright's first line, in words: "net::ERR_BLOCKED_BY_CLIENT at …" is the address check."""
    message = (error.message or str(error)).splitlines()[0]
    if "ERR_BLOCKED_BY_CLIENT" in message:
        return PRIVATE
    if "ERR_NAME_NOT_RESOLVED" in message:
        return "That website couldn't be found. Check the address."
    return f"The browser couldn't do that: {message}"


def _new_loop() -> asyncio.AbstractEventLoop:
    """A loop that can start subprocesses: on Windows only the proactor loop can."""
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def _page(session: _Session) -> Page:
    page = session.page
    if page is None:
        raise BrowserUnavailable(NO_PAGE)
    return page


async def _settle(session: _Session) -> None:
    """Give a click's navigation or update a moment to land."""
    page = _page(session)
    with contextlib.suppress(PlaywrightTimeout):
        await page.wait_for_load_state("domcontentloaded", timeout=ACTION_MS)
    await page.wait_for_timeout(SETTLE_MS)


async def _view(page: Page) -> PageView:
    raw = await page.evaluate(SNAPSHOT_JS, MAX_ELEMENTS)
    return PageView.from_js(raw)


def local_browser_settings(settings: Settings) -> LocalBrowserSettings:
    return LocalBrowserSettings(
        profiles_dir=Path(settings.browser_profiles_dir),
        channel=settings.local_browser_channel,
        allow_private=settings.allow_private_browser_urls,
        idle_minutes=settings.browser_idle_minutes,
        max_sessions=settings.browser_max_sessions,
    )

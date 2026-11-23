"""The Browser plugin (ADR 0017 §4): a bot opens web pages, reads them, and clicks and types,
each step through the normal policy.

The risk of an action is fixed per tool, so the policy decides before anything happens:
following a link and searching only read (`browser.follow`, `browser.search`); any other
click, typing and choosing ask a person at "Ask before acting" (`browser.click`, `browser.type`,
`browser.choose`, `write-external`). Each tool checks the element really is what it claims
before acting, so a button can't be pressed through `follow`, and the words on an approval card
(`what`, `field`) must match the element's own label. Pages are outside text: reading one
taints the run (ADR 0004 §5).

A core plugin like Files; the handlers call `BrowserAccess`, provided by the app
(`services/browser_tools.py`).
"""

from typing import Any, Protocol

from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolResult, ToolSpec
from pydantic import BaseModel, Field

BROWSER_PLUGIN_ID = "browser"

_REF = "The element's number from the page's list of elements, like 3 for [3]."
_WHAT = 'The element as it reads on the page, like the "Send" button. People approving see this.'


class BrowserAccess(Protocol):
    async def open(self, ctx: ToolContext, *, url: str) -> ToolResult: ...
    async def read(self, ctx: ToolContext, *, start: int) -> ToolResult: ...
    async def follow(self, ctx: ToolContext, *, ref: int) -> ToolResult: ...
    async def search(self, ctx: ToolContext, *, ref: int, text: str) -> ToolResult: ...
    async def click(self, ctx: ToolContext, *, ref: int, what: str) -> ToolResult: ...
    async def type(self, ctx: ToolContext, *, ref: int, text: str, field: str, submit: bool) -> ToolResult: ...
    async def choose(self, ctx: ToolContext, *, ref: int, option: str, field: str) -> ToolResult: ...
    async def back(self, ctx: ToolContext) -> ToolResult: ...
    async def screenshot(self, ctx: ToolContext, *, path: str) -> ToolResult: ...


class OpenArgs(BaseModel):
    url: str = Field(min_length=4, max_length=2000, description="The page's address, starting with https://.")


class ReadArgs(BaseModel):
    start: int = Field(default=0, ge=0, description="For long pages: the character to read from (from more_text_from).")


class FollowArgs(BaseModel):
    ref: int = Field(ge=1, description=_REF)


class SearchArgs(BaseModel):
    ref: int = Field(ge=1, description=_REF)
    text: str = Field(min_length=1, max_length=500, description="What to search for.")


class ClickArgs(BaseModel):
    ref: int = Field(ge=1, description=_REF)
    what: str = Field(min_length=1, max_length=120, description=_WHAT)


class TypeArgs(BaseModel):
    ref: int = Field(ge=1, description=_REF)
    text: str = Field(max_length=5000, description="The text to put in the field (it replaces what's there).")
    field: str = Field(min_length=1, max_length=120, description='The field as it reads on the page, like "Subject".')
    submit: bool = Field(default=False, description="Press Enter afterwards.")


class ChooseArgs(BaseModel):
    ref: int = Field(ge=1, description=_REF)
    option: str = Field(min_length=1, max_length=200, description="The option's text, as shown in the list.")
    field: str = Field(
        min_length=1, max_length=120, description='The dropdown as it reads on the page, like "Country".'
    )


class NoArgs(BaseModel):
    pass


class ScreenshotArgs(BaseModel):
    path: str = Field(
        default="",
        max_length=300,
        description="Where to save it in your files. Empty: screenshots/<date and time>.png.",
    )


class _Unavailable:
    async def _refuse(self, *_: Any, **__: Any) -> ToolResult:
        raise RuntimeError("The browser isn't available here.")

    open = read = follow = search = click = type = choose = back = screenshot = _refuse


def manifest(access: BrowserAccess | None = None) -> PluginManifest:
    browser: BrowserAccess = access or _Unavailable()

    async def open_page(args: OpenArgs, ctx: ToolContext) -> ToolResult:
        return await browser.open(ctx, url=args.url)

    async def read_page(args: ReadArgs, ctx: ToolContext) -> ToolResult:
        return await browser.read(ctx, start=args.start)

    async def follow(args: FollowArgs, ctx: ToolContext) -> ToolResult:
        return await browser.follow(ctx, ref=args.ref)

    async def search(args: SearchArgs, ctx: ToolContext) -> ToolResult:
        return await browser.search(ctx, ref=args.ref, text=args.text)

    async def click(args: ClickArgs, ctx: ToolContext) -> ToolResult:
        return await browser.click(ctx, ref=args.ref, what=args.what)

    async def type_text(args: TypeArgs, ctx: ToolContext) -> ToolResult:
        return await browser.type(ctx, ref=args.ref, text=args.text, field=args.field, submit=args.submit)

    async def choose(args: ChooseArgs, ctx: ToolContext) -> ToolResult:
        return await browser.choose(ctx, ref=args.ref, option=args.option, field=args.field)

    async def back(args: NoArgs, ctx: ToolContext) -> ToolResult:
        return await browser.back(ctx)

    async def screenshot(args: ScreenshotArgs, ctx: ToolContext) -> ToolResult:
        return await browser.screenshot(ctx, path=args.path)

    page = "You get back the page: its address, title, text, and the numbered elements you can use."
    return PluginManifest(
        id=BROWSER_PLUGIN_ID,
        name="Browser",
        version="1.0.0",
        description="Open web pages, read them, and click and type on them, asking before changing anything.",
        tools=(
            ToolSpec(
                name="open",
                title="Open a web page",
                description=f"Open a web page in your browser. {page}",
                args_model=OpenArgs,
                risk="read",
                handler=open_page,
                idempotent=True,
                untrusted_output=True,
            ),
            ToolSpec(
                name="read",
                title="Read the page",
                description=f"Read the page that's open again (after it changed, or the rest of a long page). {page}",
                args_model=ReadArgs,
                risk="read",
                handler=read_page,
                idempotent=True,
                untrusted_output=True,
            ),
            ToolSpec(
                name="follow",
                title="Follow a link",
                description=f"Follow a link on the page (only links; for buttons use browser.click). {page}",
                args_model=FollowArgs,
                risk="read",
                handler=follow,
                idempotent=True,
                untrusted_output=True,
            ),
            ToolSpec(
                name="search",
                title="Search the site",
                description=f"Type into a search box and press Enter (only search boxes). {page}",
                args_model=SearchArgs,
                risk="read",
                handler=search,
                idempotent=True,
                untrusted_output=True,
                summarize=lambda args: f'Search for "{args.text}"',
            ),
            ToolSpec(
                name="click",
                title="Click on a page",
                description=f"Click a button or anything else on the page. A person may be asked first. {page}",
                args_model=ClickArgs,
                risk="write-external",
                handler=click,
                untrusted_output=True,
                summarize=lambda args: f"Click {args.what}",
            ),
            ToolSpec(
                name="type",
                title="Type on a page",
                description=(
                    "Type into a field on the page (never a password: ask a person to sign in instead). "
                    f"A person may be asked first. {page}"
                ),
                args_model=TypeArgs,
                risk="write-external",
                handler=type_text,
                untrusted_output=True,
                summarize=lambda args: (
                    f'Type "{_short(args.text)}" into {args.field}' + (" and press Enter" if args.submit else "")
                ),
            ),
            ToolSpec(
                name="choose",
                title="Choose an option",
                description=f"Choose an option in a dropdown on the page. A person may be asked first. {page}",
                args_model=ChooseArgs,
                risk="write-external",
                handler=choose,
                untrusted_output=True,
                summarize=lambda args: f'Choose "{args.option}" in {args.field}',
            ),
            ToolSpec(
                name="back",
                title="Go back",
                description=f"Go back to the previous page. {page}",
                args_model=NoArgs,
                risk="read",
                handler=back,
                idempotent=True,
                untrusted_output=True,
            ),
            ToolSpec(
                name="screenshot",
                title="Take a screenshot",
                description="Save a picture of the page that's open to your files.",
                args_model=ScreenshotArgs,
                risk="write-internal",
                handler=screenshot,
                idempotent=True,
            ),
        ),
        auth=None,
    )


def _short(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"

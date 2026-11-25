"""Cloud browser providers (ADR 0017 §3): Steel, Browserbase and Kernel. Each starts a browser for a
bot, with the bot's own saved profile so its sign-ins last, and hands back a Chrome DevTools
Protocol address that `browser.local` drives with the same Playwright code as a Local browser.

A bot's **profile** at each provider:
- Steel: `profileId`, made by the first session (`persistProfile`), then reused.
- Browserbase: a context, made once (`POST /v1/contexts`), used with `persist: true`.
- Kernel: a profile named `botdesk-<bot id>-<random>`, made once (`POST /profiles`), used with
  `save_changes`. The random part means a forgotten profile is never picked up again by name.

Forgetting sign-ins drops BotDesk's record of the profile, so the next browser gets a fresh one,
and asks the provider to delete the old one (best effort: `forget`).

The organization's key goes only to the provider's fixed address; nothing here follows redirects.
"""

import contextlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
VIEWPORT = {"width": 1280, "height": 800}
SESSION_MINUTES = 30

CloudProviderId = Literal["steel", "browserbase", "kernel"]
NAMES: dict[CloudProviderId, str] = {"steel": "Steel", "browserbase": "Browserbase", "kernel": "Kernel"}


class CloudBrowserError(Exception):
    """The provider refused or failed. The message is for people and bots."""


@dataclass(frozen=True)
class CloudSession:
    cdp_url: str
    profile: str | None  # the bot's profile there, to remember (it may be new)
    release: Callable[[], Awaitable[None]]


class CloudBrowser(Protocol):
    provider: CloudProviderId

    async def start(self, bot_id: uuid.UUID, profile: str | None) -> CloudSession:
        """A browser for this bot, signed in where its profile is."""
        ...

    async def check(self) -> None:
        """Start a browser and release it: `CloudBrowserError` saying what's wrong, or nothing."""
        ...

    async def forget(self, profile: str) -> None:
        """Ask the provider to delete this profile (and so its sign-ins). Best effort: never raises."""
        ...


class _Api:
    """Calls to one provider's fixed address with the organization's key."""

    def __init__(
        self, provider: CloudProviderId, base: str, headers: dict[str, str], transport: httpx.AsyncBaseTransport | None
    ) -> None:
        self.provider = provider
        self._base = base
        self._headers = headers
        self._transport = transport

    async def call(
        self, method: str, path: str, body: dict[str, Any] | None = None, *, ok: tuple[int, ...] = ()
    ) -> Any:
        name = NAMES[self.provider]
        try:
            async with httpx.AsyncClient(
                base_url=self._base, headers=self._headers, timeout=TIMEOUT, transport=self._transport
            ) as client:
                response = await client.request(method, path, json=body)
        except httpx.HTTPError:
            raise CloudBrowserError(f"BotDesk couldn't reach {name}. Try again in a moment.") from None
        if response.is_success or response.status_code in ok:
            return response.json() if response.content and "json" in response.headers.get("content-type", "") else None
        if response.status_code in (401, 403):
            raise CloudBrowserError(f"{name} refused the key. Check it in Settings → Computers.")
        if response.status_code in (402, 429):
            raise CloudBrowserError(
                f"{name} says the plan's limit is reached (browser time, or browsers at once). "
                "Check your plan there, or try again later."
            )
        raise CloudBrowserError(f"{name} couldn't start a browser (it answered {response.status_code}).")

    async def forget(self, path: str) -> None:
        """Delete something at the provider, best effort (a profile the bot no longer uses)."""
        await _forget(self, path)


async def _forget(api: "_Api", path: str) -> None:
    with contextlib.suppress(CloudBrowserError):  # else it stays at the provider, unused by BotDesk
        await api.call("DELETE", path, ok=(404,))


def _field(body: Any, name: str, provider: CloudProviderId) -> str:
    value = body.get(name) if isinstance(body, dict) else None
    if not isinstance(value, str) or not value:
        raise CloudBrowserError(f"{NAMES[provider]} answered without a {name}.")
    return value


class SteelBrowser:
    provider: CloudProviderId = "steel"

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api = _Api("steel", "https://api.steel.dev", {"steel-api-key": api_key}, transport)

    async def start(self, bot_id: uuid.UUID, profile: str | None) -> CloudSession:
        body: dict[str, Any] = {
            "dimensions": VIEWPORT,
            "timeout": SESSION_MINUTES * 60_000,
            "persistProfile": True,  # without profileId: makes one and answers its id
            "metadata": {"botdesk_bot": str(bot_id)},
        }
        if profile:
            body["profileId"] = profile
        answer = await self._api.call("POST", "/v1/sessions", body)
        session_id = _field(answer, "id", "steel")
        made = answer.get("profileId") if isinstance(answer.get("profileId"), str) else None

        async def release() -> None:
            await self._api.call("POST", f"/v1/sessions/{session_id}/release")

        return CloudSession(cdp_url=_field(answer, "websocketUrl", "steel"), profile=made or profile, release=release)

    async def check(self) -> None:
        answer = await self._api.call("POST", "/v1/sessions", {"timeout": 60_000})
        await self._api.call("POST", f"/v1/sessions/{_field(answer, 'id', 'steel')}/release")

    async def forget(self, profile: str) -> None:
        await self._api.forget(f"/v1/profiles/{profile}")


class BrowserbaseBrowser:
    provider: CloudProviderId = "browserbase"

    def __init__(
        self, api_key: str, project_id: str = "", *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api = _Api("browserbase", "https://api.browserbase.com", {"X-BB-API-Key": api_key}, transport)
        self._project = {"projectId": project_id} if project_id else {}

    async def start(self, bot_id: uuid.UUID, profile: str | None) -> CloudSession:
        if not profile:
            context = await self._api.call("POST", "/v1/contexts", {**self._project})
            profile = _field(context, "id", "browserbase")
        body = {
            **self._project,
            "timeout": SESSION_MINUTES * 60,
            "browserSettings": {"context": {"id": profile, "persist": True}, "viewport": VIEWPORT},
            "userMetadata": {"botdesk_bot": str(bot_id)},
        }
        answer = await self._api.call("POST", "/v1/sessions", body)
        session_id = _field(answer, "id", "browserbase")

        async def release() -> None:
            await self._api.call("POST", f"/v1/sessions/{session_id}", {**self._project, "status": "REQUEST_RELEASE"})

        return CloudSession(cdp_url=_field(answer, "connectUrl", "browserbase"), profile=profile, release=release)

    async def check(self) -> None:
        answer = await self._api.call("POST", "/v1/sessions", {**self._project, "timeout": 60})
        session_id = _field(answer, "id", "browserbase")
        await self._api.call("POST", f"/v1/sessions/{session_id}", {**self._project, "status": "REQUEST_RELEASE"})

    async def forget(self, profile: str) -> None:
        await self._api.forget(f"/v1/contexts/{profile}")


class KernelBrowser:
    provider: CloudProviderId = "kernel"

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api = _Api("kernel", "https://api.onkernel.com", {"Authorization": f"Bearer {api_key}"}, transport)

    async def start(self, bot_id: uuid.UUID, profile: str | None) -> CloudSession:
        if not profile:
            profile = f"botdesk-{bot_id}-{secrets.token_hex(4)}"
            await self._api.call("POST", "/profiles", {"name": profile})
        body = {
            "headless": True,
            "timeout_seconds": SESSION_MINUTES * 60,
            "viewport": VIEWPORT,
            "profile": {"name": profile, "save_changes": True},
        }
        answer = await self._api.call("POST", "/browsers", body)
        session_id = _field(answer, "session_id", "kernel")

        async def release() -> None:
            await self._api.call("DELETE", f"/browsers/{session_id}", ok=(404,))

        return CloudSession(cdp_url=_field(answer, "cdp_ws_url", "kernel"), profile=profile, release=release)

    async def check(self) -> None:
        answer = await self._api.call("POST", "/browsers", {"headless": True, "timeout_seconds": 60})
        await self._api.call("DELETE", f"/browsers/{_field(answer, 'session_id', 'kernel')}", ok=(404,))

    async def forget(self, profile: str) -> None:
        await self._api.forget(f"/profiles/{profile}")


def cloud_browser(
    provider: CloudProviderId, api_key: str, project_id: str = "", *, transport: httpx.AsyncBaseTransport | None = None
) -> CloudBrowser:
    if provider == "steel":
        return SteelBrowser(api_key, transport=transport)
    if provider == "browserbase":
        return BrowserbaseBrowser(api_key, project_id, transport=transport)
    return KernelBrowser(api_key, transport=transport)

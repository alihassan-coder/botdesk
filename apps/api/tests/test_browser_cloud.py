"""Cloud browser providers (ADR 0017 step 4): each provider's calls, choosing one in Settings →
Computers (checked with a real start and stop), and where a bot's browser then starts. The
providers are fakes; nothing here reaches Steel, Browserbase or Kernel."""

import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.browser.cloud import BrowserbaseBrowser, CloudBrowserError, KernelBrowser, SteelBrowser
from src.services import browser_service
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

BOT = uuid.UUID("11111111-2222-3333-4444-555555555555")


class FakeCloud:
    """One provider's API: records every call and answers like the provider does."""

    def __init__(self, *, key_header: str, key: str) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self._header, self._key = key_header, key

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if request.headers.get(self._header) != self._key:
            return httpx.Response(401, json={"error": "unauthorized"})
        path = request.url.path
        if path == "/v1/sessions" and request.method == "POST":  # Steel and Browserbase
            answer = {"id": "s-1", "websocketUrl": "wss://connect.steel.dev?token=t", "connectUrl": "wss://bb/cdp"}
            if body and body.get("persistProfile") and not body.get("profileId"):
                answer["profileId"] = "steel-profile-1"
            return httpx.Response(201, json=answer)
        if path == "/v1/contexts":
            return httpx.Response(201, json={"id": "bb-context-1"})
        if path == "/profiles":
            return httpx.Response(409, json={"error": "exists"})
        if path == "/browsers" and request.method == "POST":
            return httpx.Response(200, json={"session_id": "k-1", "cdp_ws_url": "wss://kernel/cdp"})
        return httpx.Response(200, json={})


async def test_steel_makes_a_profile_once_then_reuses_it() -> None:
    fake = FakeCloud(key_header="steel-api-key", key="steel-key")
    steel = SteelBrowser("steel-key", transport=httpx.MockTransport(fake.handle))

    first = await steel.start(BOT, None)
    assert (first.cdp_url, first.profile) == ("wss://connect.steel.dev?token=t", "steel-profile-1")
    again = await steel.start(BOT, "steel-profile-1")
    assert again.profile == "steel-profile-1"
    assert fake.calls[1][2]["profileId"] == "steel-profile-1"

    await again.release()
    assert fake.calls[-1][:2] == ("POST", "/v1/sessions/s-1/release")


async def test_browserbase_keeps_a_context_per_bot() -> None:
    fake = FakeCloud(key_header="x-bb-api-key", key="bb-key")
    browserbase = BrowserbaseBrowser("bb-key", "project-9", transport=httpx.MockTransport(fake.handle))

    session = await browserbase.start(BOT, None)
    assert (session.cdp_url, session.profile) == ("wss://bb/cdp", "bb-context-1")
    sent = fake.calls[1][2]
    assert sent["projectId"] == "project-9"
    assert sent["browserSettings"]["context"] == {"id": "bb-context-1", "persist": True}

    await session.release()
    assert fake.calls[-1] == ("POST", "/v1/sessions/s-1", {"projectId": "project-9", "status": "REQUEST_RELEASE"})


async def test_kernel_uses_a_named_profile_per_bot() -> None:
    fake = FakeCloud(key_header="authorization", key="Bearer k-key")
    kernel = KernelBrowser("k-key", transport=httpx.MockTransport(fake.handle))

    session = await kernel.start(BOT, None)  # the profile already exists there (409): fine
    assert (session.cdp_url, session.profile) == ("wss://kernel/cdp", f"botdesk-{BOT}")
    assert fake.calls[1][2]["profile"] == {"name": f"botdesk-{BOT}", "save_changes": True}
    await session.release()
    assert fake.calls[-1][:2] == ("DELETE", "/browsers/k-1")


async def test_refusals_say_what_to_do() -> None:
    def limit(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "limit"})

    with pytest.raises(CloudBrowserError, match="refused the key"):
        await SteelBrowser(
            "wrong", transport=httpx.MockTransport(FakeCloud(key_header="steel-api-key", key="k").handle)
        ).check()
    with pytest.raises(CloudBrowserError, match="plan's limit"):
        await KernelBrowser("k", transport=httpx.MockTransport(limit)).check()


async def test_an_admin_chooses_steel_and_bots_start_there(providers: FakeProviders) -> None:
    fake = FakeCloud(key_header="steel-api-key", key="steel-key-1234")
    providers.answer("api.steel.dev", handler=fake.handle)
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        me = await sign_up(client)
        org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
        assert (await client.get(f"{org}/browser-provider")).json()["provider"] == "local"

        wrong = await client.put(f"{org}/browser-provider", json={"provider": "steel", "apiKey": "not-the-key"})
        assert wrong.status_code == 400 and "refused the key" in wrong.json()["detail"]

        chosen = await client.put(f"{org}/browser-provider", json={"provider": "steel", "apiKey": "steel-key-1234"})
        assert chosen.status_code == 200, chosen.text
        assert (chosen.json()["provider"], chosen.json()["keyHint"]) == ("steel", "1234")
        assert [call[:2] for call in fake.calls[-2:]] == [
            ("POST", "/v1/sessions"),
            ("POST", "/v1/sessions/s-1/release"),
        ]

        # A bot's browser now starts at Steel, with the profile Steel made for it last time.
        bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
        org_id, bot_id = uuid.UUID(me["organizations"][0]["id"]), uuid.UUID(bot["id"])
        db: AsyncSession
        async with app.state.sessionmaker() as db:
            await browser_service.remember_profile(db, org_id, bot_id, "steel", "steel-profile-1")
            await db.commit()
            launch = await browser_service.launch_for(db, org_id, bot_id, TEST_SETTINGS, app.state.vault)
        assert launch is not None and (launch.provider, launch.profile) == ("steel", "steel-profile-1")

        # Forgetting sign-ins forgets the profile; back to Local.
        assert (await client.delete(f"{org}/bots/{bot['id']}/browser")).status_code == 204
        async with app.state.sessionmaker() as db:
            launch = await browser_service.launch_for(db, org_id, bot_id, TEST_SETTINGS, app.state.vault)
        assert launch is not None and launch.profile is None
        local = await client.put(f"{org}/browser-provider", json={"provider": "local"})
        assert local.json()["provider"] == "local"


async def test_a_cloud_provider_needs_its_key(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    missing = await client.put(f"{org}/browser-provider", json={"provider": "kernel"})
    assert missing.status_code == 400 and "API key" in missing.json()["detail"]

"""Rate limits on sign-in, sign-up, forgot-password and reset-password (429 with Retry-After)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from src.core.config import Settings
from src.main import create_app
from tests.conftest import PASSWORD, TEST_SETTINGS, FakeEmailSender, sign_up

AUTH = "/api/v1/auth"


@asynccontextmanager
async def client_from(peer: str, settings: Settings = TEST_SETTINGS) -> AsyncIterator[httpx.AsyncClient]:
    """A fresh app, called from the network address `peer` (what the API sees as the connection)."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.runs.enabled = False
        app.state.email = FakeEmailSender()
        transport = httpx.ASGITransport(app=app, client=(peer, 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


async def _sign_in(client: httpx.AsyncClient, email: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return await client.post(f"{AUTH}/sign-in", json={"email": email, "password": "wrong-password"}, headers=headers)


async def test_sign_in_is_limited_per_email_with_a_friendly_429(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    for _ in range(5):
        assert (await _sign_in(client, "ali@acme.dev")).status_code == 401
    refused = await _sign_in(client, "ALI@acme.dev")  # the same email, however it's typed
    assert refused.status_code == 429
    assert 50 < int(refused.headers["retry-after"]) <= 60  # seconds
    assert refused.json()["detail"] == "Too many attempts. Try again in 1 minute."
    # Even the right password waits: the point is to stop guessing.
    right = await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": PASSWORD})
    assert right.status_code == 429


async def test_unknown_and_known_emails_are_limited_the_same(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    known = [(await _sign_in(client, "ali@acme.dev")).status_code for _ in range(6)]
    unknown = [(await _sign_in(client, "nobody@acme.dev")).status_code for _ in range(6)]
    assert known == unknown == [401] * 5 + [429]


async def test_sign_in_is_limited_per_address() -> None:
    async with client_from("203.0.113.7") as client:
        codes = [(await _sign_in(client, f"person{i}@acme.dev")).status_code for i in range(11)]
    assert codes == [401] * 10 + [429]


async def test_forwarded_for_counts_only_from_a_trusted_proxy() -> None:
    """Behind a proxy every request comes from the proxy, so the client is in X-Forwarded-For.
    Anyone else could put any address there, so it's ignored unless FORWARDED_ALLOW_IPS trusts the sender."""
    trusting = TEST_SETTINGS.model_copy(update={"forwarded_allow_ips": "10.0.0.2"})

    async with client_from("10.0.0.2", trusting) as via_proxy:
        for i in range(10):
            await _sign_in(via_proxy, f"p{i}@acme.dev", {"X-Forwarded-For": "198.51.100.1"})
        blocked = await _sign_in(via_proxy, "x@acme.dev", {"X-Forwarded-For": "198.51.100.1"})
        other_person = await _sign_in(via_proxy, "y@acme.dev", {"X-Forwarded-For": "198.51.100.2"})
    assert (blocked.status_code, other_person.status_code) == (429, 401)

    async with client_from("192.0.2.9", trusting) as direct:
        for i in range(10):
            await _sign_in(direct, f"p{i}@acme.dev", {"X-Forwarded-For": f"198.51.100.{i}"})
        spoofed = await _sign_in(direct, "x@acme.dev", {"X-Forwarded-For": "198.51.100.99"})
    assert spoofed.status_code == 429  # a made-up header doesn't buy a fresh allowance


async def test_forgot_password_is_limited_per_email_and_still_reveals_nothing(
    client: httpx.AsyncClient, outbox: FakeEmailSender
) -> None:
    await sign_up(client)
    for email in ("ali@acme.dev", "nobody@acme.dev"):
        answers = [(await client.post(f"{AUTH}/forgot-password", json={"email": email})) for _ in range(6)]
        assert [a.status_code for a in answers] == [202] * 5 + [429]
        assert answers[-1].json()["detail"] == "Too many attempts. Try again in 1 hour."
        assert 3500 < int(answers[-1].headers["retry-after"]) <= 3600
    assert len(outbox.sent) == 5


async def test_forgot_password_is_limited_per_address() -> None:
    async with client_from("203.0.113.7") as client:
        codes = [
            (await client.post(f"{AUTH}/forgot-password", json={"email": f"p{i}@acme.dev"})).status_code
            for i in range(21)
        ]
    assert codes == [202] * 20 + [429]


async def test_reset_password_is_limited_per_address(client: httpx.AsyncClient) -> None:
    body = {"token": "guess", "password": "a-new-password"}
    codes = [(await client.post(f"{AUTH}/reset-password", json=body)).status_code for _ in range(21)]
    assert codes == [400] * 20 + [429]


async def test_sign_up_is_limited_per_address(client: httpx.AsyncClient) -> None:
    for i in range(20):
        await sign_up(client, name=f"P{i}", email=f"p{i}@acme.dev")
    refused = await client.post(
        f"{AUTH}/sign-up", json={"name": "Late", "email": "late@acme.dev", "password": PASSWORD}
    )
    assert refused.status_code == 429
    assert refused.json()["detail"] == "Too many attempts. Try again in 1 hour."

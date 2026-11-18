"""`ctx.http` (plugins/authorised_http.py, ADR 0010 §8): only the plugin's hosts over https, the
credential added by BotDesk and never visible to the tool, no redirects, no private addresses,
capped size and time. No network: httpx.MockTransport, or httpcore's mock backend under the guard."""

import asyncio
import contextlib
import logging
from collections.abc import Callable

import httpcore
import httpx
import pytest
from botdesk_plugin_sdk import ApiKeyAuth, HostNotAllowed, HttpError, NotConnected, ResponseTooLarge

from src.core.url_guard import GuardedTransport
from src.plugins.authorised_http import AuthorisedHttp, guarded_client
from src.services.credential_vault import Credential, CredentialUnavailable, api_key_secret

KEY = "sk-live-TOPSECRET-000000000000000042"
HOST = "api.example.com"


def credential() -> Credential:
    return Credential(api_key_secret(KEY, ApiKeyAuth(prefix="Bearer ")))


def http_for(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    opener: Callable[[], Credential] | None = credential,
    max_bytes: int = 1024,
    timeout: float = 5,
) -> tuple[AuthorisedHttp, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = guarded_client(timeout, httpx.MockTransport(record))
    return AuthorisedHttp(client=client, egress=(HOST,), credential=opener, max_bytes=max_bytes), seen


def ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


async def test_the_credential_is_added_by_the_client_and_the_tool_cannot_replace_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    http, seen = http_for(ok)
    response = await http.request(
        "post",
        f"https://{HOST}/v1/items?x=1",
        json={"a": 1},
        headers={"authorization": "Bearer stolen", "X-Trace": "t"},
    )
    assert response.ok and response.json() == {"ok": True}
    (request,) = seen
    assert request.method == "POST"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.headers["x-trace"] == "t"
    assert http.used
    assert KEY not in repr(http) and KEY not in caplog.text and KEY not in response.url


@pytest.mark.parametrize(
    ("url", "why"),
    [
        ("https://evil.example/steal", "not one of this plugin's egress hosts"),
        (f"http://{HOST}/v1", "Only https"),
        (f"https://{HOST}.evil.example/v1", "not one of"),
        (f"https://user:pw@{HOST}/v1", "user name or password"),
        ("https://169.254.169.254/latest/meta-data/", "not one of"),
    ],
)
async def test_only_https_to_the_plugins_egress_hosts(url: str, why: str) -> None:
    http, seen = http_for(ok)
    with pytest.raises(HostNotAllowed, match=why):
        await http.request("GET", url)
    assert seen == []  # refused before anything left


async def test_a_redirect_is_never_followed() -> None:
    http, seen = http_for(lambda _r: httpx.Response(302, headers={"Location": "https://evil.example/x"}))
    with pytest.raises(HttpError, match="redirect"):
        await http.request("GET", f"https://{HOST}/v1")
    assert [request.url.host for request in seen] == [HOST]


async def test_a_response_larger_than_the_cap_is_refused() -> None:
    declared, _ = http_for(lambda _r: httpx.Response(200, content=b"x" * 2048))
    with pytest.raises(ResponseTooLarge):
        await declared.request("GET", f"https://{HOST}/big")

    async def stream() -> object:
        for _ in range(4):
            yield b"y" * 400

    chunked, _ = http_for(lambda _r: httpx.Response(200, content=stream()))  # type: ignore[arg-type]  # no length
    with pytest.raises(ResponseTooLarge):
        await chunked.request("GET", f"https://{HOST}/big")


async def test_a_slow_answer_times_out() -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200)

    seen: list[httpx.Request] = []

    class Slow(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            raise httpx.ReadTimeout("slow", request=request)

    client = guarded_client(0.1, Slow())
    http = AuthorisedHttp(client=client, egress=(HOST,), credential=credential)
    with pytest.raises(HttpError, match="took too long"):
        await http.request("GET", f"https://{HOST}/slow")
    assert guarded_client(7).timeout.read == 7


async def test_an_allowed_host_that_resolves_to_a_private_address_is_never_connected_to() -> None:
    async def resolve(_host: str) -> list[str]:
        return ["10.0.0.7"]

    backend = httpcore.AsyncMockBackend([b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"])
    transport = GuardedTransport(allow_private=False, resolve=resolve, inner=backend)
    client = guarded_client(5, transport)
    http = AuthorisedHttp(client=client, egress=(HOST,), credential=credential)
    with pytest.raises(HostNotAllowed, match="private network"):
        await http.request("GET", f"https://{HOST}/v1")
    assert not http.used
    assert client.follow_redirects is False


async def test_the_credential_is_decrypted_only_when_a_request_is_made_and_a_dead_one_is_not_connected() -> None:
    opened: list[int] = []

    def opener() -> Credential:
        opened.append(1)
        return credential()

    http, _ = http_for(ok, opener=opener)
    assert opened == []
    await http.request("GET", f"https://{HOST}/a")
    await http.request("GET", f"https://{HOST}/b")
    assert opened == [1]  # once per tool call

    def revoked() -> Credential:
        raise CredentialUnavailable("Demo was disconnected. Connect it again in Connect apps.")

    dead, seen = http_for(ok, opener=revoked)
    with pytest.raises(NotConnected, match="disconnected"):
        await dead.request("GET", f"https://{HOST}/a")
    assert seen == []


async def test_a_plugin_without_auth_calls_its_hosts_with_no_credential() -> None:
    http, seen = http_for(ok, opener=None)
    await http.request("GET", f"https://{HOST}/public", params={"q": "x"})
    assert "authorization" not in seen[0].headers
    assert seen[0].url.params["q"] == "x"


# What a failed call may have changed (ADR 0004 §2): the tool pipeline asks before it says "failed".


def answering(status: int) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(status, json={})


def raising(error: type[httpx.TransportError]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("the network", request=request)

    return handler


@pytest.mark.parametrize(
    ("handler", "changed"),
    [
        (answering(200), True),
        (answering(500), True),  # the service may have done it before failing
        (answering(302), True),  # a redirect is an answer: it got there
        (raising(httpx.ReadError), True),  # sent, then the connection dropped
        (raising(httpx.ReadTimeout), True),
        (raising(httpx.RemoteProtocolError), True),
        (answering(400), False),  # refused
        (answering(404), False),
        (answering(429), False),
        (raising(httpx.ConnectError), False),  # never left
        (raising(httpx.ConnectTimeout), False),
    ],
)
async def test_a_request_that_can_change_something_counts_until_it_certainly_had_no_effect(
    handler: Callable[[httpx.Request], httpx.Response], changed: bool
) -> None:
    http, _ = http_for(handler)
    with contextlib.suppress(HttpError):
        await http.request("POST", f"https://{HOST}/v1/send", json={"to": "sara@acme.dev"})
    assert http.may_have_changed_something is changed


async def test_reads_never_count_and_a_refusal_after_a_send_does_not_undo_it() -> None:
    reads, _ = http_for(answering(500))
    for method in ("GET", "HEAD", "OPTIONS"):
        await reads.request(method, f"https://{HOST}/v1/items")
    assert not reads.may_have_changed_something

    answers = iter([httpx.Response(200, json={}), httpx.Response(400, json={})])
    both, _ = http_for(lambda _request: next(answers))
    await both.request("POST", f"https://{HOST}/v1/send")
    await both.request("POST", f"https://{HOST}/v1/label")  # refused; the first one went through
    assert both.may_have_changed_something


async def test_refusals_before_sending_and_unbuildable_requests_never_count() -> None:
    unavailable = CredentialUnavailable("Reconnect it.")

    def broken() -> Credential:
        raise unavailable

    for http, url, body in (
        (http_for(ok)[0], "https://evil.example/send", None),  # host not allowed
        (http_for(ok, opener=broken)[0], f"https://{HOST}/send", None),  # no credential
        (http_for(ok)[0], f"https://{HOST}/send", {"when": object()}),  # not JSON
    ):
        with pytest.raises((HttpError, TypeError)):
            await http.request("POST", url, json=body)
        assert not http.may_have_changed_something


async def test_requests_sent_at_once_are_counted_one_by_one() -> None:
    """Two sends in parallel (asyncio.gather): one refused must not hide the other that may have gone."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/refused":
            await asyncio.sleep(0.01)  # both are in flight when this one is refused
            return httpx.Response(400, json={})
        await asyncio.sleep(0.05)  # answers after the refusal
        if request.url.path == "/v1/lost":
            raise httpx.ReadError("the connection dropped", request=request)
        return httpx.Response(429, json={})

    for second, changed in (("/v1/lost", True), ("/v1/limited", False)):
        client = guarded_client(5, httpx.MockTransport(handler))
        http = AuthorisedHttp(client=client, egress=(HOST,), credential=credential)
        await asyncio.gather(
            http.request("POST", f"https://{HOST}/v1/refused"),
            http.request("POST", f"https://{HOST}{second}"),
            return_exceptions=True,
        )
        assert http.may_have_changed_something is changed, second

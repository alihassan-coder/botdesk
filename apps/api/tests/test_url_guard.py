"""The SSRF guard on the wire: model calls never follow redirects, and a custom server's
connection goes to the address that was checked (DNS rebinding). No network: requests are
answered by httpx.MockTransport, and connections by httpcore's mock backend."""

from collections.abc import Iterable

import httpcore
import httpx
import pytest
from langchain_core.messages import HumanMessage

from src.core.url_guard import GuardedTransport, UnsafeUrl, check_base_url
from src.model_providers import adapter_for
from src.model_providers.anthropic import SafeChatAnthropic

PUBLIC = "93.184.216.34"
METADATA = "http://169.254.169.254/latest/meta-data/"

# Redirects on the chat path


async def test_a_custom_servers_chat_call_does_not_follow_a_redirect() -> None:
    """A server that answers the chat request with a 307 to cloud metadata gets no second
    request: the conversation and the key are never re-sent there."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(307, headers={"Location": METADATA})

    model = adapter_for("custom").chat_model(
        "llama3.2", "sk-custom-key", "https://models.example/v1", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(Exception, match="307"):
        await model.ainvoke([HumanMessage("the secret plan")])
    assert [request.url.host for request in seen] == ["models.example"]  # once, and never to 169.254.169.254


async def test_built_in_chat_models_never_follow_redirects_and_time_out() -> None:
    openai = adapter_for("openai").chat_model("gpt-5.5", "sk-test", None)
    client = openai.http_async_client  # type: ignore[attr-defined]
    assert isinstance(client, httpx.AsyncClient)
    assert client.follow_redirects is False
    assert (client.timeout.connect, client.timeout.read) == (10.0, 60.0)
    assert openai.http_client.follow_redirects is False  # type: ignore[attr-defined]

    claude = adapter_for("anthropic").chat_model("claude-opus-5-5", "sk-ant-test", None)
    assert isinstance(claude, SafeChatAnthropic)
    sdk = claude._async_client
    assert sdk._client.follow_redirects is False
    assert (sdk.timeout.connect, sdk.timeout.read) == (10.0, 60.0)  # type: ignore[union-attr]
    assert claude._client._client.follow_redirects is False


async def test_a_custom_servers_sync_calls_are_refused_rather_than_unguarded() -> None:
    model = adapter_for("custom").chat_model(
        "llama3.2", "", "https://models.example/v1", transport=httpx.MockTransport(lambda _r: httpx.Response(200))
    )
    with pytest.raises(Exception, match=r"Connection error|asynchronously"):
        model.invoke("hi")


# DNS rebinding: the checked address is the one connected to


class RecordingBackend(httpcore.AsyncMockBackend):
    """Answers every connection with a fixed HTTP reply, and remembers where it was asked to connect."""

    def __init__(self) -> None:
        super().__init__(
            [b"HTTP/1.1 200 OK\r\n", b"Content-Type: application/json\r\n", b"Content-Length: 2\r\n\r\n", b"{}"]
        )
        self.connected_to: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected_to.append((host, port))
        return await super().connect_tcp(host, port, timeout, local_address, socket_options)


class Rebinding:
    """A DNS name that answers a public address first and a private one after (rebinding)."""

    def __init__(self, *answers: list[str]) -> None:
        self.answers = list(answers)
        self.lookups = 0

    async def __call__(self, _host: str) -> list[str]:
        self.lookups += 1
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


async def test_a_name_that_rebinds_to_a_private_address_after_the_check_is_never_connected_to() -> None:
    resolve = Rebinding([PUBLIC], ["127.0.0.1"])
    backend = RecordingBackend()
    # The save-time check sees the public address...
    assert await check_base_url("http://rebind.example/v1", allow_private=False, resolve=resolve)
    # ...and the connection, which resolves for itself, sees the private one and stops.
    transport = GuardedTransport(allow_private=False, resolve=resolve, inner=backend)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(UnsafeUrl, match="private network"):
            await http.get("http://rebind.example/v1/models")
    assert backend.connected_to == []
    assert resolve.lookups == 2


async def test_the_connection_goes_to_the_checked_ip_with_the_original_host_name() -> None:
    connected_to: list[tuple[str, int]] = []
    sent: list[bytes] = []

    class Stream(httpcore.AsyncNetworkStream):
        """Wraps the mock stream to see the bytes that go out."""

        def __init__(self, inner: httpcore.AsyncNetworkStream) -> None:
            self.inner = inner

        async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:  # noqa: ASYNC109
            return await self.inner.read(max_bytes, timeout)

        async def write(self, buffer: bytes, timeout: float | None = None) -> None:  # noqa: ASYNC109
            sent.append(buffer)

        async def aclose(self) -> None:
            await self.inner.aclose()

    class Wrapping(RecordingBackend):
        """Records the address, and hands back a stream that records what's written."""

        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
            local_address: str | None = None,
            socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
        ) -> httpcore.AsyncNetworkStream:
            connected_to.append((host, port))
            return Stream(await super().connect_tcp(host, port, timeout, local_address, socket_options))

    async def public(_host: str) -> list[str]:
        return [PUBLIC]

    transport = GuardedTransport(allow_private=False, resolve=public, inner=Wrapping())
    async with httpx.AsyncClient(transport=transport) as http:
        response = await http.get("http://models.example:8080/v1/models")
    assert response.json() == {}
    assert connected_to == [(PUBLIC, 8080)]  # the IP that was checked, not the name
    assert b"Host: models.example:8080" in b"".join(sent)  # the server still sees its own name


async def test_one_private_address_among_public_ones_is_refused_at_connect_time() -> None:
    async def mixed(_host: str) -> list[str]:
        return [PUBLIC, "10.0.0.7"]

    backend = RecordingBackend()
    async with httpx.AsyncClient(transport=GuardedTransport(allow_private=False, resolve=mixed, inner=backend)) as http:
        with pytest.raises(UnsafeUrl):
            await http.get("http://mixed.example/v1/models")
        with pytest.raises(UnsafeUrl):
            await http.get(METADATA)  # an IP literal is checked too
    assert backend.connected_to == []


async def test_private_addresses_connect_when_the_server_allows_them() -> None:
    async def local(_host: str) -> list[str]:
        return ["127.0.0.1"]

    backend = RecordingBackend()
    async with httpx.AsyncClient(transport=GuardedTransport(allow_private=True, resolve=local, inner=backend)) as http:
        assert (await http.get("http://localhost:11434/v1/models")).status_code == 200
    assert backend.connected_to == [("127.0.0.1", 11434)]

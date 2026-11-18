"""`ctx.http`: the HTTP client a tool gets, bound to its plugin's hosts and (maybe) one connection.

ADR 0010 §8. A tool never sees a token; this client:

- allows only `https` URLs whose host is in the plugin's manifest `egress` (exact host names),
  checked before anything leaves, with httpx's own URL parser (the host checked is the host called);
- adds the connection's credential itself, after the tool's own headers, so a tool can't replace
  or read it. The credential is decrypted on the first request, not before;
- never follows redirects: a 3xx answer fails the call, so a credential can't be bounced elsewhere;
- connects through `GuardedTransport` (core/url_guard.py) with private addresses always refused,
  so an allowed name that resolves to 10.0.0.1 or 169.254.169.254 is never reached;
- reads at most `max_bytes` of a response and gives up after `timeout_seconds`;
- logs method, host, path and status only: never headers, query strings or bodies;
- remembers whether a request that can change something (any method but GET, HEAD and OPTIONS)
  may have reached the other app: `may_have_changed_something`. The tool pipeline reads it when a
  call fails, so a send that may have gone out is never reported as failed (ADR 0004 §2). Such a
  request counts from the moment it is sent, and stops counting only when it certainly had no
  effect: no connection could be made, or the answer was a 4xx refusal.

Every refusal is an SDK `HttpError` whose message is safe for the model and for people.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import httpx
from botdesk_plugin_sdk import HostNotAllowed, HttpError, HttpResponse, NotConnected, ResponseTooLarge
from botdesk_plugin_sdk.http import Params

from src.core.url_guard import GuardedTransport, UnsafeUrl
from src.services.credential_vault import Credential, CredentialUnavailable

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
REDIRECTS = {301, 302, 303, 307, 308}
# Methods that only read (RFC 9110 "safe"): a request with any other method may change something.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Failures that mean the request never left: no connection was made.
_NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class RebaseHosts(httpx.AsyncBaseTransport):
    """Tests only: sends requests for some hosts to a fake server instead (GMAIL_API_BASE_URL).
    The URL a tool asked for is checked against its egress before this runs."""

    def __init__(self, inner: httpx.AsyncBaseTransport, hosts: Mapping[str, str]) -> None:
        self._inner = inner
        self._hosts = {host: httpx.URL(base) for host, base in hosts.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if base := self._hosts.get(request.url.host):
            request.url = request.url.copy_with(
                scheme=base.scheme, host=base.host, port=base.port, path=base.path.rstrip("/") + request.url.path
            )
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def guarded_client(
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    rebase: Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    """An httpx client for tool calls: guarded transport (private addresses refused), no redirects,
    no proxy from the environment. `transport` replaces the network in tests. `rebase` (tests
    only, {host: fake base URL}) sends those hosts to a fake server, which may be on a private
    address such as 127.0.0.1."""
    inner = transport or GuardedTransport(allow_private=bool(rebase))
    return httpx.AsyncClient(
        transport=RebaseHosts(inner, rebase) if rebase else inner,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(timeout_seconds),
    )


class AuthorisedHttp:
    """The SDK's `HttpClient` for one tool call. Holds no open resources of its own: `client` is
    owned (and closed) by whoever made it."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        egress: Iterable[str],
        credential: Callable[[], Credential] | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._client = client
        self._hosts = frozenset(egress)
        self._open_credential = credential
        self._credential: Credential | None = None
        self._max_bytes = max_bytes
        self.used = False  # at least one request reached the service
        # A request that can change something (POST, PUT, PATCH, DELETE…) was sent and didn't
        # certainly fail before the service acted on it: the service may have done it.
        self.may_have_changed_something = False

    def __repr__(self) -> str:
        return f"AuthorisedHttp(hosts={sorted(self._hosts)})"

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Params | None = None,
        json: Any = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        target = self._allowed(url)
        merged = dict(headers or {})
        if self._open_credential is not None:
            auth = self._auth_headers()
            taken = {name.lower() for name in auth}
            # The tool can't set (or overwrite) the credential's own header.
            merged = {name: value for name, value in merged.items() if name.lower() not in taken} | auth
        # Built first, so a request that can't even be built (say, a body that isn't JSON) is
        # refused before anything counts as sent.
        request = self._client.build_request(
            method.upper(), target, params=dict(params or {}), json=json, data=data, headers=merged
        )
        changes = request.method not in SAFE_METHODS
        changed_before = self.may_have_changed_something
        if changes:
            self.may_have_changed_something = True  # from here on the service may act on it
        try:
            response = await self._client.send(request, stream=True)
            try:
                if changes and 400 <= response.status_code < 500:
                    self.may_have_changed_something = changed_before  # refused: the service didn't do it
                if response.status_code in REDIRECTS:
                    raise HttpError(
                        f"{target.host} answered with a redirect ({response.status_code}). "
                        "Tools never follow redirects; call the final address directly."
                    )
                content = await self._read_capped(response, target.host)
            finally:
                await response.aclose()
        except UnsafeUrl as error:  # refused before connecting
            self.may_have_changed_something = changed_before
            raise HostNotAllowed(
                f"{target.host} resolves to a private network address, which tools can't reach."
            ) from error
        except _NEVER_SENT as error:
            self.may_have_changed_something = changed_before
            raise HttpError(_failure_text(error, target.host)) from error
        except httpx.HTTPError as error:
            raise HttpError(_failure_text(error, target.host)) from error
        self.used = True
        logger.info("Tool request %s %s%s → %s", method.upper(), target.host, target.path, response.status_code)
        return HttpResponse(
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            content=content,
            url=str(target.copy_with(query=None)),
        )

    def _allowed(self, url: str) -> httpx.URL:
        try:
            target = httpx.URL(url)
        except httpx.InvalidURL as error:
            raise HostNotAllowed("That isn't a valid address.") from error
        if target.scheme != "https":
            raise HostNotAllowed(f"Only https addresses are allowed (got {target.scheme or 'none'}).")
        if target.userinfo:
            raise HostNotAllowed("Addresses with a user name or password aren't allowed.")
        if target.host not in self._hosts:
            raise HostNotAllowed(f"{target.host or 'That address'} is not one of this plugin's egress hosts.")
        return target

    def _auth_headers(self) -> dict[str, str]:
        if self._credential is None:
            assert self._open_credential is not None
            try:
                self._credential = self._open_credential()
            except CredentialUnavailable as error:
                raise NotConnected(str(error)) from error
        return self._credential.auth_headers()

    async def _read_capped(self, response: httpx.Response, host: str) -> bytes:
        too_large = ResponseTooLarge(f"{host}'s answer is larger than {self._max_bytes // 1024} KB, the limit.")
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_bytes:
            raise too_large
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self._max_bytes:
                raise too_large
            chunks.append(chunk)
        return b"".join(chunks)


def _failure_text(error: httpx.HTTPError, host: str) -> str:
    if isinstance(error, httpx.TimeoutException):
        return f"{host} took too long to answer."
    return f"Couldn't reach {host} ({type(error).__name__})."

"""What every model provider adapter does, and the shapes they share.

An adapter knows one provider's HTTP API: how to list its models (which is also how a key is
tested), and how to build a LangChain chat model for a run. It holds no keys: the caller passes
the key in for each call, decrypted only for that call.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from langchain_core.language_models import BaseChatModel

# Listing models should be quick; a provider that takes longer is treated as down.
LIST_TIMEOUT = httpx.Timeout(8.0, connect=4.0)

# Chat replies stream. httpx's read timeout is the longest wait for the *next* bytes, not for the
# whole reply, so a long answer that keeps streaming is fine, while a server that goes silent for
# a minute (or never answers at all) fails the run instead of holding it until RUN_MAX_SECONDS.
CHAT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# Things that look like API keys, for scrubbing provider messages ("Incorrect API key: sk-ab…12").
_KEY_LIKE = re.compile(r"\b(?:sk-|sk_|gsk_|xai-)[A-Za-z0-9_\-*.…]{4,}|\bAIza[A-Za-z0-9_\-]{10,}|\b[A-Za-z0-9_]{32,}\b")
MAX_MESSAGE = 200


@dataclass(frozen=True)
class Pricing:
    """US dollars per million tokens."""

    input_per_mtok: float
    output_per_mtok: float


@dataclass(frozen=True)
class ModelInfo:
    """One model a provider offers right now. `model` is the provider's own id."""

    model: str
    name: str
    context_window: int | None = None
    pricing: Pricing | None = None


class ProviderError(Exception):
    """The provider refused (bad key, no access) or couldn't be reached. The message is safe to show:
    it never contains the key."""


class ProviderAdapter(Protocol):
    async def list_models(self, http: httpx.AsyncClient, api_key: str, base_url: str | None) -> list[ModelInfo]: ...

    def chat_model(
        self, model: str, api_key: str, base_url: str | None, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> BaseChatModel:
        """`transport` carries the requests: a `GuardedTransport` for custom servers (so the
        address that was checked is the one connected to), or None for httpx's own."""
        ...


class _ChatHttpClient(httpx.AsyncClient):
    """A chat model's own client; it closes itself once the model is garbage-collected (as the
    provider SDKs' default clients do), since a run doesn't say when it's done with a model."""

    def __del__(self) -> None:
        try:
            if not self.is_closed:
                asyncio.get_running_loop().create_task(self.aclose())
        except Exception:  # noqa: S110 - no running loop (interpreter shutdown): nothing to close on
            pass


class _NoSyncCalls(httpx.BaseTransport):
    """Sync calls can't use the address pinning (`GuardedTransport` is async), so a custom
    server's model refuses them rather than quietly skipping the guard. Runs are async."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.UnsupportedProtocol("Custom model servers are only called asynchronously.", request=request)


def sync_chat_http_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.Client:
    """The sync twin of `chat_http_client`, so a sync call can't fall back to the SDK's
    redirect-following client either."""
    return httpx.Client(
        transport=None if transport is None else _NoSyncCalls(), follow_redirects=False, timeout=CHAT_TIMEOUT
    )


def chat_http_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """The HTTP client for a chat model. The provider SDKs follow redirects by default
    (`follow_redirects=True`); this one never does, so a model server can't bounce the request,
    with the conversation and the key in it, to another address (SSRF, e.g. cloud metadata at
    169.254.169.254). It also sets `CHAT_TIMEOUT` instead of the SDKs' 10 minutes."""
    return _ChatHttpClient(transport=transport, follow_redirects=False, timeout=CHAT_TIMEOUT)


def scrub(text: str, *secrets: str) -> str:
    """A provider's message, shortened, with the key (and anything that looks like one) taken out."""
    for secret in sorted(secrets, key=len, reverse=True):  # longest first, so no key is left half-replaced
        if secret:
            text = text.replace(secret, "[key]")
    text = _KEY_LIKE.sub("[key]", " ".join(text.split()))
    return text if len(text) <= MAX_MESSAGE else text[: MAX_MESSAGE - 1] + "…"


def _error_text(response: httpx.Response) -> str:
    """Providers wrap errors differently: {"error": {"message"}}, {"error": "…"}, [{"error": {…}}]."""
    try:
        body: Any = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or response.reason_phrase)
        return str(error)
    return response.reason_phrase


async def get_json(
    http: httpx.AsyncClient,
    url: str,
    *,
    api_key: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    """GET a provider's JSON. Any failure becomes a `ProviderError` whose message is safe to show."""
    try:
        response = await http.get(url, headers=headers, params=params, timeout=LIST_TIMEOUT)
    except httpx.TimeoutException as error:
        raise ProviderError("it didn't answer in time") from error
    except httpx.HTTPError as error:
        raise ProviderError(f"we couldn't reach it ({type(error).__name__})") from error
    if response.status_code >= 400:
        raise ProviderError(f"{response.status_code}: {scrub(_error_text(response), api_key)}")
    try:
        return response.json()
    except ValueError as error:
        raise ProviderError("it didn't answer with JSON. Is the address right?") from error

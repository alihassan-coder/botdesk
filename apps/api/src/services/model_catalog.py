"""Live model lists from the providers, with a short in-memory cache.

Model lists change (new models, retired ones), so they're fetched from each provider rather than
kept in the database. Fetching takes a second or so, and every bot editor asks, so each
organization's list per provider is kept for `ttl_seconds` (10 minutes). The cache key includes a
fingerprint of the key and base URL, so replacing a key never serves the old key's list.

One catalog per API process, created in the app's lifespan with two HTTP clients: the shared
one for the built-in providers (fixed public addresses), and one for custom servers whose
`GuardedTransport` connects only to checked public addresses (see `core/url_guard.py`).
"""

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

from src.core.errors import AppError
from src.core.url_guard import check_base_url
from src.model_providers import ModelInfo, ProviderError, adapter_for
from src.schemas.provider import ModelListOut, ModelOut, PricingOut, ProviderProblem
from src.services.provider_service import Connection

log = logging.getLogger(__name__)

CACHE_SECONDS = 600.0


@dataclass(frozen=True)
class _Entry:
    fingerprint: str
    expires_at: float
    models: list[ModelInfo]


def _fingerprint(connection: Connection) -> str:
    return hashlib.sha256(f"{connection.api_key}\0{connection.base_url or ''}".encode()).hexdigest()


def model_out(provider_id: str, info: ModelInfo) -> ModelOut:
    pricing = info.pricing
    return ModelOut(
        id=f"{provider_id}:{info.model}",
        provider=provider_id,
        name=info.name,
        context_window=info.context_window,
        pricing=PricingOut(input_per_mtok=pricing.input_per_mtok, output_per_mtok=pricing.output_per_mtok)
        if pricing
        else None,
    )


class ModelCatalog:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        allow_private_urls: bool,
        custom_http: httpx.AsyncClient | None = None,
        ttl_seconds: float = CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.http = http
        self.custom_http = custom_http or http
        self.allow_private_urls = allow_private_urls
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._cache: dict[tuple[uuid.UUID, str], _Entry] = {}

    async def fetch(self, connection: Connection) -> list[ModelInfo]:
        """Ask the provider now. This is also how a key is tested. Raises `ProviderError`, or
        `UnsafeUrl` for a custom server on an address this server may not call."""
        base_url = connection.base_url
        http = self.http
        if connection.kind == "custom":
            http = self.custom_http
            if base_url:
                base_url = await check_base_url(base_url, allow_private=self.allow_private_urls)
        return await adapter_for(connection.kind).list_models(http, connection.api_key, base_url)

    async def models(self, org_id: uuid.UUID, connection: Connection, *, refresh: bool = False) -> list[ModelInfo]:
        key = (org_id, connection.provider_id)
        fingerprint = _fingerprint(connection)
        entry = self._cache.get(key)
        if not refresh and entry and entry.fingerprint == fingerprint and entry.expires_at > self.clock():
            return entry.models
        models = await self.fetch(connection)
        self.remember(org_id, connection, models)
        return models

    def remember(self, org_id: uuid.UUID, connection: Connection, models: list[ModelInfo]) -> None:
        entry = _Entry(_fingerprint(connection), self.clock() + self.ttl_seconds, models)
        self._cache[(org_id, connection.provider_id)] = entry

    def cached(self, org_id: uuid.UUID, provider_id: str) -> list[ModelInfo] | None:
        """The last list fetched for this provider, even if it's past its 10 minutes: prices
        read from it for usage records don't need to be fresh to the second. None if never fetched."""
        entry = self._cache.get((org_id, provider_id))
        return entry.models if entry else None

    def forget(self, org_id: uuid.UUID, provider_id: str) -> None:
        self._cache.pop((org_id, provider_id), None)

    async def merged(
        self, org_id: uuid.UUID, connections: Sequence[Connection], *, refresh: bool = False
    ) -> ModelListOut:
        """Every connected provider's models, asked at the same time. A provider that fails is
        reported in `errors`; the others' models still come back."""
        results = await asyncio.gather(
            *(self.models(org_id, c, refresh=refresh) for c in connections), return_exceptions=True
        )
        models: list[ModelOut] = []
        errors: list[ProviderProblem] = []
        for connection, result in zip(connections, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                errors.append(ProviderProblem(provider=connection.provider_id, message=_problem(connection, result)))
            else:
                models.extend(model_out(connection.provider_id, info) for info in result)
        return ModelListOut(models=models, errors=errors)


def _problem(connection: Connection, error: Exception) -> str:
    if isinstance(error, ProviderError):
        return f"{connection.name}: {error}"
    if isinstance(error, AppError):  # e.g. UnsafeUrl: its message is written for people
        return f"{connection.name}: {error.message}"
    log.error("Listing %s's models failed: %s", connection.provider_id, type(error).__name__)
    return f"{connection.name} didn't answer."

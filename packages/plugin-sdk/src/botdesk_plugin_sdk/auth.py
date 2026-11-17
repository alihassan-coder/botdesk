"""Accounts: how a plugin's connections are authorised (ADR 0010 §5-§7).

A plugin that works on someone's account declares one of these as `PluginManifest.auth`. People
connect the account in Connect apps; BotDesk keeps the credential encrypted and adds it to each
request a tool makes through `ctx.http`. The plugin never sees it.

- `ApiKeyAuth`: a key someone pastes, sent in one header on every request.
- `OAuth2Auth`: sign in with the provider. Endpoints and scope sets live here, so BotDesk's one
  OAuth flow serves every provider.
"""

import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from botdesk_plugin_sdk.http import HttpClient

OwnerKind = Literal["member", "bot", "org"]
"""Whose account a connection is: one member's, a bot's own, or the organization's (shared)."""


@dataclass(frozen=True)
class ApiKeyAuth:
    """Send the key as `{header}: {prefix}{key}`. `ApiKeyAuth()` is `Authorization: <key>`;
    `ApiKeyAuth(prefix="Bearer ")` is a bearer token; `ApiKeyAuth(header="X-Api-Key")` a custom header."""

    header: str = "Authorization"
    prefix: str = ""


@dataclass(frozen=True)
class AccountIdentity:
    """Who a newly connected account is: `label` is shown to people ("ali@acme.dev"), `ref` is
    the provider's stable id for it, so connecting the same account twice updates one connection."""

    label: str
    ref: str


AccountHandler = Callable[[HttpClient], Awaitable[AccountIdentity]]
"""`async def account(http) -> AccountIdentity`: called once after sign-in, with an `http` that
already carries the new token."""


@dataclass(frozen=True)
class OAuth2Auth:
    """Sign in with an OAuth 2 provider (authorization code with PKCE).

    `scope_sets` are the access levels people choose between when connecting ("read", "full"),
    each the scopes to ask for. A tool's `scopes` must come from these sets.

    `implied_scopes` says which scopes a broader one already gives, when the provider works that
    way: Google's `gmail.modify` includes `gmail.readonly`, so `{MODIFY: (READONLY,)}` lets a tool
    that needs `gmail.readonly` run on a connection granted only `gmail.modify`."""

    provider: str  # "google": which client id/secret the server uses
    authorize_url: str
    token_url: str
    scope_sets: Mapping[str, tuple[str, ...]]
    revoke_url: str | None = None
    extra_authorize_params: Mapping[str, str] = field(default_factory=dict)
    account: AccountHandler | None = None
    implied_scopes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def effective_scopes(self, granted: Iterable[str]) -> frozenset[str]:
        """What a connection granted `granted` can do: those scopes and the ones they imply."""
        scopes = set(granted)
        for scope in list(scopes):
            scopes.update(self.implied_scopes.get(scope, ()))
        return frozenset(scopes)


Auth = ApiKeyAuth | OAuth2Auth


@dataclass(frozen=True)
class ConnectionInfo:
    """The account a tool call works on, as the tool may see it. Never a secret."""

    id: uuid.UUID
    connector_id: str  # the plugin id
    account_label: str  # "ali@acme.dev"
    owner_kind: OwnerKind
    scopes: tuple[str, ...] = ()  # granted, not merely asked for

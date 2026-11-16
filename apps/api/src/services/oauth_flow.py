"""OAuth connections: signing in with a provider, keeping the token fresh, and revoking it
(ADR 0010 §5-§6, ADR 0011 §6; the contract is docs/architecture/connections-api-contract.md).

    url = await oauth.start(db, actor, connector, body)       # → the provider's sign-in page
    connection = await oauth.finish(db, state=…, code=…, error=…, iss=…, session_user=user)
    connection = await oauth.refresh(sessionmaker, connection, connector)   # ToolAccessProvider.open
    await oauth.revoke(connector, token)                       # after a disconnect is committed

- **Start** stores one `oauth_flows` row: the state's sha256 (never the state), the PKCE verifier
  sealed with the vault's key, the owner and the scopes asked for. It lives 10 minutes.
- **Finish** deletes that row first (`DELETE … RETURNING`, by state hash *and* user), so a state
  works once and only for whoever started it. It re-checks membership and the owner rule, then
  exchanges the code and looks the account up with no transaction open, and saves the connection
  (an upsert by account: connecting again is a reconnect) in one short transaction.
- **Refresh**: whoever wins the lease (`refresh_lease_until`) calls the token endpoint, again
  with no transaction open; the others wait for its result. `invalid_grant` sets
  `needs_reconnect` and writes an audit line. Any other failure backs off for a few seconds
  (callers go on with the token they have); a crash gives the lease back. The new token is saved
  only into the row as it was read: a disconnect (or reconnect) meanwhile wins.
- **Revoke** is best effort, after the disconnect is committed: nothing it meets is raised.

Nothing here logs, returns or redirects with a token, a code, a verifier or the client secret,
and the provider's own error text never reaches the browser. `FlowFailed.code` is one of the
callback's result codes. The HTTP client takes an injectable transport (tests pass
`httpx.MockTransport`); the default connects through the SSRF guard and never follows redirects.
"""

import asyncio
import base64
import hashlib
import logging
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, cast
from urllib.parse import urlencode, urlsplit

import httpx
from botdesk_plugin_sdk import AccountIdentity, OAuth2Auth, PluginManifest
from pydantic import SecretStr
from sqlalchemy import CursorResult, delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.database import as_utc, utcnow
from src.core.errors import AppError, BadRequest
from src.core.secrets import SecretUnreadable
from src.core.url_guard import GuardedTransport
from src.models import Connection, User
from src.models import OAuthFlow as FlowRow
from src.plugins.authorised_http import AuthorisedHttp
from src.plugins.registry import ToolRegistry
from src.schemas.connection import OAuthStartIn
from src.services import connection_service, organization_service
from src.services.connection_service import Actor, Owner
from src.services.credential_vault import Credential, CredentialVault, oauth_secret

logger = logging.getLogger(__name__)

CALLBACK_PATH = "/api/v1/oauth/callback"
FLOW_LIFETIME = timedelta(minutes=10)
REFRESH_MARGIN = timedelta(seconds=60)  # refresh a token with less than this left
LEASE = timedelta(seconds=15)  # one refresh at a time per connection; the others wait this long at most
# The whole token call (connect, send, read) gives up after this, so the lease always outlives it.
TOKEN_CALL_BUDGET = timedelta(seconds=10)
# After a refresh that may work next time (network, 5xx, the guard), no one tries again for this
# long: the lease is kept this short while. A lease with at most this left is never waited for.
BACKOFF = timedelta(seconds=4)
LEASE_POLL_SECONDS = 0.2
# A token answer whose `expires_in` is missing or unreadable: assume Google's usual hour.
DEFAULT_TOKEN_LIFETIME = 3600
MAX_TOKEN_LIFETIME = 366 * 24 * 3600
HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

GOOGLE = "google"
GOOGLE_ISSUER = "https://accounts.google.com"  # the `iss` Google adds to the callback (RFC 9207)
# Providers that advertise `authorization_response_iss_parameter_supported` (RFC 9207 §3): their
# callback must carry this `iss`, and one without it is refused. Google's discovery document does.
ISSUERS = {GOOGLE: GOOGLE_ISSUER}
GMAIL_API_HOST = "gmail.googleapis.com"

FlowCode = Literal["denied", "expired", "not-configured", "signed-out", "forbidden", "failed"]
SetupState = Literal["ready", "not-configured"]

# An OAuth error code (`invalid_grant`) is safe to log; its `error_description` may not be.
_ERROR_CODE = re.compile(r"^[a-z_]{1,40}$")


class FlowFailed(Exception):
    """A sign-in that produced no connection. `code` is what the browser is told (the callback's
    result codes); `reason` is for the log and never holds a secret or the provider's words."""

    def __init__(self, code: FlowCode, reason: str = "") -> None:
        super().__init__(f"{code}: {reason}" if reason else code)
        self.code: FlowCode = code
        self.reason = reason


@dataclass(frozen=True)
class OAuthClient:
    """This server's client at one provider (Google: GOOGLE_OAUTH_CLIENT_ID / _SECRET)."""

    client_id: str
    client_secret: SecretStr = field(repr=False)


def client_for(settings: Settings, provider: str) -> OAuthClient | None:
    """The server's client for `provider`, or None when it isn't set up. Only Google so far."""
    if provider == GOOGLE:
        client_id = settings.google_oauth_client_id.strip()
        secret = settings.google_oauth_client_secret.get_secret_value().strip()
        if client_id and secret:
            return OAuthClient(client_id, SecretStr(secret))
    return None


def setup_state(settings: Settings, connector: PluginManifest) -> SetupState:
    """`not-configured` for an OAuth app whose provider has no client here; everything else is ready."""
    auth = connector.auth
    if isinstance(auth, OAuth2Auth) and client_for(settings, auth.provider) is None:
        return "not-configured"
    return "ready"


def default_access(auth: OAuth2Auth) -> str | None:
    """`full` when the app offers it, otherwise its first access level."""
    levels = list(auth.scope_sets)
    return "full" if "full" in levels else (levels[0] if levels else None)


def needs_refresh(connection: Connection) -> bool:
    expires = connection.access_expires_at
    return expires is not None and as_utc(expires) - utcnow() < REFRESH_MARGIN


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _challenge(verifier: str) -> str:
    """PKCE S256: base64url of the verifier's sha256, without padding."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


@dataclass(frozen=True)
class _Flow:
    """A consumed `oauth_flows` row."""

    org_id: uuid.UUID
    user_id: uuid.UUID
    code_verifier_encrypted: str
    connector_id: str
    owner_kind: str
    owner_bot_id: uuid.UUID | None
    access: str
    scopes: list[str]
    expires_at: datetime


@dataclass(frozen=True, repr=False)
class _Tokens:
    """A token endpoint's answer. Its repr hides the tokens."""

    access_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int  # seconds; DEFAULT_TOKEN_LIFETIME when the answer had none we could read
    scope: str | None


class _TokenRefused(Exception):
    """The token endpoint said no. `error` is its OAuth error code ("invalid_grant") or ""."""

    def __init__(self, status: int, error: str) -> None:
        super().__init__(f"{status} {error}".strip())
        self.error = error


class _Rebase(httpx.AsyncBaseTransport):
    """Tests only: sends requests for some hosts to a fake server (GMAIL_API_BASE_URL)."""

    def __init__(self, inner: httpx.AsyncBaseTransport, hosts: dict[str, str]) -> None:
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


class OAuth:
    """One per app (`app.state.oauth`) and one per run manager (for refresh). `transport`
    replaces the network (tests); `registry` is the loaded plugins."""

    def __init__(
        self,
        settings: Settings,
        vault: CredentialVault,
        registry: ToolRegistry,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.vault = vault
        self.registry = registry
        self.transport = transport

    def __repr__(self) -> str:
        return "OAuth(<hidden>)"

    @property
    def redirect_uri(self) -> str:
        return self.settings.api_public_url.rstrip("/") + CALLBACK_PATH

    # Start

    async def start(self, db: AsyncSession, actor: Actor, connector: PluginManifest, body: OAuthStartIn) -> str:
        """The provider's sign-in URL for a new (or renewed) connection. The caller commits.
        Raises `BadRequest`, `Forbidden` or `NotFound` with a sentence people can read."""
        auth = connector.auth
        if not isinstance(auth, OAuth2Auth):
            raise BadRequest(f"{connector.name} doesn't connect by signing in.")
        client = client_for(self.settings, auth.provider)
        if client is None:
            raise BadRequest(f"{connector.name} isn't set up on this server yet.")
        access = body.access or default_access(auth)
        if access is None or access not in auth.scope_sets:
            raise BadRequest(f"{connector.name} has no access level called {body.access!r}.")
        owner = await connection_service.owner_for_create(db, actor, body.owner_kind, body.bot_id)

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        scopes = list(auth.scope_sets[access])
        now = utcnow()
        await db.execute(delete(FlowRow).where(FlowRow.expires_at < now))  # tidy up abandoned ones
        db.add(
            FlowRow(
                org_id=actor.org_id,
                user_id=actor.user_id,
                state_hash=_sha256(state),
                code_verifier_encrypted=self.vault.seal(verifier),
                connector_id=connector.id,
                owner_kind=owner.kind,
                owner_bot_id=owner.bot_id,
                access=access,
                scopes=scopes,
                expires_at=now + FLOW_LIFETIME,
            )
        )
        params = {
            **auth.extra_authorize_params,
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
        return f"{self._endpoint(auth, auth.authorize_url)}?{urlencode(params)}"

    # Finish

    async def finish(
        self,
        db: AsyncSession,
        *,
        state: str | None,
        code: str | None,
        error: str | None = None,
        iss: str | None = None,
        session_user: User | None,
    ) -> Connection:
        """The connection a sign-in made (created, or reconnected). Commits; raises `FlowFailed`.

        Each database step is its own short transaction: no transaction is open while the
        provider is called."""
        flow = None
        if session_user is not None and state:
            flow = await self._consume(db, state, session_user.id)
            await db.commit()
        if error:
            raise FlowFailed("denied")
        if session_user is None:
            raise FlowFailed("signed-out")
        if flow is None or as_utc(flow.expires_at) <= utcnow():
            raise FlowFailed("expired")
        connector = self.registry.plugin(flow.connector_id)
        auth = connector.auth if connector is not None else None
        if connector is None or not isinstance(auth, OAuth2Auth):
            raise FlowFailed("failed", f"{flow.connector_id} is no longer loaded")
        client = client_for(self.settings, auth.provider)
        if client is None:
            raise FlowFailed("not-configured")
        if not code:
            raise FlowFailed("failed", "no code in the callback")
        issuer = self._issuer(auth)
        if issuer is not None and iss != issuer:  # RFC 9207: a mix-up attack, or a missing `iss`
            raise FlowFailed("failed", "the callback's issuer is missing or another one")
        actor, owner = await self._still_allowed(db, flow, session_user)
        await db.rollback()  # end the read before the network

        try:
            verifier = self.vault.unseal(flow.code_verifier_encrypted)
        except SecretUnreadable as unreadable:
            raise FlowFailed("failed", "the verifier can't be read (SECRET_KEY changed?)") from unreadable
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": client.client_id,
            "client_secret": client.client_secret.get_secret_value(),
            "code_verifier": verifier,
        }
        try:
            tokens = await self._token_call(auth, form)
        except (_TokenRefused, httpx.HTTPError, ValueError) as failed:
            raise FlowFailed("failed", f"the code exchange failed ({_describe(failed)})") from failed
        identity = await self._identity(connector, auth, tokens)
        scopes = tokens.scope.split() if tokens.scope else list(flow.scopes)

        try:
            connection = await connection_service.save_account(
                db,
                actor,
                connector.id,
                owner,
                auth_type="oauth2",
                label=identity.label.strip()[:200],
                ref=identity.ref.strip()[:255],
                scopes=scopes,
                save_secret=lambda row: self._save_tokens(row, tokens),
                details={"access": flow.access},
            )
        except AppError as conflict:
            raise FlowFailed("failed", conflict.message) from conflict
        await db.commit()
        logger.info("Connected %s for %s (%s).", connector.id, owner.kind, flow.access)
        return connection

    async def _consume(self, db: AsyncSession, state: str, user_id: uuid.UUID) -> _Flow | None:
        """Delete the flow and return it, in one statement: a state is used at most once, and
        only by the member who started it (anyone else's attempt changes nothing)."""
        statement = (
            delete(FlowRow)
            .where(FlowRow.state_hash == _sha256(state), FlowRow.user_id == user_id)
            .returning(
                FlowRow.org_id,
                FlowRow.user_id,
                FlowRow.code_verifier_encrypted,
                FlowRow.connector_id,
                FlowRow.owner_kind,
                FlowRow.owner_bot_id,
                FlowRow.access,
                FlowRow.scopes,
                FlowRow.expires_at,
            )
        )
        row = (await db.execute(statement)).one_or_none()
        return _Flow(**row._asdict()) if row is not None else None

    async def _still_allowed(self, db: AsyncSession, flow: _Flow, user: User) -> tuple[Actor, Owner]:
        """Ten minutes is long enough to leave the organization or lose a role."""
        found = await organization_service.org_and_role(db, org_id=flow.org_id, user_id=user.id)
        if found is None:
            raise FlowFailed("forbidden", "no longer a member")
        actor = Actor(org_id=flow.org_id, user_id=user.id, role=found[1])
        try:
            owner = await connection_service.owner_for_create(db, actor, flow.owner_kind, flow.owner_bot_id)
        except AppError as refused:
            raise FlowFailed("forbidden", refused.message) from refused
        return actor, owner

    async def _identity(self, connector: PluginManifest, auth: OAuth2Auth, tokens: _Tokens) -> AccountIdentity:
        """Who signed in, from the plugin's `account` handler, through an `AuthorisedHttp` that holds
        the new token and only reaches the plugin's egress hosts."""
        if auth.account is None:
            return AccountIdentity(label=connector.name, ref="default")
        credential = Credential(oauth_secret(tokens.access_token, None, tokens.token_type))
        try:
            async with self._client() as client:
                http = AuthorisedHttp(client=client, egress=connector.egress, credential=lambda: credential)
                identity = await auth.account(http)
        except Exception as failed:  # a plugin's handler can raise anything
            raise FlowFailed("failed", f"the account lookup failed ({type(failed).__name__})") from failed
        if not (isinstance(identity, AccountIdentity) and identity.label.strip() and identity.ref.strip()):
            raise FlowFailed("failed", "the account lookup returned no account")
        return identity

    def _save_tokens(self, connection: Connection, tokens: _Tokens) -> None:
        """Into the row through the vault. No new refresh token (Google often sends none on a
        refresh, sometimes on a reconnect): keep the one it had."""
        refresh = tokens.refresh_token
        if refresh is None and connection.encrypted_secret:
            kept = self.vault.refresh_token(connection)
            refresh = kept.get_secret_value() if kept else None
        self.vault.save(connection, oauth_secret(tokens.access_token, refresh, tokens.token_type))
        now = utcnow()
        connection.access_expires_at = now + timedelta(seconds=tokens.expires_in)
        connection.last_refreshed_at = now
        connection.refresh_lease_until = None

    # Refresh

    async def refresh(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        connection: Connection,
        connector: PluginManifest,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> Connection:
        """The connection with a token good for at least a minute more, refreshed if needed.
        Returned `needs_reconnect` when the provider refused the refresh token (`invalid_grant`),
        and `revoked` when it was disconnected while the token was on its way.

        Two calls at once make one token request: the one that wins the lease refreshes, the
        others re-read the row until it's done (at most `LEASE`). The lease after the winner:
        - success or `invalid_grant`: cleared;
        - a failure that may pass (network, timeout, 5xx, the SSRF guard, an answer with no
          token): kept for `BACKOFF`, so concurrent calls don't all hit the token endpoint again;
          every caller goes on with the token it has (still valid for up to a minute);
        - anything else (a bug, the database, a cancellation): cleared at once, then re-raised."""
        auth = connector.auth
        if not isinstance(auth, OAuth2Auth) or connection.status != "active" or not needs_refresh(connection):
            return connection
        now = utcnow()
        async with sessionmaker() as db:
            won = cast(
                CursorResult[Any],
                await db.execute(
                    update(Connection)
                    .where(
                        Connection.id == connection.id,
                        or_(Connection.refresh_lease_until.is_(None), Connection.refresh_lease_until < now),
                    )
                    .values(refresh_lease_until=now + LEASE)
                ),
            )
            await db.commit()
            # Someone may have refreshed between our read and the lease (and a provider that
            # rotates refresh tokens would refuse the one we read): work from the row as it is now.
            current = await db.get(Connection, connection.id, populate_existing=True) if won.rowcount == 1 else None
            await db.commit()
        if won.rowcount != 1:
            return await self._wait_for_refresh(sessionmaker, connection.id, connection)
        try:
            return await self._refresh_holding_lease(sessionmaker, current or connection, connector, auth, transport)
        except BaseException:
            await self._release_after_crash(sessionmaker, connection.id)
            raise

    async def _refresh_holding_lease(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        connection: Connection,
        connector: PluginManifest,
        auth: OAuth2Auth,
        transport: httpx.AsyncBaseTransport | None,
    ) -> Connection:
        if connection.status != "active" or not needs_refresh(connection):
            return await self._release(sessionmaker, connection.id, connection)
        client = client_for(self.settings, auth.provider)
        refresh_token = self.vault.refresh_token(connection)
        if refresh_token is None:
            return await self._needs_reconnect(sessionmaker, connection, connector, "no refresh token")
        if client is None:
            logger.warning("Can't refresh a %s token: the server has no %s client.", connector.id, auth.provider)
            return await self._release(sessionmaker, connection.id, connection)
        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token.get_secret_value(),
            "client_id": client.client_id,
            "client_secret": client.client_secret.get_secret_value(),
        }
        try:
            async with asyncio.timeout(TOKEN_CALL_BUDGET.total_seconds()):
                tokens = await self._token_call(auth, form, transport=transport)
        except _TokenRefused as refused:
            if refused.error == "invalid_grant":
                return await self._needs_reconnect(sessionmaker, connection, connector, "invalid_grant")
            logger.warning("Refreshing a %s token failed (%s).", connector.id, _describe(refused))
            return await self._back_off(sessionmaker, connection)
        except (httpx.HTTPError, AppError, ValueError, TimeoutError) as failed:
            logger.warning("Refreshing a %s token failed (%s).", connector.id, _describe(failed))
            return await self._back_off(sessionmaker, connection)
        return await self._save_refreshed(sessionmaker, connection, tokens)

    async def _save_refreshed(
        self, sessionmaker: async_sessionmaker[AsyncSession], connection: Connection, tokens: _Tokens
    ) -> Connection:
        """Save the new token only if the row is still the active one it was refreshed from, in
        one guarded UPDATE: a disconnect (or a reconnect) that committed meanwhile wins, and the
        token is thrown away. No lock is held, so this is the same on Postgres and SQLite."""
        draft = Connection(encrypted_secret=connection.encrypted_secret)  # never added to a session
        self._save_tokens(draft, tokens)
        async with sessionmaker() as db:
            saved = cast(
                CursorResult[Any],
                await db.execute(
                    update(Connection)
                    .where(
                        Connection.id == connection.id,
                        Connection.status == "active",
                        Connection.encrypted_secret == connection.encrypted_secret,
                    )
                    .values(
                        encrypted_secret=draft.encrypted_secret,
                        access_expires_at=draft.access_expires_at,
                        last_refreshed_at=draft.last_refreshed_at,
                        refresh_lease_until=None,
                    )
                ),
            )
            await db.commit()
            row = await db.get(Connection, connection.id, populate_existing=True)
        if saved.rowcount != 1:
            logger.info("A new %s token was thrown away: the connection changed meanwhile.", connection.connector_id)
        return row or connection

    async def _wait_for_refresh(
        self, sessionmaker: async_sessionmaker[AsyncSession], connection_id: uuid.UUID, fallback: Connection
    ) -> Connection:
        """Re-read the row until the winner is done. A lease with at most `BACKOFF` left is a
        backoff after a failed refresh (a call in flight always has more: `TOKEN_CALL_BUDGET`):
        go on with the token there is."""
        deadline = utcnow() + LEASE
        latest = fallback
        while True:
            async with sessionmaker() as db:
                row = await db.get(Connection, connection_id, populate_existing=True)
            if row is None:
                return latest
            latest = row
            lease = row.refresh_lease_until
            now = utcnow()
            if row.status != "active" or not needs_refresh(row) or lease is None or as_utc(lease) <= now + BACKOFF:
                return row
            if now >= deadline:
                return row
            await asyncio.sleep(LEASE_POLL_SECONDS)

    async def _release(
        self, sessionmaker: async_sessionmaker[AsyncSession], connection_id: uuid.UUID, fallback: Connection
    ) -> Connection:
        """Give the lease back: nothing to refresh, or nothing to refresh with."""
        async with sessionmaker() as db:
            await db.execute(update(Connection).where(Connection.id == connection_id).values(refresh_lease_until=None))
            await db.commit()
            row = await db.get(Connection, connection_id, populate_existing=True)
        return row or fallback

    async def _back_off(self, sessionmaker: async_sessionmaker[AsyncSession], connection: Connection) -> Connection:
        """A refresh that may work next time: keep the lease for `BACKOFF` only."""
        async with sessionmaker() as db:
            await db.execute(
                update(Connection).where(Connection.id == connection.id).values(refresh_lease_until=utcnow() + BACKOFF)
            )
            await db.commit()
            row = await db.get(Connection, connection.id, populate_existing=True)
        return row or connection

    async def _release_after_crash(
        self, sessionmaker: async_sessionmaker[AsyncSession], connection_id: uuid.UUID
    ) -> None:
        """The winner raised: free the lease now rather than make everyone wait out `LEASE`."""
        try:
            async with sessionmaker() as db:
                await db.execute(
                    update(Connection).where(Connection.id == connection_id).values(refresh_lease_until=None)
                )
                await db.commit()
        except Exception as failed:  # the original error is the one worth raising
            logger.warning("Couldn't give a refresh lease back (%s).", type(failed).__name__)

    async def _needs_reconnect(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        connection: Connection,
        connector: PluginManifest,
        why: str,
    ) -> Connection:
        """The provider won't renew this sign-in (revoked at the provider, password changed, or a
        Google app left in Testing for 7 days). Someone has to connect it again."""
        reason = (
            f"{connector.name} stopped accepting this sign-in (it was revoked, the password changed, or "
            "the server's Google app is still in Testing). Reconnect it in Connect apps."
        )
        async with sessionmaker() as db:
            await db.execute(
                update(Connection)
                .where(Connection.id == connection.id, Connection.status == "active")
                .values(status="needs_reconnect", status_reason=reason, refresh_lease_until=None)
            )
            connection_service.audit_line(
                db,
                connection.org_id,
                None,
                "connection.needs_reconnect",
                connection.id,
                {"connector": connector.id, "reason": why},
            )
            await db.commit()
            row = await db.get(Connection, connection.id, populate_existing=True)
        logger.warning("A %s connection needs reconnecting (%s).", connector.id, why)
        return row or connection

    # Revoke

    async def revoke(self, connector: PluginManifest | None, token: SecretStr | None) -> bool:
        """Tell the provider to forget a token (best effort, after the disconnect is committed).
        True when it said yes."""
        auth = connector.auth if connector is not None else None
        if token is None or not isinstance(auth, OAuth2Auth) or not auth.revoke_url:
            return False
        try:
            async with self._client() as client:
                response = await client.post(
                    self._endpoint(auth, auth.revoke_url), data={"token": token.get_secret_value()}
                )
        except (httpx.HTTPError, AppError) as failed:  # AppError: the SSRF guard (`UnsafeUrl`)
            logger.warning("Revoking a %s token failed (%s).", auth.provider, _describe(failed))
            return False
        if response.status_code != 200:
            logger.warning("Revoking a %s token: the provider answered %s.", auth.provider, response.status_code)
        return response.status_code == 200

    # HTTP

    async def _token_call(
        self, auth: OAuth2Auth, form: dict[str, str], *, transport: httpx.AsyncBaseTransport | None = None
    ) -> _Tokens:
        """POST the token endpoint (a form, as RFC 6749 says). Raises `_TokenRefused`,
        `httpx.HTTPError` or `ValueError` (an answer that isn't a token)."""
        async with self._client(transport) as client:
            response = await client.post(
                self._endpoint(auth, auth.token_url), data=form, headers={"Accept": "application/json"}
            )
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code != 200:
            error = body.get("error") if isinstance(body, dict) else None
            safe = error if isinstance(error, str) and _ERROR_CODE.match(error) else ""
            raise _TokenRefused(response.status_code, safe)
        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str) or not body["access_token"]:
            raise ValueError("the answer has no access token")
        refresh, expires, scope = body.get("refresh_token"), body.get("expires_in"), body.get("scope")
        return _Tokens(
            access_token=body["access_token"],
            refresh_token=refresh if isinstance(refresh, str) and refresh else None,
            token_type=str(body.get("token_type") or "Bearer"),
            expires_in=_lifetime(expires),
            scope=scope if isinstance(scope, str) and scope.strip() else None,
        )

    def _client(self, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
        inner = transport or self.transport or GuardedTransport(allow_private=bool(self._fake_base()))
        gmail = self._test_setting(self.settings.gmail_api_base_url)
        return httpx.AsyncClient(
            transport=_Rebase(inner, {GMAIL_API_HOST: gmail}) if gmail else inner,
            follow_redirects=False,
            trust_env=False,
            timeout=HTTP_TIMEOUT,
        )

    def _test_setting(self, value: str) -> str:
        """A fake server's address: honoured only when ENVIRONMENT=test."""
        return value.strip().rstrip("/") if self.settings.environment == "test" else ""

    def _fake_base(self) -> str:
        return self._test_setting(self.settings.google_oauth_base_url) or self._test_setting(
            self.settings.gmail_api_base_url
        )

    def _endpoint(self, auth: OAuth2Auth, url: str) -> str:
        base = self._test_setting(self.settings.google_oauth_base_url) if auth.provider == GOOGLE else ""
        return base + urlsplit(url).path if base else url

    def _issuer(self, auth: OAuth2Auth) -> str | None:
        """The `iss` this provider's callback must carry, or None for one that sends none."""
        issuer = ISSUERS.get(auth.provider)
        if issuer is None:
            return None
        fake = self._test_setting(self.settings.google_oauth_base_url) if auth.provider == GOOGLE else ""
        return fake or issuer


def _lifetime(expires: object) -> int:
    """`expires_in` in seconds: 3599, 3599.0 and "3599" all count. Missing, unreadable or not
    positive: `DEFAULT_TOKEN_LIFETIME`, so the token is still refreshed in time."""
    if isinstance(expires, bool) or not isinstance(expires, (int, float, str)):
        return DEFAULT_TOKEN_LIFETIME
    try:
        seconds = int(float(expires))
    except (ValueError, OverflowError):
        return DEFAULT_TOKEN_LIFETIME
    return min(seconds, MAX_TOKEN_LIFETIME) if seconds > 0 else DEFAULT_TOKEN_LIFETIME


def _describe(error: Exception) -> str:
    """An exception for the log: its type, and its message only for our own refusals (which
    carry an OAuth error code at most). httpx and provider messages can quote anything."""
    if isinstance(error, _TokenRefused):
        return f"status {error}"
    return type(error).__name__

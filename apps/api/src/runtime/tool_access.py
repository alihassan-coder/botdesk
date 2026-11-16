"""What a tool call may reach: its `ctx.http` and `ctx.connection` (ADR 0010 §7-§8).

    connection_id = toolset.connection_ids.get(tool.plugin_id)  # the run's toolset
    async with tool_access.open(run, tool, call_id, connection_id=connection_id, timeout_seconds=30) as access:
        ctx = ToolContext(..., http=access.http, connection=access.connection)

- A plugin with no `egress` gets an `http` that refuses every request.
- A plugin with `egress` but no `auth` gets an `AuthorisedHttp` with no credential.
- A plugin with `auth` gets the connection the run's toolset chose for it (`connection_id`, from
  the bot's binding; `runtime.toolset` already checked the run may use it) and an
  `AuthorisedHttp` that adds its credential. No connection, or one that is no longer active: an
  `http` that refuses with "connect it first" (or "needs reconnecting"), so the tool fails with
  that and the run goes on.

An OAuth connection whose token has under a minute left is refreshed first (`oauth_flow.refresh`).
The credential is decrypted only when the tool makes its first request. After the call, the
connection's `last_used_at` is saved (the call's record already names the connection).
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from botdesk_plugin_sdk import ConnectionInfo, HttpClient, NoHttp, OAuth2Auth, PluginManifest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import utcnow
from src.models import Connection
from src.plugins.authorised_http import DEFAULT_MAX_BYTES, AuthorisedHttp, guarded_client
from src.plugins.registry import RegisteredTool, ToolRegistry
from src.services import connection_service
from src.services.credential_vault import CredentialVault
from src.services.oauth_flow import OAuth
from src.services.tool_execution_service import RunRef


@dataclass(frozen=True)
class ToolAccess:
    http: HttpClient
    connection: ConnectionInfo | None = None


NO_ACCESS = ToolAccess(http=NoHttp())


class ToolAccessProvider:
    """One per run manager. `transport` replaces the network (tests); the default connects
    through the SSRF guard with private addresses refused."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        registry: ToolRegistry,
        vault: CredentialVault,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_response_bytes: int = DEFAULT_MAX_BYTES,
        oauth: OAuth | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.registry = registry
        self.vault = vault
        self.transport = transport
        self.oauth = oauth
        self.max_response_bytes = max_response_bytes

    @asynccontextmanager
    async def open(
        self,
        run: RunRef,
        tool: RegisteredTool,
        tool_call_id: str,
        *,
        connection_id: uuid.UUID | None,
        timeout_seconds: float,
    ) -> AsyncIterator[ToolAccess]:
        """`connection_id`: the connection the run's toolset gives this tool's plugin (None: the
        binding has no account)."""
        plugin = self.registry.plugin(tool.plugin_id)
        if plugin is None or not plugin.egress:
            yield NO_ACCESS
            return
        connection = None
        if plugin.auth is not None:
            if connection_id is not None:
                async with self.sessionmaker() as db:
                    connection = await connection_service.for_tool_call(db, run.org_id, connection_id)
            if connection is not None and isinstance(plugin.auth, OAuth2Auth) and self.oauth is not None:
                # A token with under a minute left is refreshed first (one refresh per connection
                # at a time; `invalid_grant` comes back as needs_reconnect).
                connection = await self.oauth.refresh(self.sessionmaker, connection, plugin, transport=self.transport)
            if connection is None or connection.status != "active":
                yield ToolAccess(http=NoHttp(_unavailable(plugin, connection)))
                return

        async with guarded_client(timeout_seconds, self.transport) as client:
            # Bound now, while `connection` is the row read above: decrypted on first use only.
            opener = (lambda row=connection: self.vault.open(row)) if connection is not None else None
            http = AuthorisedHttp(
                client=client, egress=plugin.egress, credential=opener, max_bytes=self.max_response_bytes
            )
            try:
                yield ToolAccess(http=http, connection=_info(connection) if connection else None)
            finally:
                if connection is not None and http.used:
                    await self._record_use(connection.id)

    async def _record_use(self, connection_id: uuid.UUID) -> None:
        async with self.sessionmaker() as db:
            await connection_service.record_use(db, connection_id, when=utcnow())
            await db.commit()


def _info(connection: Connection) -> ConnectionInfo:
    return ConnectionInfo(
        id=connection.id,
        connector_id=connection.connector_id,
        account_label=connection.account_label,
        owner_kind=connection.owner_kind,  # type: ignore[arg-type]  # only valid kinds are saved
        scopes=tuple(connection.scopes or ()),
    )


def _unavailable(plugin: PluginManifest, connection: Connection | None) -> str:
    if connection is not None and connection.status == "needs_reconnect":
        return f"{connection.account_label} needs reconnecting (Connect apps)."
    return (
        f"{plugin.name} isn't connected for this bot. Connect it in Connect apps and choose the "
        "account in the bot's Tools, then try again."
    )

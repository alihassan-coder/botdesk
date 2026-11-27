"""A run's toolset: the tools this run of a bot may use, and the connection each plugin's calls
go through (slice 5.2, ADR 0010 §3).

    toolset = await toolset.load(db, registry, run_id)   # two queries
    toolset.get("demo__send_email")                       # None when not bound for this run
    toolset.tools()                                       # what the model is offered
    toolset.connection_ids                                # {plugin_id: connection id}

`resolve` is the rule, a pure function over rows. For each enabled binding of the bot whose
plugin is loaded:

- no connection: keep the plugin. Its tools that need an account fail with "connect it first".
- a connection that isn't usable in this run: drop the whole plugin.
- a usable connection: keep the tools whose `scopes` were all granted to it (a granted scope also
  gives the ones the plugin's `OAuth2Auth.implied_scopes` say it implies).

A connection is usable when it is active and its owner fits the run:

- member-owned: the member is the run's requester, and the run is in that member's own DM with
  this bot (never a group, never someone else's DM, never as a guest in another bot's DM);
- bot-owned: owned by this run's bot;
- org-owned: always.

A bot works either in its browser or on its cloud computer (`Bot.computer`, ADR 0020 §2): a
"cloud" bot isn't offered the Browser plugin, and only a "cloud" bot is offered the Computer one.

The graph resolves the toolset again in every node that uses it, so a tool unbound mid-run is
refused when the run resumes.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from botdesk_plugin_sdk import Auth, OAuth2Auth
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Connection
from src.plugins.registry import RegisteredTool, ToolRegistry
from src.services import binding_service, mcp_server_service
from src.services.mcp_server_service import McpRuntime, is_mcp_plugin


@dataclass(frozen=True)
class RunScope:
    """Who and where a run is: what decides whether a connection may serve it."""

    bot_id: uuid.UUID
    requester_id: uuid.UUID | None
    thread_kind: str  # "dm" | "group"
    thread_created_by: uuid.UUID | None
    thread_bot_id: uuid.UUID | None  # a DM's own bot
    computer: str = "browser"  # the bot's: browser | cloud (ADR 0020 §2)


@dataclass(frozen=True)
class ConnectionRow:
    """A connection as the resolver needs it. Never a secret."""

    id: uuid.UUID
    connector_id: str
    account_label: str
    owner_kind: str  # member | bot | org
    owner_user_id: uuid.UUID | None
    owner_bot_id: uuid.UUID | None
    status: str
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BindingRow:
    """One of the bot's bindings, with its connection (None: no account chosen)."""

    plugin_id: str
    enabled: bool
    connection: ConnectionRow | None


def usable(connection: ConnectionRow, scope: RunScope) -> bool:
    """May this run use this connection? (ADR 0010 §3, the contract's "usable-connection rule")."""
    if connection.status != "active":
        return False
    if connection.owner_kind == "member":
        owner = connection.owner_user_id
        return (
            owner is not None
            and scope.requester_id == owner
            and scope.thread_kind == "dm"
            and scope.thread_created_by == owner
            and scope.thread_bot_id == scope.bot_id
        )
    if connection.owner_kind == "bot":
        return connection.owner_bot_id == scope.bot_id
    return connection.owner_kind == "org"


@dataclass(frozen=True)
class Toolset:
    """What `resolve` decided. Looks tools up like the registry does (`get`), so the tool
    pipeline takes either."""

    _tools: Mapping[str, RegisteredTool] = field(default_factory=dict)
    _registry: ToolRegistry | None = None
    connections: Mapping[str, ConnectionRow] = field(default_factory=dict)  # by plugin id

    def get(self, name: str) -> RegisteredTool | None:
        """By full name (`demo.create_note`) or the model's name (`demo__create_note`)."""
        tool = self._registry.get(name) if self._registry else None
        return tool if tool is not None and tool.name in self._tools else None

    def tools(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    @property
    def connection_ids(self) -> dict[str, uuid.UUID]:
        return {plugin_id: connection.id for plugin_id, connection in self.connections.items()}


def resolve(registry: ToolRegistry, bindings: Iterable[BindingRow], scope: RunScope) -> Toolset:
    """The toolset for a run in `scope` of a bot with these bindings."""
    tools: dict[str, RegisteredTool] = {}
    connections: dict[str, ConnectionRow] = {}
    for binding in bindings:
        plugin = registry.plugin(binding.plugin_id)
        if plugin is None or not binding.enabled or not _fits_computer(plugin.id, scope.computer):
            continue
        connection = binding.connection
        if connection is not None:
            if connection.connector_id != plugin.id or not usable(connection, scope):
                continue
            connections[plugin.id] = connection
        granted = _effective_scopes(plugin.auth, connection.scopes) if connection is not None else None
        for spec in plugin.tools:
            if granted is not None and not granted.issuperset(spec.scopes):
                continue
            tool = registry.get(f"{plugin.id}.{spec.name}")
            if tool is not None:
                tools[tool.name] = tool
    return Toolset(_tools=tools, _registry=registry, connections=connections)


_fits_computer = binding_service.fits_computer  # the browser or the cloud computer, by the bot's mode


def _effective_scopes(auth: Auth | None, granted: Iterable[str]) -> frozenset[str]:
    return auth.effective_scopes(granted) if isinstance(auth, OAuth2Auth) else frozenset(granted)


async def load(db: AsyncSession, registry: ToolRegistry, run_id: uuid.UUID, mcp: McpRuntime | None = None) -> Toolset:
    """The run's toolset, read from the database now (two queries; a third when the bot has an
    MCP server bound, to add the organization's servers as plugins). A run that's gone has none."""
    rows = await binding_service.run_bindings(db, run_id)
    if rows is None:
        return Toolset(_registry=registry)
    run, thread, bindings, computer = rows
    if any(is_mcp_plugin(binding.plugin_id) for binding, _ in bindings):
        registry = await mcp_server_service.org_registry(db, registry, run.org_id, mcp)
    scope = RunScope(
        bot_id=run.bot_id,
        requester_id=run.requester_id,
        thread_kind=thread.kind,
        thread_created_by=thread.created_by,
        thread_bot_id=thread.bot_id,
        computer=computer,
    )
    return resolve(
        registry,
        (
            BindingRow(
                plugin_id=binding.plugin_id,
                enabled=binding.enabled,
                connection=_row(connection) if connection is not None else None,
            )
            for binding, connection in bindings
        ),
        scope,
    )


def _row(connection: Connection) -> ConnectionRow:
    return ConnectionRow(
        id=connection.id,
        connector_id=connection.connector_id,
        account_label=connection.account_label,
        owner_kind=connection.owner_kind,
        owner_user_id=connection.owner_user_id,
        owner_bot_id=connection.owner_bot_id,
        status=connection.status,
        scopes=tuple(connection.scopes or ()),
    )

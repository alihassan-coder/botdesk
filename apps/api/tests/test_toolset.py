"""The toolset resolver (slice 5.2): which tools a run of a bot may use, and through which
connection, from the bot's bindings, their connections and the run. A pure function over rows,
tested against the contract's case table (docs/architecture/connections-api-contract.md)."""

import uuid
from dataclasses import replace

import pytest
from botdesk_plugin_sdk import ApiKeyAuth, NoArgs, OAuth2Auth, PluginManifest, ToolContext, ToolSpec

from src.plugins.registry import ToolRegistry
from src.runtime.toolset import BindingRow, ConnectionRow, RunScope, resolve

ALI, SARA = uuid.uuid4(), uuid.uuid4()
SCOUT, INBOX = uuid.uuid4(), uuid.uuid4()


async def _handler(_args: NoArgs, _ctx: ToolContext) -> dict[str, str]:
    return {}


def _tool(name: str, *, scopes: tuple[str, ...] = ()) -> ToolSpec:
    return ToolSpec(
        name=name, title=name, description=name, args_model=NoArgs, risk="read", handler=_handler, scopes=scopes
    )


MAIL = PluginManifest(
    id="mail",
    name="Mail",
    version="1",
    description="Mail",
    tools=(_tool("search", scopes=("mail.read",)), _tool("send", scopes=("mail.send",)), _tool("labels")),
    auth=OAuth2Auth(
        provider="google",
        authorize_url="https://auth.example/authorize",
        token_url="https://auth.example/token",
        scope_sets={"read": ("mail.read",), "full": ("mail.read", "mail.send")},
    ),
    egress=("mail.example",),
)
NOTES = PluginManifest(id="notes", name="Notes", version="1", description="Notes", tools=(_tool("create"),))
KEYED = PluginManifest(
    id="keyed",
    name="Keyed",
    version="1",
    description="Keyed",
    tools=(_tool("call"),),
    auth=ApiKeyAuth(),
    egress=("keyed.example",),
)


@pytest.fixture
def registry() -> ToolRegistry:
    registry = ToolRegistry()
    for plugin in (MAIL, NOTES, KEYED):
        registry.register(plugin)
    return registry


def _connection(owner_kind: str = "org", **changes: object) -> ConnectionRow:
    row = ConnectionRow(
        id=uuid.uuid4(),
        connector_id="mail",
        account_label="ali@acme.dev",
        owner_kind=owner_kind,
        owner_user_id=ALI if owner_kind == "member" else None,
        owner_bot_id=SCOUT if owner_kind == "bot" else None,
        status="active",
        scopes=("mail.read", "mail.send"),
    )
    return replace(row, **changes)  # type: ignore[arg-type]


ALIS_DM = RunScope(bot_id=SCOUT, requester_id=ALI, thread_kind="dm", thread_created_by=ALI, thread_bot_id=SCOUT)


def _names(registry: ToolRegistry, bindings: list[BindingRow], scope: RunScope = ALIS_DM) -> set[str]:
    return {tool.name for tool in resolve(registry, bindings, scope).tools()}


def _mail(connection: ConnectionRow | None, *, enabled: bool = True) -> list[BindingRow]:
    return [BindingRow(plugin_id="mail", enabled=enabled, connection=connection)]


ALL_MAIL = {"mail.search", "mail.send", "mail.labels"}


def test_a_member_connection_works_in_its_owners_own_dm(registry: ToolRegistry) -> None:
    connection = _connection("member")
    toolset = resolve(registry, _mail(connection), ALIS_DM)
    assert {tool.name for tool in toolset.tools()} == ALL_MAIL
    assert toolset.connection_ids == {"mail": connection.id}
    assert toolset.connections["mail"] == connection


def test_a_member_connection_is_not_used_in_someone_elses_dm(registry: ToolRegistry) -> None:
    saras_dm = RunScope(bot_id=SCOUT, requester_id=SARA, thread_kind="dm", thread_created_by=SARA, thread_bot_id=SCOUT)
    assert _names(registry, _mail(_connection("member")), saras_dm) == set()


def test_a_member_connection_needs_the_owner_to_be_the_requester_too(registry: ToolRegistry) -> None:
    # Ali's DM with Scout, but Sara's message started the chain (say, a routine she set up).
    asked_by_sara = replace(ALIS_DM, requester_id=SARA)
    assert _names(registry, _mail(_connection("member")), asked_by_sara) == set()
    no_requester = replace(ALIS_DM, requester_id=None)
    assert _names(registry, _mail(_connection("member")), no_requester) == set()


def test_a_member_connection_is_not_used_in_a_guests_run_in_the_owners_dm(registry: ToolRegistry) -> None:
    # Ali's DM is with another bot; Scout was @mentioned into it as a guest.
    guest = replace(ALIS_DM, thread_bot_id=INBOX)
    assert _names(registry, _mail(_connection("member")), guest) == set()


def test_a_member_connection_is_not_used_in_a_group(registry: ToolRegistry) -> None:
    group = RunScope(bot_id=SCOUT, requester_id=ALI, thread_kind="group", thread_created_by=ALI, thread_bot_id=None)
    assert _names(registry, _mail(_connection("member")), group) == set()


def test_a_bots_own_connection_works_in_every_chat_of_that_bot_only(registry: ToolRegistry) -> None:
    group = RunScope(bot_id=SCOUT, requester_id=SARA, thread_kind="group", thread_created_by=SARA, thread_bot_id=None)
    assert _names(registry, _mail(_connection("bot")), group) == ALL_MAIL
    inboxs = _connection("bot", owner_bot_id=INBOX)
    assert _names(registry, _mail(inboxs)) == set()


def test_an_org_connection_works_everywhere(registry: ToolRegistry) -> None:
    group = RunScope(bot_id=SCOUT, requester_id=None, thread_kind="group", thread_created_by=SARA, thread_bot_id=None)
    assert _names(registry, _mail(_connection("org")), group) == ALL_MAIL


@pytest.mark.parametrize("status", ["needs_reconnect", "revoked"])
def test_a_connection_that_isnt_active_drops_the_whole_plugin(registry: ToolRegistry, status: str) -> None:
    toolset = resolve(registry, _mail(_connection("org", status=status)), ALIS_DM)
    assert toolset.tools() == [] and toolset.connection_ids == {}


def test_a_plugin_switched_off_has_no_tools(registry: ToolRegistry) -> None:
    assert _names(registry, _mail(_connection("org"), enabled=False)) == set()


def test_a_tool_whose_scopes_werent_granted_is_dropped(registry: ToolRegistry) -> None:
    read_only = _connection("org", scopes=("mail.read",))
    assert _names(registry, _mail(read_only)) == {"mail.search", "mail.labels"}


def test_a_scope_the_plugin_says_a_granted_one_implies_counts_as_granted() -> None:
    # Like Google's gmail.modify, which includes gmail.readonly.
    auth = replace(MAIL.auth, implied_scopes={"mail.send": ("mail.read",)})  # type: ignore[type-var]
    registry = ToolRegistry()
    registry.register(replace(MAIL, auth=auth))
    send_only = _connection("org", scopes=("mail.send",))
    assert _names(registry, _mail(send_only)) == ALL_MAIL
    assert _names(registry, _mail(_connection("org", scopes=("openid",)))) == {"mail.labels"}


def test_a_binding_without_a_connection_keeps_its_tools_they_fail_with_connect_it_first(
    registry: ToolRegistry,
) -> None:
    toolset = resolve(registry, _mail(None), ALIS_DM)
    assert {tool.name for tool in toolset.tools()} == ALL_MAIL
    assert toolset.connection_ids == {}


def test_only_bound_plugins_count_and_unknown_ones_are_ignored(registry: ToolRegistry) -> None:
    bindings = [
        BindingRow(plugin_id="notes", enabled=True, connection=None),
        BindingRow(plugin_id="gone", enabled=True, connection=None),  # no longer in PLUGINS
    ]
    assert _names(registry, bindings) == {"notes.create"}


def test_a_connection_for_another_connector_is_never_used(registry: ToolRegistry) -> None:
    bindings = [BindingRow(plugin_id="keyed", enabled=True, connection=_connection("org"))]  # a "mail" account
    assert _names(registry, bindings) == set()


def test_the_toolset_finds_tools_by_full_or_model_name(registry: ToolRegistry) -> None:
    toolset = resolve(registry, [BindingRow(plugin_id="notes", enabled=True, connection=None)], ALIS_DM)
    assert toolset.get("notes.create") is registry.get("notes.create")
    assert toolset.get("notes__create") is registry.get("notes.create")
    assert toolset.get("mail.search") is None  # not bound

"""Loading plugins through entry points, only from the allowlist, and the plugins endpoint.

Fake entry points point at the functions below, so each kind of broken plugin is one function.
"""

import logging
from importlib.metadata import EntryPoint
from typing import Any

import httpx
import pytest
from botdesk_plugin_sdk import ENTRY_POINT_GROUP, NoArgs, PluginManifest, ToolContext, ToolResult, ToolSpec

from src.plugins import loader
from src.plugins.registry import build_registry
from tests.conftest import sign_up


async def _ok(_args: NoArgs, _ctx: ToolContext) -> ToolResult:
    return {"ok": True}


def _manifest(plugin_id: str, **tool: Any) -> PluginManifest:
    spec: dict[str, Any] = {
        "name": "ping",
        "title": "Ping",
        "description": "Answer pong.",
        "args_model": NoArgs,
        "risk": "read",
        "handler": _ok,
    }
    return PluginManifest(
        id=plugin_id, name=plugin_id.title(), version="1.0.0", description="test", tools=(ToolSpec(**spec | tool),)
    )


def good() -> PluginManifest:
    return _manifest("good")


def raises() -> PluginManifest:
    raise RuntimeError("no API key configured")


def sync_handler() -> PluginManifest:
    def blocking(_args: NoArgs, _ctx: ToolContext) -> ToolResult:
        return {}

    return _manifest("sync-handler", handler=blocking)


def bad_risk() -> PluginManifest:
    return _manifest("bad-risk", risk="dangerous")


def wrong_id() -> PluginManifest:
    return _manifest("someone-else")


def not_a_manifest() -> dict[str, str]:
    return {"id": "not-a-manifest"}


def exits() -> PluginManifest:
    raise SystemExit(1)


def wrong_types() -> PluginManifest:
    return PluginManifest(id="wrong-types", name=None, version="1", description="", tools=())  # type: ignore[arg-type]


STATIC = _manifest("static")  # an entry point may also name a ready-made manifest


def _entry(name: str, value: str) -> EntryPoint:
    return EntryPoint(name=name, value=value, group=ENTRY_POINT_GROUP)


@pytest.fixture
def fake_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    here = __name__
    entries = [
        _entry("good", f"{here}:good"),
        _entry("static", f"{here}:STATIC"),
        _entry("raises", f"{here}:raises"),
        _entry("sync-handler", f"{here}:sync_handler"),
        _entry("bad-risk", f"{here}:bad_risk"),
        _entry("wrong-id", f"{here}:wrong_id"),
        _entry("not-a-manifest", f"{here}:not_a_manifest"),
        _entry("missing-module", "botdesk_no_such_module:plugin"),
        _entry("exits", f"{here}:exits"),
        _entry("wrong-types", f"{here}:wrong_types"),
        _entry("twice", f"{here}:good"),
        _entry("twice", f"{here}:STATIC"),
    ]

    def fake_entry_points(*, group: str) -> list[EntryPoint]:
        return [entry for entry in entries if entry.group == group]

    monkeypatch.setattr(loader, "entry_points", fake_entry_points)


def test_the_demo_plugin_is_found_through_its_entry_point() -> None:
    assert "demo" in loader.installed_plugins()
    assert [plugin.id for plugin in build_registry(["demo"]).plugins()] == ["demo"]


@pytest.mark.usefixtures("fake_plugins")
def test_only_allowlisted_plugins_are_imported() -> None:
    # `missing-module` is installed but not allowlisted: never imported, so no error.
    registry = build_registry(["good", "static", "good"])
    assert [plugin.id for plugin in registry.plugins()] == ["good", "static"]
    assert registry.get("good__ping") is not None
    assert registry.get("good.ping") is registry.get("good__ping")  # a full name is looked up as it is


@pytest.mark.usefixtures("fake_plugins")
def test_an_empty_allowlist_loads_nothing() -> None:
    assert build_registry([]).plugins() == []


@pytest.mark.usefixtures("fake_plugins")
def test_broken_plugins_are_skipped_with_a_clear_log_line(caplog: pytest.LogCaptureFixture) -> None:
    broken = [
        *["raises", "sync-handler", "bad-risk", "wrong-id", "not-a-manifest", "missing-module", "twice"],
        *["exits", "wrong-types"],
    ]
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        registry = build_registry(["good", *broken])

    assert [plugin.id for plugin in registry.plugins()] == ["good"]
    log = caplog.text
    assert "Plugin 'raises' skipped: loading tests.test_plugins:raises failed: RuntimeError: no API key" in log
    assert "Plugin 'sync-handler' skipped: tool 'ping': handler must be an async function" in log
    assert "Plugin 'bad-risk' skipped: tool 'ping': risk 'dangerous' is not one of" in log
    assert "Plugin 'wrong-id' skipped: its manifest says id 'someone-else'" in log
    assert "Plugin 'not-a-manifest' skipped: expected a PluginManifest, got dict" in log
    assert "Plugin 'missing-module' skipped: loading botdesk_no_such_module:plugin failed: ModuleNotFoundError" in log
    assert "Plugin 'twice' skipped: more than one installed package provides it" in log
    assert "Plugin 'exits' skipped: loading tests.test_plugins:exits failed: SystemExit" in log
    assert "Plugin 'wrong-types' skipped: id, name and version must be strings" in log


@pytest.mark.usefixtures("fake_plugins")
def test_an_allowlisted_plugin_that_is_not_installed_is_a_settings_mistake() -> None:
    with pytest.raises(ValueError, match="PLUGINS names 'gmail', but there is no such plugin"):
        build_registry(["good", "gmail"])


async def test_members_see_the_loaded_plugins_and_their_tools(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    response = await client.get(f"/api/v1/orgs/{me['organizations'][0]['id']}/plugins")
    assert response.status_code == 200
    (demo,) = response.json()
    assert demo["id"] == "demo"
    assert set(demo) == {"id", "name", "version", "description", "tools"}
    send = next(tool for tool in demo["tools"] if tool["name"] == "demo.send_email")
    assert send == {
        "name": "demo.send_email",
        "title": "Send an email",
        "description": "Send an email from the (fake) mailbox. Demo: it is only recorded.",
        "risk": "external-send",
    }


async def test_plugins_are_only_listed_for_members(client: httpx.AsyncClient) -> None:
    ali = await sign_up(client)
    url = f"/api/v1/orgs/{ali['organizations'][0]['id']}/plugins"
    await sign_up(client, name="Sara", email="sara@acme.dev")  # now signed in as Sara
    assert (await client.get(url)).status_code == 404

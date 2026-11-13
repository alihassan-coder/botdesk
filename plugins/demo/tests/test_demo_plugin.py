"""The demo plugin through the SDK's test helpers: no app, no database."""

from importlib.metadata import entry_points

import pytest
from botdesk_plugin_sdk import ENTRY_POINT_GROUP, validate_manifest
from botdesk_plugin_sdk.testing import call_tool, make_context
from pydantic import ValidationError

from botdesk_demo import DemoState, demo_plugin


def test_the_manifest_is_valid() -> None:
    manifest = validate_manifest(demo_plugin())
    assert manifest.id == "demo"
    assert len(manifest.tools) == 6


def test_it_is_registered_under_the_botdesk_entry_point() -> None:
    (entry,) = [ep for ep in entry_points(group=ENTRY_POINT_GROUP) if ep.name == "demo"]
    assert entry.load() is demo_plugin


async def test_notes_are_kept_per_organization() -> None:
    state = DemoState()
    plugin = demo_plugin(state)
    ctx = make_context()
    result = await call_tool(plugin, "create_note", {"title": "Q3 plan"}, ctx)
    assert result["notesInOrganization"] == 1
    await call_tool(plugin, "create_note", {"title": "Other org"})
    assert [n["title"] for n in state.notes[str(ctx.org_id)]] == ["Q3 plan"]


async def test_send_email_only_records_and_keeps_the_idempotency_key() -> None:
    state = DemoState()
    ctx = make_context(tool_call_id="c1")
    result = await call_tool(demo_plugin(state), "send_email", {"to": "sara@acme.dev", "subject": "Hi"}, ctx)
    assert result["sent"] is True
    assert state.sent[0]["key"] == "test:c1"
    with pytest.raises(ValidationError):
        await call_tool(demo_plugin(state), "send_email", {"to": "not an email", "subject": "Hi"})


async def test_search_finds_topics_by_word() -> None:
    result = await call_tool(demo_plugin(), "search_kb", {"query": "refunds policy"})
    assert [hit["topic"] for hit in result["results"]] == ["refunds"]

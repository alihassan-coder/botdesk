"""The SDK on its own: manifests, the load-time checks and the test helpers."""

import dataclasses
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, Field, ValidationError

from botdesk_plugin_sdk import (
    RISK_CLASSES,
    NoArgs,
    PluginError,
    PluginManifest,
    ToolContext,
    ToolResult,
    ToolSpec,
    manifest_problems,
    validate_manifest,
)
from botdesk_plugin_sdk.testing import call_tool, make_context


class GreetArgs(BaseModel):
    name: str = Field(min_length=1, description="Who to greet")


async def greet(args: GreetArgs, ctx: ToolContext) -> ToolResult:
    return {"greeting": f"Hello, {args.name}!", "key": ctx.idempotency_key}


async def ping(_args: NoArgs, _ctx: ToolContext) -> ToolResult:
    return {"pong": True}


def greet_tool(**changes: Any) -> ToolSpec:
    spec = ToolSpec(
        name="greet",
        title="Greet someone",
        description="Say hello to a person by name.",
        args_model=GreetArgs,
        risk="read",
        handler=greet,
        idempotent=True,
    )
    return dataclasses.replace(spec, **changes)


def plugin(*tools: ToolSpec, plugin_id: str = "hello") -> PluginManifest:
    return PluginManifest(
        id=plugin_id, name="Hello", version="0.1.0", description="Greets people.", tools=tools or (greet_tool(),)
    )


def test_the_seven_risk_classes_in_order_of_danger() -> None:
    assert RISK_CLASSES == (
        "read",
        "write-internal",
        "write-external",
        "external-send",
        "spend",
        "destructive",
        "credential",
    )


def test_a_good_manifest_passes_and_turns_into_json() -> None:
    manifest = validate_manifest(plugin(greet_tool(), greet_tool(name="ping", args_model=NoArgs, handler=ping)))
    data = manifest.to_json()
    assert data["manifestVersion"] == 1
    assert data["id"] == "hello"
    first = data["tools"][0]
    assert first["risk"] == "read"
    assert first["idempotent"] is True
    assert first["untrustedOutput"] is False
    assert first["inputSchema"]["required"] == ["name"]


def test_every_problem_is_reported_at_once() -> None:
    def blocking(_args: GreetArgs, _ctx: ToolContext) -> ToolResult:
        return {}

    broken = plugin(
        greet_tool(risk="dangerous"),  # a typo (mypy catches it in a direct ToolSpec call)
        greet_tool(handler=blocking),  # sync: would block the server
        greet_tool(name="Bad Name", args_model=dict),
        plugin_id="Hello_World",
    )
    with pytest.raises(PluginError) as caught:
        validate_manifest(broken)
    problems = caught.value.problems
    assert any("id 'Hello_World'" in p for p in problems)
    assert any("risk 'dangerous' is not one of" in p for p in problems)
    assert any("'greet' is declared twice" in p for p in problems)
    assert any("handler must be an async function" in p for p in problems)
    assert any("args_model must be a Pydantic BaseModel class" in p for p in problems)
    assert any("name must be lowercase" in p for p in problems)


def test_something_that_is_not_a_manifest_is_refused() -> None:
    assert manifest_problems({"id": "x"}) == ["expected a PluginManifest, got dict"]
    with pytest.raises(PluginError, match=r"Plugin '\?' is invalid"):
        validate_manifest(None)


def test_a_plugin_without_tools_is_refused() -> None:
    empty = PluginManifest(id="empty", name="Empty", version="1", description="")
    assert manifest_problems(empty) == ["it has no tools"]


async def test_call_tool_validates_arguments_then_runs_the_handler() -> None:
    result = await call_tool(plugin(), "greet", {"name": "Sara"}, make_context(tool_call_id="c1"))
    assert result == {"greeting": "Hello, Sara!", "key": "test:c1"}
    with pytest.raises(ValidationError):
        await call_tool(plugin(), "greet", {"name": ""})
    with pytest.raises(KeyError, match="no tool called 'wave'"):
        await call_tool(plugin(), "wave", {})


def test_make_context_takes_fixed_ids() -> None:
    org = uuid.uuid4()
    ctx = make_context(org_id=org)
    assert ctx.org_id == org
    assert ctx.idempotency_key.startswith("test:")


def test_the_summary_falls_back_to_the_title() -> None:
    args = GreetArgs(name="Sara")
    assert greet_tool().summary(args) == "Greet someone"
    assert greet_tool(summarize=lambda a: f"Greet {a.name}").summary(args) == "Greet Sara"

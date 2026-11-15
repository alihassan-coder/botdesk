"""Manifest version 2 (ADR 0010 §7): accounts (auth), the hosts a plugin may call (egress),
per-tool scopes, settings models, triggers, and `ctx.http`. All additive: a version-1 manifest
(none of these fields) still validates and runs."""

import dataclasses
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, Field

from botdesk_plugin_sdk import (
    MANIFEST_VERSION,
    ApiKeyAuth,
    ConnectionInfo,
    HostNotAllowed,
    HttpResponse,
    NoArgs,
    NotConnected,
    OAuth2Auth,
    PluginManifest,
    ToolContext,
    ToolResult,
    ToolSpec,
    TriggerPollResult,
    TriggerSpec,
    manifest_problems,
    validate_manifest,
)
from botdesk_plugin_sdk.testing import FakeHttp, call_tool, make_context


async def whoami(_args: NoArgs, ctx: ToolContext) -> ToolResult:
    response = await ctx.http.request("GET", "https://api.example.com/v1/me", params={"full": "1"})
    return {"status": response.status_code, "name": response.json()["name"]}


async def poll_new(_ctx: ToolContext, cursor: str | None) -> TriggerPollResult:
    return TriggerPollResult(events=(), cursor=cursor)


class OrgSettings(BaseModel):
    workspace: str = Field(default="", description="Which workspace to use")


class BotSettings(BaseModel):
    label: str = "INBOX"


def whoami_tool(**changes: Any) -> ToolSpec:
    spec = ToolSpec(
        name="whoami",
        title="Who am I",
        description="The connected account's name.",
        args_model=NoArgs,
        risk="read",
        handler=whoami,
        idempotent=True,
    )
    return dataclasses.replace(spec, **changes)


def v1_plugin() -> PluginManifest:
    return PluginManifest(id="hello", name="Hello", version="1", description="v1", tools=(whoami_tool(),))


def api_key_plugin(**changes: Any) -> PluginManifest:
    manifest = PluginManifest(
        id="acme",
        name="Acme",
        version="1",
        description="An API-key app.",
        tools=(whoami_tool(),),
        auth=ApiKeyAuth(header="X-Api-Key"),
        egress=("api.example.com",),
    )
    return dataclasses.replace(manifest, **changes)


GOOGLE = OAuth2Auth(
    provider="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",  # noqa: S106 - a URL, not a password
    revoke_url="https://oauth2.googleapis.com/revoke",
    scope_sets={"read": ("gmail.readonly",), "full": ("gmail.modify",)},
    extra_authorize_params={"access_type": "offline"},
)


def oauth_plugin(**changes: Any) -> PluginManifest:
    manifest = PluginManifest(
        id="mail",
        name="Mail",
        version="1",
        description="An OAuth app.",
        tools=(whoami_tool(scopes=("gmail.readonly",)),),
        auth=GOOGLE,
        egress=("gmail.googleapis.com",),
        settings_model=OrgSettings,
        bot_settings_model=BotSettings,
        triggers=(TriggerSpec(name="new_email", title="New email", description="Mail arrived.", poll=poll_new),),
    )
    return dataclasses.replace(manifest, **changes)


def test_the_manifest_version_is_2() -> None:
    assert MANIFEST_VERSION == 2


def test_a_version_1_manifest_still_validates_and_its_json_has_empty_v2_fields() -> None:
    data = validate_manifest(v1_plugin()).to_json()
    assert data["manifestVersion"] == 2
    assert data["auth"] is None
    assert data["egress"] == []
    assert data["triggers"] == []
    assert data["settingsSchema"] is None
    assert data["botSettingsSchema"] is None
    assert data["tools"][0]["scopes"] == []


def test_a_version_2_manifest_shows_auth_egress_scopes_triggers_and_settings() -> None:
    data = validate_manifest(oauth_plugin()).to_json()
    assert data["auth"] == {
        "type": "oauth2",
        "provider": "google",
        "authorizeUrl": "https://accounts.google.com/o/oauth2/v2/auth",
        "tokenUrl": "https://oauth2.googleapis.com/token",
        "revokeUrl": "https://oauth2.googleapis.com/revoke",
        "scopeSets": {"full": ["gmail.modify"], "read": ["gmail.readonly"]},
        "extraAuthorizeParams": {"access_type": "offline"},
    }
    assert data["egress"] == ["gmail.googleapis.com"]
    assert data["tools"][0]["scopes"] == ["gmail.readonly"]
    assert data["triggers"] == [
        {
            "name": "new_email",
            "title": "New email",
            "description": "Mail arrived.",
            "intervalSeconds": 300,
            "untrustedPayload": True,
        }
    ]
    assert data["settingsSchema"]["properties"]["workspace"]["description"] == "Which workspace to use"
    assert data["botSettingsSchema"]["title"] == "BotSettings"
    api_key = validate_manifest(api_key_plugin()).to_json()["auth"]
    assert api_key == {"type": "api_key", "header": "X-Api-Key", "prefix": ""}


def test_an_account_plugin_must_name_the_hosts_it_calls() -> None:
    assert manifest_problems(api_key_plugin(egress=())) == ["a plugin with auth must list the hosts it calls in egress"]


@pytest.mark.parametrize(
    "host", ["https://api.example.com", "api.example.com/v1", "API.example.com", "api.example.com:443", "localhost", ""]
)
def test_egress_hosts_are_plain_lowercase_host_names(host: str) -> None:
    problems = manifest_problems(api_key_plugin(egress=(host,)))
    assert any("egress host" in problem for problem in problems), problems


def test_bad_auth_and_scope_declarations_are_reported() -> None:
    bad_header = manifest_problems(api_key_plugin(auth=ApiKeyAuth(header="X Api\nKey")))
    assert any("header" in p for p in bad_header)
    insecure = dataclasses.replace(GOOGLE, token_url="http://oauth2.googleapis.com/token")  # noqa: S106
    assert any("token_url must start with https://" in p for p in manifest_problems(oauth_plugin(auth=insecure)))
    unknown_scope = oauth_plugin(tools=(whoami_tool(scopes=("drive",)),))
    assert any("scope 'drive' is not in any scope set" in p for p in manifest_problems(unknown_scope))
    scopes_without_oauth = api_key_plugin(tools=(whoami_tool(scopes=("x",)),))
    assert any("scopes need OAuth2Auth" in p for p in manifest_problems(scopes_without_oauth))
    assert any("auth must be ApiKeyAuth" in p for p in manifest_problems(api_key_plugin(auth="key")))


def test_bad_triggers_and_settings_models_are_reported() -> None:
    def blocking(_ctx: ToolContext, cursor: str | None) -> TriggerPollResult:
        return TriggerPollResult(events=(), cursor=cursor)

    trigger = TriggerSpec(name="Bad Name", title="", description="x", poll=blocking, interval_seconds=5)  # type: ignore[arg-type]
    problems = manifest_problems(oauth_plugin(triggers=(trigger,), settings_model=dict))
    assert any("trigger 'Bad Name': name must be lowercase" in p for p in problems)
    assert any("poll must be an async function" in p for p in problems)
    assert any("interval_seconds must be at least 60" in p for p in problems)
    assert any("title and description are required" in p for p in problems)
    assert any("settings_model must be a Pydantic BaseModel class" in p for p in problems)


def test_a_plugin_that_only_connects_an_account_may_have_no_tools_yet() -> None:
    assert manifest_problems(oauth_plugin(tools=(), triggers=())) == []
    assert manifest_problems(v1_plugin().__class__(id="empty", name="E", version="1", description="")) == [
        "it has no tools"
    ]


async def test_without_web_access_ctx_http_refuses_with_a_clear_reason() -> None:
    with pytest.raises(NotConnected, match="no web access"):
        await call_tool(v1_plugin(), "whoami", {})


async def test_fake_http_answers_from_its_routes_and_records_each_request() -> None:
    http = FakeHttp(api_key_plugin())
    http.route("GET", "https://api.example.com/v1/me", json={"name": "Acme Inc"})
    result = await call_tool(api_key_plugin(), "whoami", {}, make_context(http=http))
    assert result == {"status": 200, "name": "Acme Inc"}
    (request,) = http.requests
    assert (request.method, request.url, request.params) == ("GET", "https://api.example.com/v1/me", {"full": "1"})


async def test_fake_http_refuses_hosts_the_manifest_does_not_list_and_plain_http() -> None:
    http = FakeHttp(("api.example.com",))
    with pytest.raises(HostNotAllowed, match=r"evil\.example"):
        await http.request("GET", "https://evil.example/steal")
    with pytest.raises(HostNotAllowed, match="https"):
        await http.request("GET", "http://api.example.com/v1/me")
    with pytest.raises(AssertionError, match=r"no route for POST https://api\.example\.com/x"):
        await http.request("POST", "https://api.example.com/x")


def test_http_response_helpers() -> None:
    response = HttpResponse(status_code=404, headers={"content-type": "text/plain"}, content=b"nope")
    assert not response.ok
    assert response.text == "nope"


def test_a_context_carries_the_connection_without_any_secret() -> None:
    info = ConnectionInfo(
        id=uuid.uuid4(), connector_id="acme", account_label="Acme", owner_kind="org", scopes=("read",)
    )
    ctx = make_context(connection=info)
    assert ctx.connection == info
    assert ctx.settings is None
    assert not any("secret" in name or "token" in name for name in vars(info))

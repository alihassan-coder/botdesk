"""Models & keys without HTTP routes: encryption, the SSRF guard, adapters, the cache, and which
key a run uses."""

import uuid

import httpx
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.core.config import Settings
from src.core.database import utcnow
from src.core.secrets import SecretBox, SecretUnreadable, build_secret_box
from src.core.url_guard import UnsafeUrl, check_base_url
from src.model_providers import ModelInfo, Pricing, ProviderError, adapter_for, scrub
from src.runtime.chat_model import ModelResolver, ModelUnavailable, StandInModel, describe_model_error
from src.services import provider_service
from src.services.model_catalog import ModelCatalog
from src.services.provider_service import Connection
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

# Encryption


def test_keys_round_trip_and_only_the_same_secret_reads_them() -> None:
    box = SecretBox("a long random secret for tests")
    token = box.encrypt("sk-live-123456")
    assert "sk-live-123456" not in token
    assert box.decrypt(token) == "sk-live-123456"
    assert box.encrypt("sk-live-123456") != token  # a fresh IV each time
    with pytest.raises(SecretUnreadable):
        SecretBox("another secret").decrypt(token)
    assert "secret" not in repr(box)


def test_production_refuses_to_start_without_a_secret_key() -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        build_secret_box(Settings(environment="production", _env_file=None))
    development = build_secret_box(Settings(environment="development", _env_file=None))
    assert development.decrypt(build_secret_box(Settings(environment="test", _env_file=None)).encrypt("x")) == "x"


# The SSRF guard


async def test_only_http_and_https_addresses_without_passwords() -> None:
    for url in ("ftp://example.com/v1", "file:///etc/passwd", "localhost:11434", "http://"):
        with pytest.raises(UnsafeUrl, match="http"):
            await check_base_url(url, allow_private=True)
    with pytest.raises(UnsafeUrl, match="user name"):
        await check_base_url("https://me:secret@example.com/v1", allow_private=True)
    assert await check_base_url(" http://localhost:11434/v1/ ", allow_private=True) == "http://localhost:11434/v1"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/v1",
        "http://10.0.0.5/v1",
        "http://192.168.1.20:8000/v1",
        "http://169.254.169.254/latest",  # cloud metadata
        "http://[::1]:8000/v1",
        "http://100.64.0.1/v1",  # carrier-grade NAT
        "http://0.0.0.0/v1",
    ],
)
async def test_private_addresses_are_refused_unless_allowed(url: str) -> None:
    with pytest.raises(UnsafeUrl, match="private network"):
        await check_base_url(url, allow_private=False)
    assert await check_base_url(url, allow_private=True) == url


async def test_host_names_are_checked_by_what_they_resolve_to() -> None:
    async def private(_host: str) -> list[str]:
        return ["93.184.216.34", "10.1.2.3"]  # one private address is enough to refuse

    async def public(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async def missing(_host: str) -> list[str]:
        raise OSError("no such host")

    with pytest.raises(UnsafeUrl, match="private network"):
        await check_base_url("https://sneaky.example/v1", allow_private=False, resolve=private)
    assert await check_base_url("https://models.example/v1", allow_private=False, resolve=public)
    with pytest.raises(UnsafeUrl, match="couldn't find"):
        await check_base_url("https://nowhere.example/v1", allow_private=False, resolve=missing)


def test_production_allows_private_model_urls_only_when_asked() -> None:
    assert Settings(environment="development", _env_file=None).private_model_urls_allowed
    assert not Settings(environment="production", _env_file=None).private_model_urls_allowed
    allowed = Settings(environment="production", allow_private_model_urls=True, _env_file=None)
    assert allowed.private_model_urls_allowed


async def test_a_custom_server_on_a_private_address_is_refused_in_production(providers: FakeProviders) -> None:
    catalog = ModelCatalog(httpx.AsyncClient(transport=httpx.MockTransport(providers.handle)), allow_private_urls=False)
    local = Connection("custom-1", "custom", "Ollama", "", base_url="http://127.0.0.1:11434/v1")
    with pytest.raises(UnsafeUrl):
        await catalog.fetch(local)
    assert providers.requests == []  # never called


# Adapters


async def _list(kind: str, body: object) -> list[ModelInfo]:
    async def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        return await adapter_for(kind).list_models(http, "key", None)  # type: ignore[arg-type]


async def test_openrouter_keeps_names_context_and_prices_per_million_tokens() -> None:
    body = {
        "data": [
            {
                "id": "anthropic/claude-opus-5.5",
                "name": "Anthropic: Claude Opus 5.5",
                "context_length": 1_000_000,
                "pricing": {"prompt": "0.000005", "completion": "0.000025"},
            },
            {"id": "openrouter/auto", "name": "Auto Router", "context_length": 2_000_000, "pricing": {"prompt": "-1"}},
        ]
    }
    claude, auto = await _list("openrouter", body)
    assert claude == ModelInfo("anthropic/claude-opus-5.5", "Anthropic: Claude Opus 5.5", 1_000_000, Pricing(5.0, 25.0))
    assert auto.pricing is None  # "it varies"


async def test_gemini_keeps_chat_models_and_drops_the_models_prefix() -> None:
    body = {
        "data": [
            {"id": "models/gemini-3-pro"},
            {"id": "models/gemini-embedding-001"},
            {"id": "models/imagen-4.0-generate-001"},
            {"id": "models/gemini-2.5-flash-preview-tts"},
        ]
    }
    assert [m.model for m in await _list("gemini", body)] == ["gemini-3-pro"]


async def test_provider_errors_never_carry_the_key() -> None:
    key = "sk-proj-SECRET00000000000000000000"

    async def refuse(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {key}"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as http:
        with pytest.raises(ProviderError) as caught:
            await adapter_for("openai").list_models(http, key, None)
    assert key not in str(caught.value)
    assert str(caught.value) == "401: Incorrect API key provided: [key]"


def test_scrub_removes_key_like_text_and_keeps_messages_short() -> None:
    assert scrub("bad key sk-ant-api03-abc123xyz, skipping") == "bad key [key], skipping"
    assert scrub("AIzaSyD-0123456789abcdef is wrong") == "[key] is wrong"
    assert len(scrub("x " * 500)) == 200


def test_run_errors_say_what_to_do() -> None:
    class AuthError(Exception):
        status_code = 401

    assert "refused the API key" in describe_model_error(AuthError("Incorrect API key provided: sk-abc12345"))
    tools = describe_model_error(Exception("Error code: 400 - model does not support tools"))
    assert tools == "This model can't use tools. Pick another model in the bot's settings."
    other = describe_model_error(Exception("boom with gsk_abcdefghij123"))
    assert other == "The model couldn't reply: boom with [key]"


# The cache


async def test_the_cache_expires_and_follows_key_changes(providers: FakeProviders) -> None:
    providers.answer("api.groq.com", {"data": [{"id": "llama-3.3-70b-versatile"}]})
    now = [1000.0]
    http = httpx.AsyncClient(transport=httpx.MockTransport(providers.handle))
    catalog = ModelCatalog(http, allow_private_urls=False, ttl_seconds=600, clock=lambda: now[0])
    org = uuid.uuid4()
    groq = Connection("groq", "groq", "Groq", "gsk_one")

    await catalog.models(org, groq)
    await catalog.models(org, groq)
    assert providers.calls_to("api.groq.com") == 1
    await catalog.models(uuid.uuid4(), groq)  # another organization has its own entry
    assert providers.calls_to("api.groq.com") == 2
    await catalog.models(org, Connection("groq", "groq", "Groq", "gsk_two"))  # a replaced key
    assert providers.calls_to("api.groq.com") == 3
    now[0] += 601
    await catalog.models(org, Connection("groq", "groq", "Groq", "gsk_two"))
    assert providers.calls_to("api.groq.com") == 4


# Which key a run uses


def _key_of(model: ChatOpenAI) -> str:
    assert isinstance(model.openai_api_key, SecretStr)
    return model.openai_api_key.get_secret_value()


async def test_a_run_uses_the_org_key_then_the_server_key_then_the_stand_in(providers: FakeProviders) -> None:
    settings = TEST_SETTINGS.model_copy(update={"openai_api_key": "sk-from-the-environment"})
    async with api_client(settings, providers) as (app, client):
        me = await sign_up(client)
        org_id = uuid.UUID(me["organizations"][0]["id"])
        resolve = ModelResolver(settings, app.state.sessionmaker, app.state.secrets)

        from_env = await resolve(org_id, "openai:gpt-5.5")
        assert isinstance(from_env, ChatOpenAI)
        assert _key_of(from_env) == "sk-from-the-environment"
        assert isinstance(await resolve(org_id, "anthropic:claude-opus-5-5"), StandInModel)
        assert isinstance(await resolve(org_id, ""), StandInModel)  # DEFAULT_MODEL_ID is Anthropic's

        async with app.state.sessionmaker() as db:
            for kind, key in (("openai", "sk-org-openai-key"), ("anthropic", "sk-ant-org-key")):
                connection = Connection(kind, kind, kind, key)  # type: ignore[arg-type]
                await provider_service.save_credential(
                    db,
                    org_id=org_id,
                    user_id=uuid.UUID(me["user"]["id"]),
                    connection=connection,
                    secrets=app.state.secrets,
                    verified_at=utcnow(),
                )
            await db.commit()

        from_org = await resolve(org_id, "openai:gpt-5.5")
        assert isinstance(from_org, ChatOpenAI)
        assert _key_of(from_org) == "sk-org-openai-key"
        claude = await resolve(org_id, "anthropic:claude-opus-5-5")
        assert isinstance(claude, ChatAnthropic)
        assert claude.anthropic_api_key.get_secret_value() == "sk-ant-org-key"

        # Another organization doesn't get this one's keys.
        assert isinstance(await resolve(uuid.uuid4(), "anthropic:claude-opus-5-5"), StandInModel)

        # A key saved under another SECRET_KEY can't be read: the run fails with a clear message.
        other_box = ModelResolver(settings, app.state.sessionmaker, SecretBox("a different secret"))
        with pytest.raises(ModelUnavailable, match="can't be read"):
            await other_box(org_id, "openai:gpt-5.5")

"""Models & keys over HTTP: saving a key (checked live), who may, model lists, and bots' models.

Every provider call goes to `FakeProviders`; nothing here touches the network.
"""

import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from src.models import ProviderCredential
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

OPENAI_KEY = "sk-proj-TESTKEY0000000000000000abcd"
ANTHROPIC_KEY = "sk-ant-api03-TESTKEY00000000000wxyz"
GROQ_KEY = "gsk_TESTKEY000000000000000000groq"
CUSTOM_KEY = "vllm-TESTKEY-0000000000-cust"

OPENAI_MODELS = {
    "data": [
        {"id": "gpt-5.5", "object": "model"},
        {"id": "o4-mini", "object": "model"},
        {"id": "text-embedding-3-large", "object": "model"},
        {"id": "whisper-1", "object": "model"},
        {"id": "dall-e-3", "object": "model"},
        {"id": "gpt-4o-mini-tts", "object": "model"},
        {"id": "omni-moderation-latest", "object": "model"},
    ]
}
ANTHROPIC_MODELS = {
    "data": [
        {
            "id": "claude-opus-5-5",
            "display_name": "Claude Opus 5.5",
            "max_input_tokens": 1_000_000,
            "lifecycle": "active",
        },
        {"id": "claude-3-haiku-20240307", "display_name": "Claude Haiku 3", "lifecycle": "deprecated"},
    ],
    "has_more": False,
}
GROQ_MODELS = {
    "data": [
        {"id": "llama-3.3-70b-versatile", "context_window": 131072, "active": True},
        {"id": "whisper-large-v3", "context_window": 448, "active": True},
        {"id": "meta-llama/llama-prompt-guard-2-86m", "active": True},
    ]
}


def openai_answer(request: httpx.Request) -> httpx.Response:
    """OpenAI's /models: works with OPENAI_KEY, refuses anything else the way OpenAI does."""
    if request.headers.get("authorization") != f"Bearer {OPENAI_KEY}":
        sent = request.headers.get("authorization", "").removeprefix("Bearer ")
        error = {"message": f"Incorrect API key provided: {sent}.", "type": "invalid_request_error"}
        return httpx.Response(401, json={"error": error})
    return httpx.Response(200, json=OPENAI_MODELS)


async def _org(client: httpx.AsyncClient) -> str:
    me = await sign_up(client)
    return f"/api/v1/orgs/{me['organizations'][0]['id']}"


async def _connect_openai(client: httpx.AsyncClient, providers: FakeProviders, org: str) -> dict[str, Any]:
    providers.answer("api.openai.com", handler=openai_answer)
    response = await client.put(f"{org}/providers/openai", json={"apiKey": OPENAI_KEY})
    assert response.status_code == 200, response.text
    saved: dict[str, Any] = response.json()
    return saved


async def test_a_working_key_is_saved_encrypted_and_never_shown(
    providers: FakeProviders, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        org = await _org(client)
        saved = await _connect_openai(client, providers, org)
        assert saved == {**saved, "id": "openai", "connected": True, "source": "org", "keyHint": "abcd", "status": "ok"}
        assert saved["lastVerifiedAt"]

        listed = (await client.get(f"{org}/providers")).text
        tested = (await client.post(f"{org}/providers/openai/test")).text
        models = (await client.get(f"{org}/models")).text
        for text in (str(saved), listed, tested, models, caplog.text):
            assert OPENAI_KEY not in text

        # In the database it's a Fernet token, not the key.
        async with app.state.sessionmaker() as db:
            stored = await db.scalar(select(ProviderCredential.encrypted_key))
        assert stored and OPENAI_KEY not in stored
        assert app.state.secrets.decrypt(stored) == OPENAI_KEY


async def test_a_bad_key_is_refused_with_the_providers_reason_but_not_the_key(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    org = await _org(client)
    providers.answer("api.openai.com", handler=openai_answer)
    wrong = "sk-proj-WRONGKEY99999999999999999zz"
    response = await client.put(f"{org}/providers/openai", json={"apiKey": wrong})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail.startswith("That key didn't work: 401: Incorrect API key provided")
    assert wrong not in detail
    providers_list = (await client.get(f"{org}/providers")).json()
    assert next(p for p in providers_list if p["id"] == "openai")["connected"] is False


async def test_an_unreachable_provider_is_a_clear_400(client: httpx.AsyncClient) -> None:
    org = await _org(client)  # no answer for api.groq.com: the connection is refused
    response = await client.put(f"{org}/providers/groq", json={"apiKey": GROQ_KEY})
    assert response.status_code == 400
    assert response.json()["detail"] == "That key didn't work: we couldn't reach it (ConnectError)"


async def test_only_owners_and_admins_change_keys_but_everyone_sees_providers_and_models(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    owner = await sign_up(client)
    org_id = owner["organizations"][0]["id"]
    org = f"/api/v1/orgs/{org_id}"
    await _connect_openai(client, providers, org)
    invite = await client.post(f"{org}/invitations", json={"email": "sara@acme.dev", "role": "member"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200

    assert (await client.put(f"{org}/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 403
    assert (await client.post(f"{org}/providers/openai/test")).status_code == 403
    assert (await client.delete(f"{org}/providers/openai")).status_code == 403
    listed = (await client.get(f"{org}/providers")).json()
    assert [p["id"] for p in listed] == ["anthropic", "openai", "gemini", "openrouter", "groq"]
    assert [m["id"] for m in (await client.get(f"{org}/models")).json()["models"]] == [
        "openai:gpt-5.5",
        "openai:o4-mini",
    ]


async def test_models_merge_across_providers_and_a_provider_that_is_down_is_reported(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    org = await _org(client)
    await _connect_openai(client, providers, org)
    providers.answer("api.anthropic.com", ANTHROPIC_MODELS)
    assert (await client.put(f"{org}/providers/anthropic", json={"apiKey": ANTHROPIC_KEY})).status_code == 200
    anthropic_call = next(r for r in providers.requests if r.url.host == "api.anthropic.com")
    assert anthropic_call.headers["x-api-key"] == ANTHROPIC_KEY
    assert anthropic_call.headers["anthropic-version"] == "2023-06-01"
    providers.answer("api.groq.com", GROQ_MODELS)
    assert (await client.put(f"{org}/providers/groq", json={"apiKey": GROQ_KEY})).status_code == 200

    providers.answer("api.groq.com", {"error": {"message": "Service unavailable"}}, status=503)
    listing = (await client.get(f"{org}/models", params={"refresh": "true"})).json()
    assert {m["id"] for m in listing["models"]} == {
        "openai:gpt-5.5",
        "openai:o4-mini",
        "anthropic:claude-opus-5-5",
    }
    opus = next(m for m in listing["models"] if m["provider"] == "anthropic")
    assert (opus["name"], opus["contextWindow"]) == ("Claude Opus 5.5", 1_000_000)
    assert listing["errors"] == [{"provider": "groq", "message": "Groq: 503: Service unavailable"}]

    # Without refresh, the list saved with the key is still served (for up to 10 minutes).
    only_groq = (await client.get(f"{org}/models", params={"provider": "groq"})).json()
    assert (only_groq["models"][0]["id"], only_groq["errors"]) == ("groq:llama-3.3-70b-versatile", [])


async def test_model_lists_are_cached_until_you_refresh(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    org = await _org(client)
    await _connect_openai(client, providers, org)
    calls = providers.calls_to("api.openai.com")  # the check when the key was saved
    await client.get(f"{org}/models")
    await client.get(f"{org}/models")
    assert providers.calls_to("api.openai.com") == calls  # saving the key filled the cache
    await client.get(f"{org}/models", params={"refresh": "true"})
    assert providers.calls_to("api.openai.com") == calls + 1


async def test_removing_a_key_disconnects_the_provider(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    org = await _org(client)
    await _connect_openai(client, providers, org)
    assert (await client.delete(f"{org}/providers/openai")).status_code == 204
    assert (await client.delete(f"{org}/providers/openai")).status_code == 404
    assert (await client.get(f"{org}/models")).json() == {"models": [], "errors": []}
    assert (await client.put(f"{org}/providers/nope", json={"apiKey": "x"})).status_code == 404


async def test_a_custom_server_gets_its_own_id_and_needs_no_key(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    org = await _org(client)
    providers.answer("localhost", {"object": "list", "data": [{"id": "llama3.2:latest"}]})
    body = {"label": "Ollama", "baseUrl": "http://localhost:11434/v1/"}
    saved = (await client.put(f"{org}/providers/custom", json=body)).json()
    assert saved["id"].startswith("custom-")
    assert (saved["kind"], saved["name"], saved["baseUrl"], saved["keyHint"]) == (
        "custom",
        "Ollama",
        "http://localhost:11434/v1",
        None,
    )
    assert "authorization" not in providers.requests[-1].headers

    models = (await client.get(f"{org}/models")).json()["models"]
    assert [m["id"] for m in models] == [f"{saved['id']}:llama3.2:latest"]
    bot = await client.post(f"{org}/bots", json={"name": "Local", "modelId": models[0]["id"]})
    assert bot.status_code == 201, bot.text

    second = await client.put(f"{org}/providers/custom", json={"label": "vLLM", "baseUrl": "http://localhost:8001/v1"})
    assert second.status_code == 200
    assert len([p for p in (await client.get(f"{org}/providers")).json() if p["kind"] == "custom"]) == 2
    assert (await client.put(f"{org}/providers/custom", json={"label": "No URL"})).status_code == 400


async def _custom_server_with_key(client: httpx.AsyncClient, providers: FakeProviders, org: str) -> dict[str, Any]:
    """A custom server that only answers with its key, saved with that key."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {CUSTOM_KEY}":
            return httpx.Response(401, json={"error": "a key is required"})
        return httpx.Response(200, json={"data": [{"id": "qwen3:32b"}]})

    providers.answer("localhost", handler=answer)
    body = {"label": "vLLM", "baseUrl": "http://localhost:8001/v1", "apiKey": CUSTOM_KEY}
    saved: dict[str, Any] = (await client.put(f"{org}/providers/custom", json=body)).json()
    assert saved["keyHint"] == CUSTOM_KEY[-4:]
    return saved


async def test_editing_a_custom_server_with_the_key_left_empty_keeps_the_key(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    org = await _org(client)
    saved = await _custom_server_with_key(client, providers, org)

    renamed = await client.put(f"{org}/providers/{saved['id']}", json={"label": "vLLM box", "apiKey": ""})
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["name"], renamed.json()["keyHint"]) == ("vLLM box", CUSTOM_KEY[-4:])
    assert providers.requests[-1].headers["authorization"] == f"Bearer {CUSTOM_KEY}"  # checked with the kept key
    same_url = {"label": "vLLM box", "baseUrl": "http://localhost:8001/v1/", "apiKey": ""}
    assert (await client.put(f"{org}/providers/{saved['id']}", json=same_url)).json()["keyHint"] == CUSTOM_KEY[-4:]


async def test_a_saved_key_is_never_sent_to_a_new_base_url(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    org = await _org(client)
    saved = await _custom_server_with_key(client, providers, org)
    calls = len(providers.requests)

    moved = {"label": "vLLM", "baseUrl": "http://localhost:9999/v1", "apiKey": ""}
    refused = await client.put(f"{org}/providers/{saved['id']}", json=moved)
    assert refused.status_code == 400
    assert "paste the API key again" in refused.json()["detail"]
    assert len(providers.requests) == calls  # the new address was never called with the old key

    providers.answer("localhost", {"data": [{"id": "llama3.2"}]})
    no_key = await client.put(f"{org}/providers/{saved['id']}", json={**moved, "noKey": True})
    assert no_key.status_code == 200, no_key.text
    assert (no_key.json()["baseUrl"], no_key.json()["keyHint"]) == ("http://localhost:9999/v1", None)
    assert "authorization" not in providers.requests[-1].headers

    new_key = await client.put(f"{org}/providers/{saved['id']}", json={**moved, "apiKey": "sk-a-brand-new-key-1234"})
    assert new_key.json()["keyHint"] == "1234"


async def test_a_bots_model_must_belong_to_a_connected_provider(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    org = await _org(client)
    refused = await client.post(f"{org}/bots", json={"name": "Scout", "modelId": "openai:gpt-5.5"})
    assert refused.status_code == 400
    assert refused.json()["detail"] == "OpenAI isn't connected. Add a key in Settings → Models & keys first."
    unknown = await client.post(f"{org}/bots", json={"name": "Scout", "modelId": "acme:big-model"})
    assert unknown.json()["detail"] == '"acme" isn\'t a model provider we know.'

    await _connect_openai(client, providers, org)
    bot = await client.post(f"{org}/bots", json={"name": "Scout", "modelId": "openai:gpt-5.5"})
    assert bot.status_code == 201
    # Not checked against the live list: lists change, and the run says so if a model is gone.
    edited = await client.patch(f"{org}/bots/{bot.json()['id']}", json={"modelId": "openai:gpt-6"})
    assert edited.status_code == 200


async def test_a_server_key_in_the_environment_counts_as_connected(providers: FakeProviders) -> None:
    settings = TEST_SETTINGS.model_copy(update={"groq_api_key": SecretStr(GROQ_KEY)})
    async with api_client(settings, providers) as (_, client):
        org = await _org(client)
        groq = next(p for p in (await client.get(f"{org}/providers")).json() if p["id"] == "groq")
        assert (groq["connected"], groq["source"], groq["keyHint"]) == (True, "env", None)
        bot = await client.post(f"{org}/bots", json={"name": "Fast", "modelId": "groq:llama-3.3-70b-versatile"})
        assert bot.status_code == 201

        providers.answer("api.groq.com", GROQ_MODELS)
        models = (await client.get(f"{org}/models")).json()["models"]
        assert [(m["id"], m["contextWindow"]) for m in models] == [("groq:llama-3.3-70b-versatile", 131072)]

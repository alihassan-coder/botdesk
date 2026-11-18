"""Member keys: a member's own model keys ("My keys" in Settings → Models & keys).

A member saves their own key for a built-in provider; it's checked live, encrypted like the
organization's, and shown only by its last 4 characters, and only to that member. A run uses its
requester's own key first, then the organization's, then the server's, then the stand-in model.
One member's key never serves another member's run, and it belongs to one organization only.
"""

import uuid
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy import select

from src.core.database import utcnow
from src.models import ProviderCredential
from src.runtime.chat_model import ModelResolver, StandInModel
from src.services import provider_service
from src.services.provider_service import ProviderAccess
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up
from tests.test_handoffs import TWO_TASKS, Org, org  # noqa: F401  (org is a fixture)
from tests.test_members import _invite, _sign_in
from tests.test_providers import OPENAI_KEY, OPENAI_MODELS, openai_answer

ORGS = "/api/v1/orgs"
SARAS_KEY = "sk-proj-SARA0000000000000000000sara"


async def _team(client: httpx.AsyncClient) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Ali owns the org; Sara joins as a member and is signed in. Returns (org path, ali, sara)."""
    ali = await sign_up(client, name="Ali", email="ali@acme.dev")
    path = f"{ORGS}/{ali['organizations'][0]['id']}"
    token = await _invite(client, ali["organizations"][0]["id"], "sara@acme.dev")
    client.cookies.clear()
    sara = await sign_up(client, name="Sara", email="sara@acme.dev")
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
    return path, ali, sara


def _key_of(model: Any) -> str:
    assert isinstance(model, ChatOpenAI)
    assert isinstance(model.openai_api_key, SecretStr)
    return model.openai_api_key.get_secret_value()


def two_openai_keys(request: httpx.Request) -> httpx.Response:
    """OpenAI's /models for two accounts: the organization's key sees gpt-5.5, Sara's sees o4-mini too."""
    auth = request.headers.get("authorization")
    if auth == f"Bearer {SARAS_KEY}":
        return httpx.Response(200, json=OPENAI_MODELS)
    if auth == f"Bearer {OPENAI_KEY}":
        return httpx.Response(200, json={"data": [{"id": "gpt-5.5", "object": "model"}]})
    return httpx.Response(401, json={"error": {"message": "Incorrect API key provided."}})


def _by_id(providers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in providers}


# Saving, seeing and removing your own keys


async def test_a_member_saves_their_own_key_and_sees_only_its_hint(providers: FakeProviders) -> None:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        path, _, sara = await _team(client)
        providers.answer("api.openai.com", handler=openai_answer)

        response = await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})

        assert response.status_code == 200, response.text
        saved = response.json()
        assert (saved["id"], saved["connected"], saved["source"], saved["keyHint"]) == (
            "openai",
            True,
            "member",
            "abcd",
        )
        mine = _by_id((await client.get(f"{path}/me/providers")).json())
        assert mine["openai"]["keyHint"] == "abcd"
        assert mine["groq"]["connected"] is False
        assert "custom" not in {p["kind"] for p in mine.values()}
        # The organization's list doesn't show a member's key.
        assert _by_id((await client.get(f"{path}/providers")).json())["openai"]["connected"] is False
        async with app.state.sessionmaker() as db:
            row = (await db.scalars(select(ProviderCredential))).one()
        assert row.user_id == uuid.UUID(sara["user"]["id"])
        assert OPENAI_KEY not in row.encrypted_key  # encrypted at rest
        assert app.state.secrets.decrypt(row.encrypted_key) == OPENAI_KEY


async def test_a_member_key_is_never_readable_through_the_api(providers: FakeProviders) -> None:
    async with api_client(TEST_SETTINGS, providers) as (_, client):
        path, _, _ = await _team(client)
        providers.answer("api.openai.com", handler=openai_answer)
        answers = [await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})]

        for url in ("/me/providers", "/providers", "/models", "/models?refresh=true"):
            answers.append(await client.get(f"{path}{url}"))
        await _sign_in(client, "ali@acme.dev")  # the owner
        for url in ("/me/providers", "/providers", "/models"):
            answers.append(await client.get(f"{path}{url}"))

        assert all(answer.is_success for answer in answers)
        assert not [answer.request.url for answer in answers if OPENAI_KEY in answer.text]


async def test_a_bad_key_is_refused(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    path, _, _ = await _team(client)
    providers.answer("api.openai.com", handler=openai_answer)
    response = await client.put(f"{path}/me/providers/openai", json={"apiKey": "sk-wrong-000000000000"})
    assert response.status_code == 400
    assert response.json()["detail"].startswith("That key didn't work")
    assert "sk-wrong-000000000000" not in response.text


async def test_custom_servers_are_for_the_whole_organization(client: httpx.AsyncClient) -> None:
    path, _, _ = await _team(client)
    response = await client.put(f"{path}/me/providers/custom", json={"baseUrl": "http://x.test/v1", "label": "Mine"})
    assert response.status_code == 400
    assert response.json()["detail"] == provider_service.MEMBER_KEYS_BUILT_IN_ONLY


async def test_members_see_and_remove_only_their_own_keys(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    path, _, _ = await _team(client)
    providers.answer("api.openai.com", handler=openai_answer)
    assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200

    # Not even the owner sees or removes it, through either list.
    await _sign_in(client, "ali@acme.dev")
    assert _by_id((await client.get(f"{path}/me/providers")).json())["openai"]["connected"] is False
    assert (await client.delete(f"{path}/me/providers/openai")).status_code == 404
    assert (await client.delete(f"{path}/providers/openai")).status_code == 404
    assert (await client.post(f"{path}/providers/openai/test")).status_code == 404

    await _sign_in(client, "sara@acme.dev")
    assert _by_id((await client.get(f"{path}/me/providers")).json())["openai"]["keyHint"] == "abcd"
    assert (await client.delete(f"{path}/me/providers/openai")).status_code == 204
    assert _by_id((await client.get(f"{path}/me/providers")).json())["openai"]["connected"] is False


async def test_your_key_and_the_organizations_live_side_by_side(providers: FakeProviders) -> None:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        path, _, _ = await _team(client)
        providers.answer("api.openai.com", handler=two_openai_keys)
        assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": SARAS_KEY})).status_code == 200
        await _sign_in(client, "ali@acme.dev")
        assert (await client.put(f"{path}/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200

        # Replacing or removing the organization's key leaves Sara's alone.
        assert (await client.delete(f"{path}/providers/openai")).status_code == 204
        async with app.state.sessionmaker() as db:
            (left,) = await db.scalars(select(ProviderCredential))
        assert left.user_id is not None and left.key_hint == "sara"


async def test_a_member_lists_models_with_their_own_key_first(providers: FakeProviders) -> None:
    """What a member's runs would use: their own key, so its models are the ones they see."""
    async with api_client(TEST_SETTINGS, providers) as (_, client):
        path, _, _ = await _team(client)
        providers.answer("api.openai.com", handler=two_openai_keys)
        assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": SARAS_KEY})).status_code == 200
        await _sign_in(client, "ali@acme.dev")
        assert (await client.put(f"{path}/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200

        calls = providers.calls_to("api.openai.com")
        alis = {m["id"] for m in (await client.get(f"{path}/models")).json()["models"]}
        await _sign_in(client, "sara@acme.dev")
        saras = {m["id"] for m in (await client.get(f"{path}/models")).json()["models"]}
        await _sign_in(client, "ali@acme.dev")
        alis_again = {m["id"] for m in (await client.get(f"{path}/models")).json()["models"]}

        assert "openai:o4-mini" in saras
        # Sara's list, cached for her when she saved her key, never answers for Ali (nor the other
        # way round), and neither pushes the other's out of the cache: no list was fetched again.
        assert alis == alis_again == {"openai:gpt-5.5"}
        assert providers.calls_to("api.openai.com") == calls


async def test_a_member_with_their_own_key_may_pick_its_models(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    path, _, _ = await _team(client)
    providers.answer("api.openai.com", handler=openai_answer)
    refused = await client.post(f"{path}/bots", json={"name": "Scout", "modelId": "openai:gpt-5.5"})
    assert refused.status_code == 400
    assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200

    assert (await client.post(f"{path}/bots", json={"name": "Scout", "modelId": "openai:gpt-5.5"})).status_code == 201
    models = (await client.get(f"{path}/models")).json()["models"]
    assert "openai:gpt-5.5" in {m["id"] for m in models}
    # Ali has no key of his own and the organization none: OpenAI isn't connected for him.
    await _sign_in(client, "ali@acme.dev")
    assert "openai:gpt-5.5" not in {m["id"] for m in (await client.get(f"{path}/models")).json()["models"]}


async def test_your_key_belongs_to_one_organization(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    path, _, sara = await _team(client)
    providers.answer("api.openai.com", handler=openai_answer)
    assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200
    saras_own = f"{ORGS}/{sara['organizations'][0]['id']}"  # the organization sign-up made her

    assert _by_id((await client.get(f"{saras_own}/me/providers")).json())["openai"]["connected"] is False
    # And nobody reaches into an organization they're not in.
    await _sign_in(client, "ali@acme.dev")
    for call in (
        client.get(f"{saras_own}/me/providers"),
        client.put(f"{saras_own}/me/providers/openai", json={"apiKey": OPENAI_KEY}),
        client.delete(f"{saras_own}/me/providers/openai"),
    ):
        assert (await call).status_code == 404


async def test_only_signed_in_members_have_keys(client: httpx.AsyncClient) -> None:
    path, _, _ = await _team(client)
    client.cookies.clear()
    assert (await client.get(f"{path}/me/providers")).status_code == 401


# Which key a run uses


async def test_a_run_uses_its_requesters_key_then_the_orgs_then_the_servers_then_the_stand_in(
    providers: FakeProviders,
) -> None:
    settings = TEST_SETTINGS.model_copy(update={"openai_api_key": SecretStr("sk-from-the-environment")})
    async with api_client(settings, providers) as (app, client):
        path, ali, sara = await _team(client)
        org_id = uuid.UUID(path.rsplit("/", 1)[1])
        ali_id, sara_id = uuid.UUID(ali["user"]["id"]), uuid.UUID(sara["user"]["id"])
        resolve = ModelResolver(settings, app.state.sessionmaker, app.state.secrets)

        async def save(key: str, member_id: uuid.UUID | None) -> None:
            async with app.state.sessionmaker() as db:
                await provider_service.save_credential(
                    db,
                    org_id=org_id,
                    user_id=ali_id,
                    member_id=member_id,
                    connection=ProviderAccess("openai", "openai", "OpenAI", key),
                    secrets=app.state.secrets,
                    verified_at=utcnow(),
                )
                await db.commit()

        await save("sk-sara-own-key", sara_id)
        assert _key_of(await resolve(org_id, "openai:gpt-5.5", sara_id)) == "sk-sara-own-key"
        # Never one member's key for another member's run, nor for a run with no requester.
        assert _key_of(await resolve(org_id, "openai:gpt-5.5", ali_id)) == "sk-from-the-environment"
        assert _key_of(await resolve(org_id, "openai:gpt-5.5", None)) == "sk-from-the-environment"

        await save("sk-the-orgs-key", None)
        assert _key_of(await resolve(org_id, "openai:gpt-5.5", sara_id)) == "sk-sara-own-key"
        assert _key_of(await resolve(org_id, "openai:gpt-5.5", ali_id)) == "sk-the-orgs-key"
        assert _key_of(await resolve(org_id, "openai:gpt-5.5", None)) == "sk-the-orgs-key"
        # Sara's key is hers in this organization only.
        assert isinstance(await resolve(uuid.uuid4(), "anthropic:claude-opus-5-5", sara_id), StandInModel)


async def test_a_bot_on_a_provider_only_your_key_connects_gives_others_the_stand_in(
    providers: FakeProviders,
) -> None:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        path, ali, sara = await _team(client)
        providers.answer("api.openai.com", handler=openai_answer)
        assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200
        org_id = uuid.UUID(path.rsplit("/", 1)[1])
        resolve = ModelResolver(TEST_SETTINGS, app.state.sessionmaker, app.state.secrets)

        assert _key_of(await resolve(org_id, "openai:gpt-5.5", uuid.UUID(sara["user"]["id"]))) == OPENAI_KEY
        assert isinstance(await resolve(org_id, "openai:gpt-5.5", uuid.UUID(ali["user"]["id"])), StandInModel)


OPENROUTER_MODELS = {
    "data": [
        {"id": "x-ai/grok-4.5", "name": "xAI: Grok 4.5", "pricing": {"prompt": "0.000003", "completion": "0.000015"}}
    ]
}


async def test_a_run_on_your_own_openrouter_key_is_still_priced(providers: FakeProviders) -> None:
    """Budgets need the price: with no organization key, the requester's own key fetches the list."""
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        path, ali, sara = await _team(client)
        providers.answer("openrouter.ai", OPENROUTER_MODELS)
        assert (
            await client.put(f"{path}/me/providers/openrouter", json={"apiKey": "sk-or-v1-sara00000000"})
        ).is_success
        org_id = uuid.UUID(path.rsplit("/", 1)[1])
        resolve = ModelResolver(TEST_SETTINGS, app.state.sessionmaker, app.state.secrets, app.state.models)

        saras = await resolve.price(org_id, "openrouter:x-ai/grok-4.5", uuid.UUID(sara["user"]["id"]))
        alis = await resolve.price(org_id, "openrouter:x-ai/grok-4.5", uuid.UUID(ali["user"]["id"]))

        assert saras.pricing is not None and saras.pricing.output_per_mtok == 15.0
        assert alis.pricing is None  # Ali's runs have no OpenRouter key: his never use Sara's


async def test_leaving_the_organization_removes_your_keys_there(providers: FakeProviders) -> None:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        path, _, sara = await _team(client)
        providers.answer("api.openai.com", handler=openai_answer)
        assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200

        assert (await client.delete(f"{path}/members/{sara['user']['id']}")).status_code == 204

        async with app.state.sessionmaker() as db:
            assert (await db.scalars(select(ProviderCredential))).all() == []


async def test_being_removed_by_an_admin_removes_your_keys_there(providers: FakeProviders) -> None:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        path, _, sara = await _team(client)
        providers.answer("api.openai.com", handler=openai_answer)
        assert (await client.put(f"{path}/me/providers/openai", json={"apiKey": OPENAI_KEY})).status_code == 200
        await _sign_in(client, "ali@acme.dev")

        assert (await client.delete(f"{path}/members/{sara['user']['id']}")).status_code == 204

        async with app.state.sessionmaker() as db:
            assert (await db.scalars(select(ProviderCredential))).all() == []


async def test_a_run_and_the_runs_it_hands_off_to_look_up_models_for_its_requester(org: Org) -> None:  # noqa: F811
    asked: list[uuid.UUID | None] = []

    async def model_for(_org_id: uuid.UUID, _model_id: str, requester_id: uuid.UUID | None) -> BaseChatModel:
        asked.append(requester_id)
        return org.model

    org.runs.model_for = model_for
    org.model.plans["Chief"] = TWO_TASKS
    org.model.replies["Chief"] = "Done."
    parent = await org.send(await org.dm("chief"), "Plan tonight's outreach")

    assert (await org.run(parent)).status == "succeeded"
    assert len(asked) >= 3  # the parent (twice: before and after its tasks) and both children
    assert set(asked) == {org.user_id}

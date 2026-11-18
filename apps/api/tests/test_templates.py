"""Marketplace templates: one catalogue kept in code (`src/templates/catalogue.json`), listed by
`GET /templates` and hired by `POST /orgs/{id}/templates/{templateId}/hire`."""

from collections.abc import AsyncIterator
from typing import Any, get_args

import httpx
import pytest

from src.core.config import Settings
from src.models.bot import AvatarColor, SecurityLevel
from src.services.template_service import HIRED_BUDGET_USD
from src.templates import TEMPLATES
from tests.conftest import FakeProviders, api_client, sign_up

FIELDS = {"id", "name", "role", "category", "description", "instructions", "avatarColor", "securityLevel", "plugins"}
# Gmail loaded, as on a server with Google set up.
WITH_GMAIL = Settings(environment="test", database_url="sqlite+aiosqlite://", plugins="demo,gmail", _env_file=None)


@pytest.fixture
async def gmail_server(providers: FakeProviders) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(WITH_GMAIL, providers) as (_, http):
        yield http


async def _org(client: httpx.AsyncClient) -> str:
    me = await sign_up(client)
    return f"/api/v1/orgs/{me['organizations'][0]['id']}"


def _by_id(templates: list[dict[str, Any]], template_id: str) -> dict[str, Any]:
    return next(t for t in templates if t["id"] == template_id)


async def test_signed_in_people_list_the_catalogue(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/templates")).status_code == 401
    await sign_up(client)
    response = await client.get("/api/v1/templates")
    assert response.status_code == 200, response.text
    listed = response.json()
    assert [t["id"] for t in listed] == [t.id for t in TEMPLATES]
    assert all(set(t) == FIELDS for t in listed)
    chief = _by_id(listed, "chief")
    assert chief["name"] == "Chief" and "team.handoff" in chief["instructions"]


async def test_the_list_names_only_the_plugins_this_server_loaded(
    client: httpx.AsyncClient, gmail_server: httpx.AsyncClient
) -> None:
    await sign_up(client)
    await sign_up(gmail_server)
    without = _by_id((await client.get("/api/v1/templates")).json(), "inbox-zero")
    with_gmail = _by_id((await gmail_server.get("/api/v1/templates")).json(), "inbox-zero")
    assert without["plugins"] == []
    assert with_gmail["plugins"] == ["gmail"]


def test_every_template_is_ready_to_hire() -> None:
    """Each one gives a bot a real job: a name, a role, instructions, valid choices, unique ids."""
    colors, levels = set(get_args(AvatarColor)), set(get_args(SecurityLevel))
    assert len({t.id for t in TEMPLATES}) == len(TEMPLATES) >= 7
    for template in TEMPLATES:
        assert template.name and template.role and template.description and template.category, template.id
        assert len(template.instructions) > 80, template.id
        assert template.avatar_color in colors and template.security_level in levels, template.id


async def test_hiring_a_template_makes_its_bot(gmail_server: httpx.AsyncClient) -> None:
    """Its name, job and instructions, the instance's default model, a budget any member may give,
    and its plugins switched on: Gmail is on with no account yet, so its Tools tab asks for one."""
    org = await _org(gmail_server)
    response = await gmail_server.post(f"{org}/templates/inbox-zero/hire")
    assert response.status_code == 201, response.text
    bot = response.json()
    template = next(t for t in TEMPLATES if t.id == "inbox-zero")
    assert {k: bot[k] for k in ("name", "role", "description", "instructions", "avatarColor", "modelId")} == {
        "name": template.name,
        "role": template.role,
        "description": template.description,
        "instructions": template.instructions,
        "avatarColor": template.avatar_color,
        "modelId": "",
    }
    assert bot["monthlyBudgetUsd"] == HIRED_BUDGET_USD
    tools = {p["pluginId"]: p for p in (await gmail_server.get(f"{org}/bots/{bot['id']}/tools")).json()["plugins"]}
    assert (tools["gmail"]["enabled"], tools["gmail"]["connectionId"]) == (True, None)
    assert tools["demo"]["enabled"]  # every new bot's defaults stay


async def test_chief_can_hand_off_once_hired(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    chief = (await client.post(f"{org}/templates/chief/hire")).json()
    assert "chief of staff" in chief["instructions"]
    tools = (await client.get(f"{org}/bots/{chief['id']}/tools")).json()["plugins"]
    assert {p["pluginId"]: p["enabled"] for p in tools}.get("team") is not False


@pytest.mark.parametrize(
    ("org_default", "template_id", "starts_at"),
    [
        ("ask-before-acting", "expense-clerk", "read-only"),  # the template is stricter
        ("read-only", "inbox-zero", "read-only"),  # the organization is stricter
        ("autonomous", "inbox-zero", "ask-before-acting"),  # never looser than the template
    ],
)
async def test_a_hired_bot_starts_at_the_stricter_level(
    client: httpx.AsyncClient, org_default: str, template_id: str, starts_at: str
) -> None:
    org = await _org(client)
    assert (await client.patch(org, json={"defaultSecurityLevel": org_default})).status_code == 200
    bot = (await client.post(f"{org}/templates/{template_id}/hire")).json()
    assert bot["securityLevel"] == starts_at


async def test_a_member_may_hire_and_an_unknown_template_is_a_404(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    invite = await client.post(f"{org}/invitations", json={"email": "omar@acme.dev", "role": "member"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()
    await sign_up(client, name="Omar", email="omar@acme.dev")
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200

    assert (await client.post(f"{org}/templates/researcher/hire")).status_code == 201
    missing = await client.post(f"{org}/templates/nope/hire")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "That bot isn't in the marketplace any more."


async def test_only_members_of_the_organization_can_hire_into_it(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    client.cookies.clear()
    await sign_up(client, name="Mallory", email="mallory@evil.dev")
    assert (await client.post(f"{org}/templates/chief/hire")).status_code == 404

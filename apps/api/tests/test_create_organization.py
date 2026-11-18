"""Creating another organization (POST /orgs): the creator owns it, as with sign-up's first one."""

import httpx

from tests.conftest import sign_up

ORGS = "/api/v1/orgs"


async def test_the_creator_owns_the_new_organization(client: httpx.AsyncClient) -> None:
    await sign_up(client)

    response = await client.post(ORGS, json={"name": "Acme Labs"})

    assert response.status_code == 201, response.text
    org = response.json()
    assert (org["name"], org["slug"], org["role"]) == ("Acme Labs", "acme-labs", "owner")
    assert (org["defaultSecurityLevel"], org["maxSecurityLevel"], org["monthlyBudgetUsd"]) == (
        "ask-before-acting",
        "autonomous",
        None,
    )
    assert [o["name"] for o in (await client.get(ORGS)).json()] == ["Ali's team", "Acme Labs"]
    members = (await client.get(f"{ORGS}/{org['id']}/members")).json()
    assert [(m["name"], m["role"]) for m in members] == [("Ali Hassan", "owner")]


async def test_the_new_organization_is_ready_to_use(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    org = (await client.post(ORGS, json={"name": "Acme Labs"})).json()

    bot = await client.post(f"{ORGS}/{org['id']}/bots", json={"name": "Scout"})

    assert bot.status_code == 201, bot.text


async def test_a_taken_address_gets_a_number(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    first = (await client.post(ORGS, json={"name": "Acme"})).json()
    second = (await client.post(ORGS, json={"name": "Acme"})).json()
    assert (first["slug"], second["slug"]) == ("acme", "acme-2")


async def test_a_chosen_address_must_be_free(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    assert (await client.post(ORGS, json={"name": "Acme", "slug": "acme-hq"})).json()["slug"] == "acme-hq"
    response = await client.post(ORGS, json={"name": "Other", "slug": "acme-hq"})
    assert response.status_code == 409
    assert response.json()["detail"] == "That address is taken. Try another."


async def test_a_name_is_required(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    assert (await client.post(ORGS, json={"name": "   "})).status_code == 400
    assert (await client.post(ORGS, json={})).status_code == 422


async def test_only_signed_in_people_create_organizations(client: httpx.AsyncClient) -> None:
    assert (await client.post(ORGS, json={"name": "Acme"})).status_code == 401


async def test_nobody_else_sees_the_new_organization(client: httpx.AsyncClient) -> None:
    await sign_up(client, name="Ali", email="ali@acme.dev")
    org = (await client.post(ORGS, json={"name": "Acme Labs"})).json()
    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")
    assert (await client.get(f"{ORGS}/{org['id']}")).status_code == 404


async def test_a_long_name_still_gets_an_address_that_fits(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    name = "The Extraordinarily Long Name Of A Very Serious Research Organization For Testing Limits"
    first = (await client.post(ORGS, json={"name": name})).json()
    second = (await client.post(ORGS, json={"name": name})).json()
    assert len(first["slug"]) <= 64 and len(second["slug"]) <= 64
    assert second["slug"] == f"{first['slug']}-2"


async def test_a_new_organization_shares_nothing_with_your_others(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    first = f"{ORGS}/{me['organizations'][0]['id']}"
    await client.post(f"{first}/bots", json={"name": "Scout"})
    assert (await client.patch(first, json={"maxSecurityLevel": "read-only"})).status_code == 200

    second = f"{ORGS}/{(await client.post(ORGS, json={'name': 'Acme Labs'})).json()['id']}"

    assert (await client.get(f"{second}/bots")).json() == []
    assert (await client.get(second)).json()["maxSecurityLevel"] == "autonomous"

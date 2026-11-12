import httpx

from tests.conftest import sign_up

ORGS = "/api/v1/orgs"


async def test_list_my_organizations(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    orgs = (await client.get(ORGS)).json()
    assert [(org["slug"], org["role"], org["plan"]) for org in orgs] == [("ali-s-team", "owner", "free")]


async def test_the_owner_can_rename_the_organization(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    org_id = me["organizations"][0]["id"]

    response = await client.patch(f"{ORGS}/{org_id}", json={"name": "Acme Labs", "slug": "acme"})
    assert response.status_code == 200
    assert response.json()["name"] == "Acme Labs"
    assert (await client.get(f"{ORGS}/{org_id}")).json()["slug"] == "acme"


async def test_an_address_can_only_be_used_once(client: httpx.AsyncClient) -> None:
    ali = await sign_up(client, name="Ali", email="ali@acme.dev")
    await client.patch(f"{ORGS}/{ali['organizations'][0]['id']}", json={"slug": "acme"})

    client.cookies.clear()
    sara = await sign_up(client, name="Sara", email="sara@acme.dev")
    response = await client.patch(f"{ORGS}/{sara['organizations'][0]['id']}", json={"slug": "acme"})
    assert response.status_code == 409


async def test_bad_addresses_are_refused(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    response = await client.patch(f"{ORGS}/{me['organizations'][0]['id']}", json={"slug": "Not A Slug!"})
    assert response.status_code == 422


async def test_someone_elses_organization_looks_like_it_does_not_exist(client: httpx.AsyncClient) -> None:
    ali = await sign_up(client, name="Ali", email="ali@acme.dev")
    alis_org = ali["organizations"][0]["id"]

    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")
    for response in (
        await client.get(f"{ORGS}/{alis_org}"),
        await client.patch(f"{ORGS}/{alis_org}", json={"name": "Mine now"}),
        await client.get(f"{ORGS}/{alis_org}/members"),
    ):
        assert response.status_code == 404


async def test_members_lists_people_with_their_roles(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    members = (await client.get(f"{ORGS}/{me['organizations'][0]['id']}/members")).json()
    assert [(m["name"], m["role"]) for m in members] == [("Ali Hassan", "owner")]


async def test_health(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).json() == {"status": "ok"}

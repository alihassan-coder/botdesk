import httpx

from tests.conftest import sign_up

ORGS = "/api/v1/orgs"


async def test_list_my_organizations(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    orgs = (await client.get(ORGS)).json()
    assert [(org["slug"], org["role"]) for org in orgs] == [("ali-s-team", "owner")]
    assert "plan" not in orgs[0]


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


# The default security level for new bots


async def _join(client: httpx.AsyncClient, org_id: str, name: str, email: str, role: str) -> None:
    """Invite someone with `role` and sign them in on `client` (they accept the invite)."""
    invite = await client.post(f"{ORGS}/{org_id}/invitations", json={"email": email, "role": role})
    assert invite.status_code == 201, invite.text
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    client.cookies.clear()
    await sign_up(client, name=name, email=email)
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200


async def test_new_organizations_ask_before_acting_by_default(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    assert me["organizations"][0]["defaultSecurityLevel"] == "ask-before-acting"
    org = (await client.get(f"{ORGS}/{me['organizations'][0]['id']}")).json()
    assert org["defaultSecurityLevel"] == "ask-before-acting"


async def test_owners_and_admins_set_the_default(client: httpx.AsyncClient) -> None:
    me = await sign_up(client, name="Ali", email="ali@acme.dev")
    org = f"{ORGS}/{me['organizations'][0]['id']}"

    response = await client.patch(org, json={"defaultSecurityLevel": "read-only"})
    assert response.status_code == 200, response.text
    assert response.json()["defaultSecurityLevel"] == "read-only"
    assert (await client.patch(org, json={"name": "Acme"})).json()["defaultSecurityLevel"] == "read-only"  # kept
    assert (await client.patch(org, json={"defaultSecurityLevel": "yolo"})).status_code == 422

    await _join(client, me["organizations"][0]["id"], "Nadia", "nadia@acme.dev", "admin")
    admin_set = await client.patch(org, json={"defaultSecurityLevel": "autonomous"})
    assert admin_set.status_code == 200, admin_set.text
    assert admin_set.json()["defaultSecurityLevel"] == "autonomous"


async def test_a_member_cant_change_the_default(client: httpx.AsyncClient) -> None:
    me = await sign_up(client, name="Ali", email="ali@acme.dev")
    org_id = me["organizations"][0]["id"]
    await _join(client, org_id, "Sara", "sara@acme.dev", "member")
    refused = await client.patch(f"{ORGS}/{org_id}", json={"defaultSecurityLevel": "autonomous"})
    assert refused.status_code == 403
    assert (await client.get(f"{ORGS}/{org_id}")).json()["defaultSecurityLevel"] == "ask-before-acting"


async def test_new_bots_get_the_default_unless_they_pick_a_level(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    org = f"{ORGS}/{me['organizations'][0]['id']}"
    await client.patch(org, json={"defaultSecurityLevel": "read-only"})

    plain = (await client.post(f"{org}/bots", json={"name": "Plain"})).json()
    assert plain["securityLevel"] == "read-only"
    chosen = (await client.post(f"{org}/bots", json={"name": "Chosen", "securityLevel": "autonomous"})).json()
    assert chosen["securityLevel"] == "autonomous"

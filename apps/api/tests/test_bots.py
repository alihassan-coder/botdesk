import httpx

from tests.conftest import sign_up


async def _bots_url(client: httpx.AsyncClient) -> str:
    me = await sign_up(client)
    return f"/api/v1/orgs/{me['organizations'][0]['id']}/bots"


async def test_hire_a_bot_and_see_it_in_the_list(client: httpx.AsyncClient) -> None:
    bots = await _bots_url(client)
    response = await client.post(
        bots,
        json={
            "name": "Release Notes",
            "role": "Writing",
            "description": "Turns merged pull requests into release notes.",
            "avatarColor": "emerald",
            "modelId": "anthropic:claude-sonnet-5-5",
        },
    )
    assert response.status_code == 201, response.text
    bot = response.json()
    assert (bot["handle"], bot["securityLevel"], bot["status"]) == ("release-notes", "ask-before-acting", "idle")

    listed = (await client.get(bots)).json()
    assert [b["name"] for b in listed] == ["Release Notes"]


async def test_handles_stay_unique_and_follow_renames(client: httpx.AsyncClient) -> None:
    bots = await _bots_url(client)
    first = (await client.post(bots, json={"name": "Researcher"})).json()
    second = (await client.post(bots, json={"name": "Researcher"})).json()
    assert (first["handle"], second["handle"]) == ("researcher", "researcher-2")

    renamed = (await client.patch(f"{bots}/{second['id']}", json={"name": "Deep Researcher"})).json()
    assert renamed["handle"] == "deep-researcher"


async def test_editing_changes_only_what_you_send(client: httpx.AsyncClient) -> None:
    bots = await _bots_url(client)
    bot = (await client.post(bots, json={"name": "Inbox", "role": "Email"})).json()
    updated = (await client.patch(f"{bots}/{bot['id']}", json={"securityLevel": "read-only"})).json()
    assert (updated["role"], updated["securityLevel"], updated["handle"]) == ("Email", "read-only", "inbox")


async def test_bad_input_is_refused(client: httpx.AsyncClient) -> None:
    bots = await _bots_url(client)
    for body in ({"name": "  "}, {"name": "X", "securityLevel": "yolo"}, {"name": "X", "modelId": "no colon"}):
        assert (await client.post(bots, json=body)).status_code == 422


async def test_owners_can_remove_bots(client: httpx.AsyncClient) -> None:
    bots = await _bots_url(client)
    bot = (await client.post(bots, json={"name": "Temp"})).json()
    assert (await client.delete(f"{bots}/{bot['id']}")).status_code == 204
    assert (await client.get(f"{bots}/{bot['id']}")).status_code == 404


async def test_bots_are_private_to_their_organization(client: httpx.AsyncClient) -> None:
    alis_bots = await _bots_url(client)
    bot = (await client.post(alis_bots, json={"name": "Secret"})).json()

    client.cookies.clear()
    sara = await sign_up(client, name="Sara", email="sara@acme.dev")
    saras_bots = f"/api/v1/orgs/{sara['organizations'][0]['id']}/bots"
    assert (await client.get(alis_bots)).status_code == 404  # not her organization
    assert (await client.get(f"{saras_bots}/{bot['id']}")).status_code == 404  # not her bot
    assert (await client.get(saras_bots)).json() == []

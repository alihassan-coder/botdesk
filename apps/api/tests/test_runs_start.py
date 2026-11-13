"""Which bots reply to a message: always the bot in a DM, only @mentioned bots in a group."""

import httpx

from tests.conftest import sign_up


async def _org_with_bots(client: httpx.AsyncClient) -> tuple[str, list[dict[str, str]]]:
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bots = [(await client.post(f"{org}/bots", json={"name": name})).json() for name in ("Scout", "Inbox Manager")]
    return org, bots


async def test_a_message_in_a_bot_chat_starts_one_run(client: httpx.AsyncClient) -> None:
    org, (scout, _) = await _org_with_bots(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": scout["id"]})).json()

    sent = await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Hi"})

    assert sent.status_code == 201
    assert sent.json()["parts"][0]["text"] == "Hi"
    assert len(sent.json()["runIds"]) == 1
    run = (await client.get(f"{org}/runs/{sent.json()['runIds'][0]}")).json()
    assert run["botId"] == scout["id"]
    assert run["status"] == "queued"
    assert run["triggerMessageId"] == sent.json()["id"]


async def test_in_a_group_only_mentioned_bots_reply(client: httpx.AsyncClient) -> None:
    org, (scout, inbox) = await _org_with_bots(client)
    group = (
        await client.post(f"{org}/threads/groups", json={"title": "Launch", "botIds": [scout["id"], inbox["id"]]})
    ).json()
    messages = f"{org}/threads/{group['id']}/messages"

    assert (await client.post(messages, json={"text": "Morning all"})).json()["runIds"] == []
    one = (await client.post(messages, json={"text": "@inbox-manager any news?"})).json()["runIds"]
    both = (await client.post(messages, json={"text": "@Scout and @inbox-manager, sync up"})).json()["runIds"]

    bots_of = [(await client.get(f"{org}/runs/{run_id}")).json()["botId"] for run_id in [*one, *both]]
    assert bots_of == [inbox["id"], scout["id"], inbox["id"]]


async def test_a_bot_that_is_not_in_the_group_is_not_started(client: httpx.AsyncClient) -> None:
    org, (scout, _) = await _org_with_bots(client)
    group = (await client.post(f"{org}/threads/groups", json={"title": "Just Scout", "botIds": [scout["id"]]})).json()
    sent = await client.post(f"{org}/threads/{group['id']}/messages", json={"text": "@inbox-manager hello?"})
    assert sent.json()["runIds"] == []


async def test_people_outside_the_chat_cannot_see_its_runs(client: httpx.AsyncClient) -> None:
    org, (scout, _) = await _org_with_bots(client)
    thread = (await client.post(f"{org}/threads/dm", json={"botId": scout["id"]})).json()
    run_id = (await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Hi"})).json()["runIds"][0]

    client.cookies.clear()
    await sign_up(client, name="Mallory", email="mallory@evil.dev")
    assert (await client.get(f"{org}/runs/{run_id}")).status_code == 404
    assert (await client.get(f"{org}/threads/{thread['id']}/events", params={"follow": False})).status_code == 404
    assert (await client.get(f"{org}/threads/{thread['id']}/runs", params={"active": True})).status_code == 404


async def _latest_event_id(client: httpx.AsyncClient, thread: str) -> int:
    body = (await client.get(f"{thread}/events", params={"follow": False, "after": 0})).text
    return max((int(line[4:]) for line in body.splitlines() if line.startswith("id: ")), default=0)


async def test_a_chat_lists_its_unfinished_runs_and_where_its_stream_is(client: httpx.AsyncClient) -> None:
    org, (scout, _) = await _org_with_bots(client)
    thread = f"{org}/threads/{(await client.post(f'{org}/threads/dm', json={'botId': scout['id']})).json()['id']}"

    assert (await client.get(f"{thread}/runs", params={"active": True})).json() == {"runs": [], "lastEventId": 0}

    run_id = (await client.post(f"{thread}/messages", json={"text": "Hi"})).json()["runIds"][0]
    active = (await client.get(f"{thread}/runs", params={"active": True})).json()
    assert [(run["id"], run["status"], run["botId"], run["error"]) for run in active["runs"]] == [
        (run_id, "queued", scout["id"], None)
    ]
    assert active["lastEventId"] == await _latest_event_id(client, thread) > 0

    await client.post(f"{org}/runs/{run_id}/cancel")
    after_stop = (await client.get(f"{thread}/runs", params={"active": True})).json()
    assert after_stop["runs"] == []
    assert after_stop["lastEventId"] == await _latest_event_id(client, thread) > active["lastEventId"]
    every = (await client.get(f"{thread}/runs")).json()["runs"]
    assert [(run["id"], run["status"]) for run in every] == [(run_id, "cancelled")]

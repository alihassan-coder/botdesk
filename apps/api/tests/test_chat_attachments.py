"""Files attached to chat messages (ADR 0017): which files a message may carry, how it keeps them,
and how a bot's run reads them."""

import uuid
from typing import Any

import httpx

from src.services.run_service import _file_lines
from tests.conftest import sign_up


async def _org(client: httpx.AsyncClient, email: str = "ali@acme.dev") -> str:
    me = await sign_up(client, email=email)
    return f"/api/v1/orgs/{me['organizations'][0]['id']}"


async def _upload(client: httpx.AsyncClient, org: str, name: str, *, bot_id: str | None = None) -> dict[str, Any]:
    data = {"botId": bot_id} if bot_id else {}
    response = await client.post(f"{org}/files", data=data, files={"file": (name, b"a,b\n1,2\n", "text/csv")})
    assert response.status_code == 201, response.text
    file: dict[str, Any] = response.json()
    return file


async def test_a_file_attached_in_a_dm_reaches_the_bot(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
    dm = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    file = await _upload(client, org, "q3.csv", bot_id=bot["id"])

    sent = await client.post(
        f"{org}/threads/{dm['id']}/messages", json={"text": "Sum this up", "attachments": [file["id"]]}
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["parts"] == [
        {"type": "text", "text": "Sum this up"},
        {
            "type": "file",
            "fileId": file["id"],
            "botId": bot["id"],
            "path": "q3.csv",
            "contentType": "text/csv",
            "sizeBytes": 8,
        },
    ]
    assert len(sent.json()["runIds"]) == 1

    # A file on its own is a message too.
    alone = await client.post(f"{org}/threads/{dm['id']}/messages", json={"attachments": [file["id"]]})
    assert alone.status_code == 201
    assert [part["type"] for part in alone.json()["parts"]] == ["file"]


async def test_an_empty_message_is_refused(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
    dm = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
    assert (await client.post(f"{org}/threads/{dm['id']}/messages", json={"text": "  "})).status_code == 422


async def test_a_group_only_takes_shared_files(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    scout = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
    group = (await client.post(f"{org}/threads/groups", json={"title": "Launch", "botIds": [scout["id"]]})).json()
    private = await _upload(client, org, "mine.csv", bot_id=scout["id"])
    shared = await _upload(client, org, "brief.csv")

    refused = await client.post(f"{org}/threads/{group['id']}/messages", json={"attachments": [private["id"]]})
    assert refused.status_code == 400
    assert "shared files" in refused.json()["detail"]
    ok = await client.post(f"{org}/threads/{group['id']}/messages", json={"attachments": [shared["id"]]})
    assert ok.status_code == 201


async def test_another_organizations_file_cant_be_attached(client: httpx.AsyncClient) -> None:
    org = await _org(client)
    theirs = await _upload(client, org, "secret.csv")
    mine = await _org(client, email="sara@globex.dev")
    bot = (await client.post(f"{mine}/bots", json={"name": "Scout"})).json()
    dm = (await client.post(f"{mine}/threads/dm", json={"botId": bot["id"]})).json()
    sent = await client.post(f"{mine}/threads/{dm['id']}/messages", json={"attachments": [theirs["id"]]})
    assert sent.status_code == 404


def test_a_run_reads_where_each_attached_file_is() -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    parts = [
        {"type": "text", "text": "Look"},
        {"type": "file", "botId": str(me), "path": "q3.csv", "contentType": "text/csv", "sizeBytes": 2048},
        {"type": "file", "botId": None, "path": "brief.pdf", "contentType": "application/pdf", "sizeBytes": 3_500_000},
        {"type": "file", "botId": str(other), "path": "x.txt", "contentType": "text/plain", "sizeBytes": 10},
    ]
    assert _file_lines(parts, me) == [
        '(attached file "q3.csv" (text/csv, 2 KB) in your folder: files.read)',
        '(attached file "brief.pdf" (application/pdf, 3.3 MB) in the shared folder: files.read with shared=true)',
        '(attached file "x.txt" (text/plain, 10 B) in another bot\'s folder)',
    ]

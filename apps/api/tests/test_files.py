"""Bots' files over HTTP (ADR 0017): the organization's storage, uploading, listing, opening and
deleting a bot's files, and who may do what. Storage is Local, in the tests' temporary folder."""

from pathlib import Path
from typing import Any

import httpx

from tests.conftest import TEST_SETTINGS, sign_up


async def _org_with_bot(client: httpx.AsyncClient, *, email: str = "ali@acme.dev") -> tuple[str, dict[str, Any]]:
    me = await sign_up(client, email=email)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Inbox Manager"})).json()
    return org, bot


async def _upload(
    client: httpx.AsyncClient, org: str, *, bot_id: str | None, name: str, data: bytes, path: str | None = None
) -> httpx.Response:
    form = {key: value for key, value in (("botId", bot_id), ("path", path)) if value is not None}
    return await client.post(f"{org}/files", data=form, files={"file": (name, data, "text/plain")})


async def test_storage_is_local_until_chosen(client: httpx.AsyncClient) -> None:
    org, _ = await _org_with_bot(client)
    storage = (await client.get(f"{org}/storage")).json()
    assert (storage["provider"], storage["localAvailable"], storage["s3"]) == ("local", True, None)


async def test_a_member_gives_a_bot_a_file_and_it_lands_in_the_bots_folder(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)

    saved = await _upload(client, org, bot_id=bot["id"], name="march.csv", data=b"a,b\n1,2\n", path="reports/march.csv")
    assert saved.status_code == 201, saved.text
    file = saved.json()
    assert (file["path"], file["folder"], file["sizeBytes"], file["available"]) == (
        "reports/march.csv",
        "botdesk/inbox-manager",
        8,
        True,
    )

    listed = (await client.get(f"{org}/files", params={"botId": bot["id"]})).json()
    assert [f["path"] for f in listed] == ["reports/march.csv"]
    opened = await client.get(f"{org}/files/{file['id']}/content")
    assert opened.content == b"a,b\n1,2\n"
    assert opened.headers["x-content-type-options"] == "nosniff"

    # On the server: one folder per organization, `botdesk/`, one folder per bot.
    org_id = org.rsplit("/", 1)[1]
    on_disk = Path(TEST_SETTINGS.files_dir) / org_id / "botdesk" / "inbox-manager" / "reports" / "march.csv"
    assert on_disk.read_bytes() == b"a,b\n1,2\n"


async def test_saving_the_same_path_replaces_the_file(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    first = (await _upload(client, org, bot_id=bot["id"], name="notes.txt", data=b"one")).json()
    second = (await _upload(client, org, bot_id=bot["id"], name="notes.txt", data=b"two two")).json()
    assert second["id"] == first["id"]
    assert (await client.get(f"{org}/files/{first['id']}/content")).content == b"two two"


async def test_shared_files_have_their_own_folder(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    shared = (await _upload(client, org, bot_id=None, name="brand.md", data=b"# Brand")).json()
    assert shared["folder"] == "botdesk/_shared"
    assert [f["path"] for f in (await client.get(f"{org}/files")).json()] == ["brand.md"]
    assert (await client.get(f"{org}/files", params={"botId": bot["id"]})).json() == []


async def test_paths_that_leave_the_folder_are_refused(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    for path in ("../other-bot/x.txt", "/etc/passwd", "a//b.txt", "a\\b.txt", " "):
        response = await _upload(client, org, bot_id=bot["id"], name="x.txt", data=b"x", path=path)
        assert response.status_code == 400, path


async def test_deleting_a_file(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    file = (await _upload(client, org, bot_id=bot["id"], name="old.txt", data=b"x")).json()
    assert (await client.delete(f"{org}/files/{file['id']}")).status_code == 204
    assert (await client.get(f"{org}/files", params={"botId": bot["id"]})).json() == []
    assert (await client.get(f"{org}/files/{file['id']}/content")).status_code == 404


async def test_files_are_private_to_their_organization(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    file = (await _upload(client, org, bot_id=bot["id"], name="secret.txt", data=b"x")).json()

    other_org, _ = await _org_with_bot(client, email="sara@globex.dev")  # now signed in as Sara
    assert (await client.get(f"{org}/files", params={"botId": bot["id"]})).status_code == 404
    assert (await client.get(f"{other_org}/files/{file['id']}/content")).status_code == 404
    assert (await _upload(client, other_org, bot_id=bot["id"], name="x.txt", data=b"x")).status_code == 404


async def test_files_over_the_size_limit_are_refused(client: httpx.AsyncClient) -> None:
    org, bot = await _org_with_bot(client)
    too_big = b"x" * (TEST_SETTINGS.file_max_mb * 1024 * 1024 + 1)
    response = await _upload(client, org, bot_id=bot["id"], name="big.bin", data=too_big)
    assert response.status_code == 400
    assert "25 MB" in response.json()["detail"]


async def test_s3_storage_on_a_private_address_is_refused(client: httpx.AsyncClient) -> None:
    org, _ = await _org_with_bot(client)
    body = {
        "provider": "s3",
        "s3": {
            "endpoint": "https://10.0.0.5:9000",
            "region": "us-east-1",
            "bucket": "files",
            "accessKeyId": "AKIAEXAMPLE0000",
            "secretAccessKey": "secret-example",
        },
    }
    response = await client.put(f"{org}/storage", json=body)
    assert response.status_code == 400
    assert "private network" in response.json()["detail"]
    assert (await client.get(f"{org}/storage")).json()["provider"] == "local"


async def test_s3_storage_needs_its_fields(client: httpx.AsyncClient) -> None:
    org, _ = await _org_with_bot(client)
    response = await client.put(f"{org}/storage", json={"provider": "s3", "s3": {"bucket": "files"}})
    assert response.status_code == 422

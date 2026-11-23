"""Cloudinary storage (ADR 0017 step 5) against a fake Cloudinary that checks every signature, and
the signature itself against Cloudinary's documented examples."""

from urllib.parse import parse_qsl

import httpx
import pytest

from src.storage.base import StorageError
from src.storage.cloudinary import CloudinaryStorage, kind_of, sign
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

SECRET = "abcd"


def test_signatures_match_cloudinarys_examples() -> None:
    assert sign({"timestamp": "1315060510"}, SECRET) == "a21ad0f63beb4de2e5575204b79ab90bffb02c10"
    signed = {"timestamp": "1315060510", "public_id": "sample_image", "eager": "w_400,h_300,c_pad|w_260,h_200,c_crop"}
    assert sign(signed, SECRET) == "bfd09f95f331f558cbd1320e67aa8d488770583e"


def test_images_and_videos_drop_their_extension_other_files_keep_it() -> None:
    assert kind_of("botdesk/scout/shot.png") == ("image", "botdesk/scout/shot", "png")
    assert kind_of("botdesk/scout/demo.mp4") == ("video", "botdesk/scout/demo", "mp4")
    assert kind_of("botdesk/scout/notes.csv") == ("raw", "botdesk/scout/notes.csv", "")
    assert kind_of("botdesk/scout/README") == ("raw", "botdesk/scout/README", "")


class FakeCloudinary:
    def __init__(self) -> None:
        self.assets: dict[tuple[str, str], bytes] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "res.cloudinary.com":
            return httpx.Response(200, content=self.assets[("raw", request.url.path.split("/", 2)[2])])
        _, _, cloud, resource, action = request.url.path.split("/")
        if request.method == "GET":
            fields = dict(request.url.params)
        elif action == "upload":
            fields = _form_fields(request)
        else:
            fields = dict(parse_qsl(request.content.decode()))
        given = fields.pop("signature")
        fields.pop("api_key")
        if cloud != "acme" or given != sign(fields, SECRET):
            return httpx.Response(401, json={"error": {"message": "Invalid Signature"}})
        assert fields["type"] == "private"
        key = (resource, fields["public_id"])
        if action == "upload":
            self.assets[key] = _form_file(request)
            return httpx.Response(200, json={"public_id": fields["public_id"]})
        if action == "destroy":
            return httpx.Response(200, json={"result": "ok" if self.assets.pop(key, None) is not None else "not found"})
        if key not in self.assets:
            return httpx.Response(404, json={"error": {"message": "Resource not found"}})
        if resource == "raw":  # hand raw downloads over to the delivery network, as a redirect
            return httpx.Response(302, headers={"location": f"https://res.cloudinary.com/acme/{fields['public_id']}"})
        return httpx.Response(200, content=self.assets[key])


def _form_fields(request: httpx.Request) -> dict[str, str]:
    body = request.read().decode("latin-1")
    fields: dict[str, str] = {}
    for part in body.split("--")[1:]:
        if 'name="' in part and "filename=" not in part:
            name = part.split('name="', 1)[1].split('"', 1)[0]
            fields[name] = part.split("\r\n\r\n", 1)[1].rsplit("\r\n", 1)[0]
    return fields


def _form_file(request: httpx.Request) -> bytes:
    body = request.read()
    start = body.index(b"filename=")
    content = body[body.index(b"\r\n\r\n", start) + 4 :]
    return content[: content.rindex(b"\r\n--")]


def _storage(fake: FakeCloudinary, secret: str = SECRET) -> CloudinaryStorage:
    return CloudinaryStorage("acme", "key-123", secret, transport=httpx.MockTransport(fake.handle))


async def test_files_round_trip_as_private_assets() -> None:
    fake = FakeCloudinary()
    storage = _storage(fake)
    await storage.check()
    await storage.put("botdesk/scout/shot.png", b"\x89PNG", content_type="image/png")
    await storage.put("botdesk/scout/notes.csv", b"a,b", content_type="text/csv")
    assert set(fake.assets) == {("image", "botdesk/scout/shot"), ("raw", "botdesk/scout/notes.csv")}
    assert await storage.get("botdesk/scout/shot.png") == b"\x89PNG"
    assert await storage.get("botdesk/scout/notes.csv") == b"a,b"  # through the delivery redirect
    await storage.delete("botdesk/scout/notes.csv")
    await storage.delete("botdesk/scout/notes.csv")  # already gone: fine
    with pytest.raises(StorageError, match="isn't there"):
        await storage.get("botdesk/scout/notes.csv")


async def test_wrong_keys_are_refused() -> None:
    with pytest.raises(StorageError, match="refused the keys"):
        await _storage(FakeCloudinary(), secret="wrong").check()


async def test_a_download_redirect_elsewhere_is_not_followed() -> None:
    def elsewhere(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    storage = CloudinaryStorage("acme", "k", SECRET, transport=httpx.MockTransport(elsewhere))
    with pytest.raises(StorageError, match="doesn't follow"):
        await storage.get("botdesk/scout/notes.csv")


async def test_an_admin_chooses_cloudinary_and_the_folders_are_laid_out(providers: FakeProviders) -> None:
    fake = FakeCloudinary()
    providers.answer("api.cloudinary.com", handler=fake.handle)
    providers.answer("res.cloudinary.com", handler=fake.handle)  # where downloads are handed over
    async with api_client(TEST_SETTINGS, providers) as (_, client):
        me = await sign_up(client)
        org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
        await client.post(f"{org}/bots", json={"name": "Scout"})
        body = {
            "provider": "cloudinary",
            "cloudinary": {"cloudName": "acme", "apiKey": "key-1234", "apiSecret": SECRET},
        }
        chosen = await client.put(f"{org}/storage", json=body)
        assert chosen.status_code == 200, chosen.text
        assert (chosen.json()["provider"], chosen.json()["cloudinary"]) == (
            "cloudinary",
            {"cloudName": "acme", "apiKeyHint": "1234"},
        )
        assert {public_id for _, public_id in fake.assets} == {
            "botdesk/README.txt",
            "botdesk/scout/README.txt",
            "botdesk/_shared/README.txt",
        }
        wrong = {"provider": "cloudinary", "cloudinary": {"cloudName": "acme", "apiKey": "k-99", "apiSecret": "nope"}}
        refused = await client.put(f"{org}/storage", json=wrong)
        assert refused.status_code == 400 and "refused the keys" in refused.json()["detail"]

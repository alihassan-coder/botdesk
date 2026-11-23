"""Cloudinary storage (ADR 0017 step 5): best for images and screenshots; other files are kept as
Cloudinary "raw" files (10 MB each on its free plan).

Every file is uploaded as `type=private`, so nobody can open it from a guessed address: BotDesk
reads it back through the signed `download` call. Calls are signed as Cloudinary documents
(`sign`: the parameters sorted, joined with `&`, the API secret appended, SHA-1) and go only to
`api.cloudinary.com`; a download may redirect, but only to another `cloudinary.com` address.

Cloudinary sorts files into images, videos and raw files, and names images and videos without
their extension. The kind comes from the key's extension, the same way for every call, so a
file is always found where it was put.
"""

import hashlib
import mimetypes
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from src.storage.base import StorageError, check_key, round_trip

API = "https://api.cloudinary.com/v1_1"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def sign(params: dict[str, str], api_secret: str) -> str:
    """Cloudinary's signature: `a=1&b=2` (sorted by name, empty values left out) + the secret, SHA-1."""
    joined = "&".join(f"{name}={value}" for name, value in sorted(params.items()) if value != "")
    return hashlib.sha1(f"{joined}{api_secret}".encode(), usedforsecurity=False).hexdigest()


def kind_of(key: str) -> tuple[str, str, str]:
    """(resource type, public id, format): `botdesk/x/shot.png` → ("image", "botdesk/x/shot", "png");
    `botdesk/x/notes.csv` → ("raw", "botdesk/x/notes.csv", "")."""
    guessed, _ = mimetypes.guess_type(key)
    stem, dot, extension = key.rpartition(".")
    if guessed and guessed.startswith("image/") and dot and "/" not in extension:
        return "image", stem, extension.lower()
    if guessed and guessed.startswith(("video/", "audio/")) and dot and "/" not in extension:
        return "video", stem, extension.lower()
    return "raw", key, ""


class CloudinaryStorage:
    def __init__(
        self, cloud_name: str, api_key: str, api_secret: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.cloud_name = cloud_name
        self._api_key = api_key
        self._api_secret = api_secret
        self._transport = transport

    def __repr__(self) -> str:
        return f"CloudinaryStorage({self.cloud_name})"  # never the keys

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        resource, public_id, _ = kind_of(check_key(key))
        fields = self._signed({"public_id": public_id, "type": "private", "overwrite": "true", "invalidate": "true"})
        name = key.rsplit("/", 1)[-1]
        await self._send("POST", resource, "upload", data=fields, files={"file": (name, data, content_type)})

    async def get(self, key: str) -> bytes:
        resource, public_id, extension = kind_of(check_key(key))
        params = self._signed({"public_id": public_id, "format": extension, "type": "private"})
        return (await self._send("GET", resource, "download", params=params)).content

    async def delete(self, key: str) -> None:
        resource, public_id, _ = kind_of(check_key(key))
        fields = self._signed({"public_id": public_id, "type": "private", "invalidate": "true"})
        await self._send("POST", resource, "destroy", data=fields)

    async def check(self) -> None:
        await round_trip(self)

    def _signed(self, params: dict[str, str]) -> dict[str, str]:
        params = {name: value for name, value in params.items() if value != ""}
        params["timestamp"] = str(int(time.time()))
        return {**params, "api_key": self._api_key, "signature": sign(params, self._api_secret)}

    async def _send(self, method: str, resource: str, action: str, **request: Any) -> httpx.Response:
        url = f"{API}/{self.cloud_name}/{resource}/{action}"
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT, follow_redirects=False) as client:
                response = await client.request(method, url, **request)
                if response.is_redirect:  # a download handed over to Cloudinary's delivery network
                    location = response.headers.get("location", "")
                    host = urlsplit(location).hostname or ""
                    if urlsplit(location).scheme != "https" or not (
                        host == "cloudinary.com" or host.endswith(".cloudinary.com")
                    ):
                        raise StorageError("Cloudinary sent the file somewhere BotDesk doesn't follow.")
                    response = await client.get(location)
        except httpx.HTTPError:
            raise StorageError("BotDesk couldn't reach Cloudinary. Try again in a moment.") from None
        if response.is_success:
            if action == "destroy" and _result(response) not in ("ok", "not found"):
                raise StorageError("Cloudinary didn't delete the file.")
            return response
        raise self._explain(response)

    def _explain(self, response: httpx.Response) -> StorageError:
        if response.status_code == 404:
            return StorageError("That file isn't there any more.")
        if response.status_code in (401, 403):
            return StorageError(f"Cloudinary refused the keys for {self.cloud_name}. Check the API key and secret.")
        message = _error_message(response)
        return StorageError(
            f"Cloudinary said: {message}" if message else f"Cloudinary answered {response.status_code}."
        )


def _result(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("result", "")) if isinstance(body, dict) else ""


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return str(error.get("message", ""))[:200] if isinstance(error, dict) else ""

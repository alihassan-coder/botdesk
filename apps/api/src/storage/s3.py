"""S3-compatible storage: AWS S3, Cloudflare R2, Backblaze B2, Tigris, Wasabi, DigitalOcean Spaces,
Supabase Storage, Google Cloud Storage (HMAC keys), MinIO and Garage.

Requests go through BotDesk's own guarded HTTP client (`core/url_guard.GuardedTransport`), as
model and MCP servers do: the endpoint's address is checked and pinned for each connection
(public only, unless ALLOW_PRIVATE_STORAGE_URLS), and redirects are never followed, so an
endpoint can't send BotDesk's requests on to the server's own network. Requests are signed with
AWS Signature Version 4 (`sign`), path-style (`{endpoint}/{bucket}/{key}`), which every service
above accepts. Nothing is read from the environment: no `AWS_*` variable of the server's can
reach an organization's storage.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from src.core.url_guard import GuardedTransport, UnsafeUrl
from src.storage.base import StorageError, check_key, round_trip

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@dataclass(frozen=True)
class S3Location:
    """Where the files go. `endpoint` is empty for AWS itself (then the region's endpoint is used);
    `prefix` is an optional folder inside the bucket that `botdesk/` goes under."""

    bucket: str
    region: str
    endpoint: str = ""
    prefix: str = ""

    @property
    def address(self) -> str:
        return self.endpoint or f"https://s3.{self.region}.amazonaws.com"

    def describe(self) -> str:
        """What people see: `r2.example.com/bucket/prefix`. Also tells files' storage apart."""
        host = self.address.split("://", 1)[-1]
        return "/".join(part for part in (host, self.bucket, self.prefix) if part)

    def url(self, key: str) -> str:
        path = "/".join(part for part in (self.bucket, self.prefix, key) if part)
        return f"{self.address}/{quote(path, safe='/-_.~')}"


class S3Storage:
    def __init__(
        self,
        location: S3Location,
        *,
        access_key_id: str,
        secret_access_key: str,
        allow_private: bool,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.location = location
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._allow_private = allow_private
        self._transport = transport  # tests answer requests themselves

    def __repr__(self) -> str:
        return f"S3Storage({self.location.describe()})"  # never the keys

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        await self._send("PUT", key, data, {"content-type": content_type})

    async def get(self, key: str) -> bytes:
        return (await self._send("GET", key)).content

    async def delete(self, key: str) -> None:
        await self._send("DELETE", key, missing_ok=True)

    async def check(self) -> None:
        await round_trip(self)

    async def _send(
        self, method: str, key: str, body: bytes = b"", extra: dict[str, str] | None = None, *, missing_ok: bool = False
    ) -> httpx.Response:
        url = self.location.url(check_key(key))
        headers = sign(
            method,
            url,
            body,
            access_key_id=self._access_key_id,
            secret_access_key=self._secret_access_key,
            region=self.location.region,
            now=datetime.now(UTC),
        )
        transport = self._transport or GuardedTransport(allow_private=self._allow_private)
        try:
            async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT, follow_redirects=False) as client:
                response = await client.request(method, url, content=body or None, headers={**headers, **(extra or {})})
        except UnsafeUrl as error:
            raise StorageError(error.message) from None
        except httpx.HTTPError:
            raise StorageError(f"BotDesk couldn't reach {self.location.describe()}. Check the address.") from None
        if response.is_success or (missing_ok and response.status_code == 404):
            return response
        raise self._explain(response)

    def _explain(self, response: httpx.Response) -> StorageError:
        where, text = self.location.describe(), response.text
        if response.status_code == 404:
            if "NoSuchBucket" in text:
                return StorageError(f"There's no bucket {self.location.bucket!r} at {where}. Check the bucket name.")
            return StorageError("That file isn't there any more.")
        if response.status_code in (401, 403):
            return StorageError(
                f"{where} refused the keys. Check the access key and secret, "
                "and that they may read and write this bucket."
            )
        if response.is_redirect or "AuthorizationHeaderMalformed" in text or "PermanentRedirect" in text:
            return StorageError(f"{where} says the bucket is in another region. Check the region.")
        return StorageError(f"BotDesk couldn't use {where} (it answered {response.status_code}).")


def sign(
    method: str,
    url: str,
    body: bytes,
    *,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    now: datetime,
    also_sign: dict[str, str] | None = None,
) -> dict[str, str]:
    """The headers that sign this request with AWS Signature Version 4 (`host`, `x-amz-date`,
    `x-amz-content-sha256`, `authorization`, and `also_sign`'s), for the "s3" service."""
    parts = httpx.URL(url)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    payload = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
    host = parts.netloc.decode()
    signed = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": amz_date}
    signed |= {name.lower(): value.strip() for name, value in (also_sign or {}).items()}
    names = ";".join(sorted(signed))
    canonical = "\n".join(
        [
            method,
            parts.raw_path.decode().split("?", 1)[0] or "/",
            _canonical_query(parts.query.decode()),
            "".join(f"{name}:{signed[name]}\n" for name in sorted(signed)),
            names,
            payload,
        ]
    )
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    signing_key = _hmac(f"AWS4{secret_access_key}".encode(), day)
    for part in (region, "s3", "aws4_request"):
        signing_key = _hmac(signing_key, part)
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = f"AWS4-HMAC-SHA256 Credential={access_key_id}/{scope}, SignedHeaders={names}, Signature={signature}"
    return {**signed, "authorization": authorization}


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def _canonical_query(query: str) -> str:
    if not query:
        return ""
    pairs = sorted(tuple(pair.split("=", 1)) if "=" in pair else (pair, "") for pair in query.split("&"))
    return "&".join(f"{name}={value}" for name, value in pairs)

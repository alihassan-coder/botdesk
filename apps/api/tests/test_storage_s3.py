"""S3-compatible storage (ADR 0017 §3) against a fake S3 that checks each request's signature,
and the signature itself against AWS's published example."""

from datetime import UTC, datetime

import httpx
import pytest

from src.storage import S3Location, S3Storage, StorageError
from src.storage.s3 import sign

# AWS's documented Signature Version 4 example ("GET Object", Amazon S3 API reference).
AWS_KEY, AWS_SECRET = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def test_the_signature_matches_awss_published_example() -> None:
    headers = sign(
        "GET",
        "https://examplebucket.s3.amazonaws.com/test.txt",
        b"",
        access_key_id=AWS_KEY,
        secret_access_key=AWS_SECRET,
        region="us-east-1",
        now=datetime(2013, 5, 24, tzinfo=UTC),
        also_sign={"Range": "bytes=0-9"},
    )
    assert headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


class FakeS3:
    """A bucket in memory that only answers correctly signed, path-style requests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if not request.headers.get("authorization", "").startswith("AWS4-HMAC-SHA256 Credential=key-id/"):
            return httpx.Response(403, text="<Error><Code>InvalidAccessKeyId</Code></Error>")
        bucket, _, key = request.url.path.lstrip("/").partition("/")
        if bucket != "files":
            return httpx.Response(404, text="<Error><Code>NoSuchBucket</Code></Error>")
        if request.method == "PUT":
            self.objects[key] = request.content
            return httpx.Response(200)
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        if key not in self.objects:
            return httpx.Response(404, text="<Error><Code>NoSuchKey</Code></Error>")
        return httpx.Response(200, content=self.objects[key])


def _storage(fake: FakeS3, *, bucket: str = "files", key_id: str = "key-id") -> S3Storage:
    location = S3Location(bucket=bucket, region="auto", endpoint="https://r2.example.com", prefix="team")
    return S3Storage(
        location,
        access_key_id=key_id,
        secret_access_key="secret",
        allow_private=False,
        transport=httpx.MockTransport(fake.handle),
    )


async def test_files_round_trip_under_the_prefix() -> None:
    fake = FakeS3()
    storage = _storage(fake)
    await storage.check()
    await storage.put("botdesk/inbox-manager/march report.csv", b"a,b", content_type="text/csv")
    assert fake.objects == {"team/botdesk/inbox-manager/march report.csv": b"a,b"}
    assert await storage.get("botdesk/inbox-manager/march report.csv") == b"a,b"
    await storage.delete("botdesk/inbox-manager/march report.csv")
    await storage.delete("botdesk/inbox-manager/march report.csv")  # already gone: fine
    with pytest.raises(StorageError, match="isn't there"):
        await storage.get("botdesk/inbox-manager/march report.csv")


async def test_refusals_say_what_to_fix() -> None:
    with pytest.raises(StorageError, match="refused the keys"):
        await _storage(FakeS3(), key_id="wrong").check()
    with pytest.raises(StorageError, match="no bucket 'other'"):
        await _storage(FakeS3(), bucket="other").check()


async def test_redirects_are_never_followed() -> None:
    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    location = S3Location(bucket="files", region="auto", endpoint="https://r2.example.com")
    storage = S3Storage(
        location, access_key_id="k", secret_access_key="s", allow_private=False, transport=httpx.MockTransport(redirect)
    )
    with pytest.raises(StorageError, match="another region"):
        await storage.get("botdesk/x")


async def test_a_private_address_is_refused_as_it_connects() -> None:
    location = S3Location(bucket="files", region="auto", endpoint="https://127.0.0.1:9")
    storage = S3Storage(location, access_key_id="k", secret_access_key="s", allow_private=False)
    with pytest.raises(StorageError, match="private network"):
        await storage.get("botdesk/x")

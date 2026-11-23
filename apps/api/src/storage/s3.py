"""S3-compatible storage through obstore (MIT): AWS S3, Cloudflare R2, Backblaze B2, Tigris, Wasabi,
DigitalOcean Spaces, Supabase Storage, Google Cloud Storage (HMAC keys), MinIO and Garage.

obstore fills anything it isn't given from `AWS_*` environment variables. That would hand the
server operator's own AWS settings to an organization's storage, so every value it needs is
always passed explicitly: the endpoint (AWS's own when none is given), region, bucket and keys.
"""

from dataclasses import dataclass
from datetime import timedelta

from obstore import delete_async, get_async, put_async
from obstore.exceptions import BaseError, NotFoundError, PermissionDeniedError, UnauthenticatedError
from obstore.store import S3Store

from src.storage.base import StorageError, check_key, round_trip

REQUEST_TIMEOUT = "30s"
CONNECT_TIMEOUT = "10s"
RETRIES = 2
RETRY_WINDOW = timedelta(seconds=20)


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


class S3Storage:
    def __init__(self, location: S3Location, *, access_key_id: str, secret_access_key: str, allow_http: bool) -> None:
        self.location = location
        self._store = S3Store(
            location.bucket,
            prefix=location.prefix or None,
            endpoint=location.address,
            region=location.region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            client_options={"timeout": REQUEST_TIMEOUT, "connect_timeout": CONNECT_TIMEOUT, "allow_http": allow_http},
            retry_config={"max_retries": RETRIES, "retry_timeout": RETRY_WINDOW},
        )

    def __repr__(self) -> str:
        return f"S3Storage({self.location.describe()})"  # never the keys

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            await put_async(self._store, check_key(key), data, attributes={"Content-Type": content_type})
        except BaseError as error:
            raise self._explain(error) from None

    async def get(self, key: str) -> bytes:
        try:
            result = await get_async(self._store, check_key(key))
            return bytes(await result.bytes_async())
        except BaseError as error:
            raise self._explain(error) from None

    async def delete(self, key: str) -> None:
        try:
            await delete_async(self._store, check_key(key))
        except NotFoundError:
            return
        except BaseError as error:
            raise self._explain(error) from None

    async def check(self) -> None:
        await round_trip(self)

    def _explain(self, error: BaseError) -> StorageError:
        where = self.location.describe()
        if isinstance(error, NotFoundError):
            return StorageError("That file isn't there any more.")
        if isinstance(error, PermissionDeniedError | UnauthenticatedError):
            return StorageError(
                f"{where} refused the keys. Check the access key and secret, "
                "and that they may read and write this bucket."
            )
        return StorageError(f"BotDesk couldn't use {where}. Check the address, region and bucket name.")

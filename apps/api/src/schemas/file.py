"""Bots' files and the organization's storage (ADR 0017)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from src.schemas.common import ApiModel

StorageProviderId = Literal["local", "s3"]


class S3In(ApiModel):
    """An S3-compatible bucket. `endpoint` is empty for AWS itself. `secretAccessKey` may be left
    out when changing other fields of storage that is already S3: the saved one is kept."""

    endpoint: str = Field(default="", max_length=300)
    region: str = Field(min_length=1, max_length=60)
    bucket: str = Field(min_length=3, max_length=63)
    prefix: str = Field(default="", max_length=200)
    access_key_id: str = Field(min_length=4, max_length=200)
    secret_access_key: str | None = Field(default=None, min_length=4, max_length=400)

    @field_validator("endpoint", "region", "bucket", "access_key_id")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("prefix")
    @classmethod
    def _folder(cls, value: str) -> str:
        return value.strip().strip("/")


class StorageIn(ApiModel):
    provider: StorageProviderId
    s3: S3In | None = None


class S3Out(ApiModel):
    endpoint: str
    region: str
    bucket: str
    prefix: str
    access_key_hint: str  # the access key's last 4 characters


class StorageOut(ApiModel):
    provider: StorageProviderId
    s3: S3Out | None
    # Whether this server lets organizations keep files on its own disk (LOCAL_FILES).
    local_available: bool
    checked_at: datetime | None


class FileOut(ApiModel):
    id: uuid.UUID
    bot_id: uuid.UUID | None
    path: str  # inside the folder: "reports/march.csv"
    folder: str  # "botdesk/inbox-manager", or "botdesk/shared"
    content_type: str
    size_bytes: int
    # False when it was saved to storage the organization no longer uses.
    available: bool
    created_at: datetime
    updated_at: datetime

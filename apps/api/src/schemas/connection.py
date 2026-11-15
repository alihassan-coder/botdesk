"""Connections as the API shows them (ADR 0010). No response ever carries a credential."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, SecretStr, field_validator

from src.schemas.common import ApiModel

OwnerKindIn = Literal["member", "bot", "org"]


class ApiKeyConnectionIn(ApiModel):
    """Connect an account by pasting its API key. `botId` is required for a bot-owned connection."""

    connector_id: str = Field(min_length=1, max_length=80)
    owner_kind: OwnerKindIn = "member"
    bot_id: uuid.UUID | None = None
    # What people will see ("Linear (Acme workspace)"). Empty: the connector's name. Connecting
    # again with the same label replaces the key of that connection.
    account_label: str = Field(default="", max_length=200)
    # SecretStr: never in a repr, a log line or a validation error.
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def one_line(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if not key:
            raise ValueError("Paste the API key.")
        if len(key) > 4096 or any(c in key for c in "\r\n\0"):
            raise ValueError("That doesn't look like an API key.")  # header injection, or a paste gone wrong
        return SecretStr(key)


class ConnectionOut(ApiModel):
    id: uuid.UUID
    connector_id: str
    owner_kind: str
    owner_user_id: uuid.UUID | None
    owner_bot_id: uuid.UUID | None
    auth_type: str
    account_label: str
    scopes: list[str]
    status: str
    status_reason: str | None
    created_at: datetime
    last_used_at: datetime | None
    created_by: uuid.UUID | None

"""MCP servers as the API shows them (ADR 0012). No response ever carries the header key's value."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from src.schemas.common import ApiModel

HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class McpServerIn(ApiModel):
    """Add a server: a name, its https address and, optionally, an API key sent in a header
    (`apiKeyHeader: "Authorization"`, `apiKeyValue: "Bearer …"`, or `X-API-Key`)."""

    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=2000)
    api_key_header: str | None = Field(default=None, max_length=64)
    api_key_value: SecretStr | None = None  # never in a repr, a log line or a validation error

    @field_validator("name")
    @classmethod
    def named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the server a name.")
        return value.strip()

    @field_validator("api_key_header")
    @classmethod
    def header_name(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not HEADER_NAME.match(value):
            raise ValueError("A header name is letters, digits and dashes, like X-API-Key.")
        return value

    @model_validator(mode="after")
    def both_halves(self) -> "McpServerIn":
        value = self.api_key_value.get_secret_value().strip() if self.api_key_value else ""
        if bool(self.api_key_header) != bool(value):
            raise ValueError("Give both the header name and the key, or neither.")
        if len(value) > 4096 or any(c in value for c in "\r\n\0"):
            raise ValueError("That doesn't look like an API key.")
        self.api_key_value = SecretStr(value) if value else None
        return self


class McpToolOut(ApiModel):
    name: str  # full name, as on approval cards: "mcp-1a2b3c4d.search_issues"
    server_name: str  # what the server calls it
    title: str | None
    description: str | None
    annotations: dict[str, Any]  # the server's own claims (readOnlyHint…): shown, never trusted


class McpServerOut(ApiModel):
    id: uuid.UUID
    plugin_id: str  # "mcp-1a2b3c4d": bind it in a bot's Tools like any plugin
    name: str
    url: str
    auth_kind: Literal["none", "header"]
    auth_header: str | None  # the header's name only
    status: Literal["active", "unreachable"]
    status_reason: str | None
    tools: list[McpToolOut]
    last_checked_at: datetime | None
    created_at: datetime
    created_by: uuid.UUID | None

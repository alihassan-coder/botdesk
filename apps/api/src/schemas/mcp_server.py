"""MCP servers as the API shows them (ADR 0012). No response ever carries the header key's value,
an OAuth token or a client secret."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from src.schemas.common import ApiModel

HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")


ReviewRisk = Literal["read", "write-internal", "write-external", "external-send", "destructive"]


class McpServerIn(ApiModel):
    """Add a server: a name, its https address and, optionally, an API key sent in a header
    (`apiKeyHeader: "Authorization"`, `apiKeyValue: "Bearer …"`, or `X-API-Key`), or OAuth sign-in
    (`signIn: true`, or found when the server answers 401) with an optional pre-registered client."""

    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=2000)
    api_key_header: str | None = Field(default=None, max_length=64)
    api_key_value: SecretStr | None = None  # never in a repr, a log line or a validation error
    sign_in: bool = False
    oauth_client_id: str | None = Field(default=None, max_length=500)
    oauth_client_secret: SecretStr | None = None

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
        client_id = (self.oauth_client_id or "").strip() or None
        secret = self.oauth_client_secret.get_secret_value().strip() if self.oauth_client_secret else ""
        if secret and not client_id:
            raise ValueError("Give the client ID with the client secret.")
        if len(secret) > 4096 or any(c in secret for c in "\r\n\0"):
            raise ValueError("That doesn't look like a client secret.")
        self.oauth_client_id = client_id
        self.oauth_client_secret = SecretStr(secret) if secret else None
        self.sign_in = self.sign_in or client_id is not None
        if self.sign_in and self.api_key_header:
            raise ValueError("Use an API key or sign-in, not both.")
        return self


class McpToolChoiceIn(ApiModel):
    """One tool on the review screen: offered to bots or not, and its risk (never below read)."""

    server_name: str = Field(min_length=1, max_length=500)
    enabled: bool
    risk: ReviewRisk


class McpToolsReviewIn(ApiModel):
    """The review screen's save. `toolsHash` is the server's `toolsHash` the admin looked at."""

    tools_hash: str = Field(max_length=64)
    tools: list[McpToolChoiceIn] = Field(max_length=200)


class McpToolBeforeOut(ApiModel):
    """What an admin approved, for a tool that has changed since."""

    title: str | None
    description: str | None
    input_schema: dict[str, Any] | None


class McpToolOut(ApiModel):
    name: str  # full name, as on approval cards: "mcp-1a2b3c4d.search_issues"
    server_name: str  # what the server calls it
    title: str | None
    description: str | None
    annotations: dict[str, Any]  # the server's own claims (readOnlyHint…): shown, never trusted
    input_schema: dict[str, Any]
    # approved: offered if enabled; changed / pending: waits for the review; removed: gone from the server
    state: Literal["approved", "changed", "pending", "removed"]
    enabled: bool  # "offer to bots"
    risk: ReviewRisk
    previous: McpToolBeforeOut | None  # for a changed tool: what was approved


class McpServerOut(ApiModel):
    id: uuid.UUID
    plugin_id: str  # "mcp-1a2b3c4d": bind it in a bot's Tools like any plugin
    name: str
    url: str
    auth_kind: Literal["none", "header", "oauth"]
    auth_header: str | None  # the header's name only
    status: Literal["active", "unreachable", "needs_sign_in", "needs_reconnect"]
    status_reason: str | None
    tools: list[McpToolOut]
    tools_hash: str  # send it back with the review, so a change in between isn't approved unseen
    tools_changed: int  # changed, new or removed tools waiting for the review ("Tools changed" badge)
    last_checked_at: datetime | None
    created_at: datetime
    created_by: uuid.UUID | None


class McpServerAddedOut(McpServerOut):
    authorize_url: str | None  # set when the server wants a sign-in: send the browser there


class McpSignInOut(ApiModel):
    authorize_url: str

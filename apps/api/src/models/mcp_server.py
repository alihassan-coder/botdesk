import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow

McpServerStatus = Literal["active", "unreachable"]


class McpServer(IdMixin, CreatedAtMixin, Base):
    """A remote MCP server an owner or admin added to the organization (ADR 0012, slice 7.2).

    It is the organization's plugin `mcp-<short_id>`: bots get its tools through bindings like any
    other plugin. `tools` is the tool snapshot taken when it was added or last refreshed (each
    tool's server name, local name, description, schemas and hash); only those definitions are
    offered to bots, and a call whose tool no longer matches its hash is refused.

    Header auth (`auth_header` + the value) is sealed by the credential vault in
    `encrypted_auth`; it never leaves the server."""

    __tablename__ = "mcp_servers"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    short_id: Mapped[str] = mapped_column(String(16), unique=True)  # the plugin id is "mcp-<short_id>"
    name: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(2000))
    auth_kind: Mapped[str] = mapped_column(String(20), default="none")  # "none" | "header"
    auth_header: Mapped[str | None] = mapped_column(String(64))  # the header's name, not a secret
    encrypted_auth: Mapped[str | None] = mapped_column(Text)  # the header's value, sealed
    status: Mapped[str] = mapped_column(String(20), default="active")  # McpServerStatus
    status_reason: Mapped[str | None] = mapped_column(Text)
    tools: Mapped[list[dict[str, Any]]] = mapped_column(default=list)  # the tool snapshot
    tools_hash: Mapped[str] = mapped_column(String(64))
    last_checked_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    @property
    def plugin_id(self) -> str:
        return f"mcp-{self.short_id}"

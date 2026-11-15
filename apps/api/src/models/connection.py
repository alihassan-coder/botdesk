import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow

OwnerKind = Literal["member", "bot", "org"]
AuthType = Literal["oauth2", "api_key"]
ConnectionStatus = Literal["active", "needs_reconnect", "revoked"]


class Connection(IdMixin, CreatedAtMixin, Base):
    """One authorised account on one connector (ADR 0010 §2): a member's, a bot's own, or the
    organization's shared one.

    The credential is a Fernet token in `encrypted_secret`, readable only through the credential
    vault (`services/credential_vault.py`) and only inside a tool call. Disconnecting nulls it
    and sets `revoked`; the row stays for the audit trail. Connecting the same account again
    (same connector, owner and `account_ref`) updates this row instead of adding one.
    """

    __tablename__ = "connections"
    __table_args__ = (
        CheckConstraint(
            "(owner_kind = 'member' AND owner_user_id IS NOT NULL AND owner_bot_id IS NULL)"
            " OR (owner_kind = 'bot' AND owner_bot_id IS NOT NULL AND owner_user_id IS NULL)"
            " OR (owner_kind = 'org' AND owner_user_id IS NULL AND owner_bot_id IS NULL)",
            name="owner",
        ),
        # One row per account per owner. The owner id is folded into one expression (the org's
        # own id for org-owned rows), because a unique index treats NULLs as all different.
        Index(
            "uq_connections_account",
            "org_id",
            "connector_id",
            "owner_kind",
            text("coalesce(owner_user_id, owner_bot_id, org_id)"),
            "account_ref",
            unique=True,
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    connector_id: Mapped[str] = mapped_column(String(80))  # the plugin id: "gmail", "mcp-<server id>"
    owner_kind: Mapped[str] = mapped_column(String(10))  # OwnerKind
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    owner_bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    auth_type: Mapped[str] = mapped_column(String(10))  # AuthType
    account_label: Mapped[str] = mapped_column(String(200))  # what people see: "ali@acme.dev"
    # The provider's stable id for the account (OAuth), or the label in lower case (API keys,
    # which can't name their account): connecting it again updates this row.
    account_ref: Mapped[str] = mapped_column(String(255))
    encrypted_secret: Mapped[str | None] = mapped_column(Text)  # null once disconnected
    # Scopes granted (from the token response, not what was asked for). Empty for API keys.
    scopes: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=list)
    access_expires_at: Mapped[datetime | None]  # null for API keys
    status: Mapped[str] = mapped_column(String(20), default="active")  # ConnectionStatus
    status_reason: Mapped[str | None] = mapped_column(Text)
    # Two runs must not refresh one token at once (ADR 0010 §6); used from OAuth (slice 5.3).
    refresh_lease_until: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]
    last_refreshed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditEntry(IdMixin, CreatedAtMixin, Base):
    """One line of the audit log (ADR 0010 §9): who did what to which connection, and when.

    Append-only: the app inserts rows and never updates or deletes them. `target_id` has no
    foreign key on purpose, so an entry outlives what it describes."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_org_id_created_at", "org_id", "created_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # "connection.created", "connection.reconnected", "connection.disconnected", ...
    action: Mapped[str] = mapped_column(String(60))
    target_kind: Mapped[str] = mapped_column(String(30))  # "connection"
    target_id: Mapped[uuid.UUID | None]
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)  # never a secret

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow


class ComputerProvider(IdMixin, CreatedAtMixin, Base):
    """The organization's **storage provider** (and, later, its **browser provider**): which
    service it chose in Settings → Computers, and its keys, sealed by the vault (ADR 0017 §2).

    One per organization and kind. No row means Local. `config` holds what isn't secret (bucket,
    region, endpoint, prefix); `encrypted_secret` holds the keys as one sealed JSON object, and
    people only ever see `secret_hint` (the access key's last 4 characters)."""

    __tablename__ = "computer_providers"
    __table_args__ = (UniqueConstraint("org_id", "kind", name="uq_computer_providers_org_id_kind"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))  # "storage" (later "browser")
    provider: Mapped[str] = mapped_column(String(40))  # "local" | "s3"
    config: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=dict)
    encrypted_secret: Mapped[str] = mapped_column(Text, default="")
    secret_hint: Mapped[str] = mapped_column(String(8), default="")
    checked_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

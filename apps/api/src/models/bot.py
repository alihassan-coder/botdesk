import uuid
from typing import Literal

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin

SecurityLevel = Literal["read-only", "ask-before-acting", "autonomous"]
AvatarColor = Literal["indigo", "violet", "sky", "emerald", "amber", "rose", "orange", "slate"]


class Bot(IdMixin, CreatedAtMixin, Base):
    """A bot on an organization's team. Its @handle is unique within the organization."""

    __tablename__ = "bots"
    __table_args__ = (UniqueConstraint("org_id", "handle", name="uq_bots_org_id_handle"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    handle: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    avatar_color: Mapped[str] = mapped_column(String(20), default="indigo")
    # "provider:model", e.g. "anthropic:claude-sonnet-5-5" or "custom-<id>:llama3.2:latest".
    # Empty = DEFAULT_MODEL_ID.
    model_id: Mapped[str] = mapped_column(String(200), default="")
    security_level: Mapped[str] = mapped_column(String(30), default="ask-before-acting")
    monthly_budget_usd: Mapped[int] = mapped_column(default=50)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

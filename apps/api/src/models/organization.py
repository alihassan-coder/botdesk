import uuid
from typing import Literal

from sqlalchemy import ForeignKey, String, sql, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin

Role = Literal["owner", "admin", "member"]


class Organization(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    # What all the organization's bots together may spend in a calendar month (UTC), in whole
    # dollars. None = no limit. Each bot also has its own budget.
    monthly_budget_usd: Mapped[int | None] = mapped_column(default=None)
    # The security level a new bot gets when whoever hires it doesn't pick one.
    default_security_level: Mapped[str] = mapped_column(
        String(30), default="ask-before-acting", server_default=text("'ask-before-acting'")
    )
    # The ceiling: no run in the organization acts above this level, whatever its bot's level
    # (ADR 0004: the strictest of org, bot and routine wins). "autonomous" = no ceiling.
    max_security_level: Mapped[str] = mapped_column(
        String(30), default="autonomous", server_default=text("'autonomous'")
    )
    # Chat history (ADR 0019): bots read a summary of messages older than what a run reads, and
    # messages older than `history_retention_days` are deleted every night (None = kept forever).
    history_summaries: Mapped[bool] = mapped_column(default=True, server_default=sql.true())
    history_retention_days: Mapped[int | None] = mapped_column(default=None)


class Membership(CreatedAtMixin, Base):
    """A user's place in an organization, and their role there."""

    __tablename__ = "memberships"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")

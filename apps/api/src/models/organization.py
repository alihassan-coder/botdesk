import uuid
from typing import Literal

from sqlalchemy import ForeignKey, String
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


class Membership(CreatedAtMixin, Base):
    """A user's place in an organization, and their role there."""

    __tablename__ = "memberships"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")

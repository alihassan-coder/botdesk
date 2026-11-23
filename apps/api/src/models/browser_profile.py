import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class BrowserProfile(IdMixin, CreatedAtMixin, Base):
    """A bot's **browser profile** at a cloud browser provider (ADR 0017 §5): what it remembers
    there, above all its sign-ins. `ref` is the provider's id for it (a Steel profile, a
    Browserbase context, a Kernel profile name). A Local profile is a folder, not a row.
    Forgetting sign-ins deletes the row, so the next browser starts with a fresh profile."""

    __tablename__ = "browser_profiles"
    __table_args__ = (UniqueConstraint("bot_id", "provider", name="uq_browser_profiles_bot_id_provider"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))  # "steel" | "browserbase" | "kernel"
    ref: Mapped[str] = mapped_column(String(200))

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow


class MemoryKey(IdMixin, CreatedAtMixin, Base):
    """The organization's **memory key**: a model provider's key used only for its bots' memory
    (reading, saving and searching memories), never for their replies. One per organization.
    Without one, memory uses the server's own key, if the operator set one up.

    Sealed by the vault like every key; people see `key_hint` (its last 4 characters)."""

    __tablename__ = "memory_keys"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    provider: Mapped[str] = mapped_column(String(20))  # "openai" | "gemini"
    encrypted_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(8))
    checked_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

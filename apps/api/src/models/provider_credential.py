import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class ProviderCredential(IdMixin, CreatedAtMixin, Base):
    """An organization's key for a model provider (a **model key**), encrypted at rest.

    One per built-in provider per organization; custom (OpenAI-compatible) servers may have
    several, told apart by their label and base URL. The key itself is only ever decrypted for
    the call that needs it; people see `key_hint` (its last 4 characters).
    """

    __tablename__ = "provider_credentials"
    __table_args__ = (
        Index(
            "uq_provider_credentials_org_id_builtin",
            "org_id",
            "provider",
            unique=True,
            postgresql_where=text("provider <> 'custom'"),
            sqlite_where=text("provider <> 'custom'"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # "anthropic", "openai", "gemini", "openrouter", "groq" or "custom".
    provider: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(80), default="")  # custom only: what people call it
    base_url: Mapped[str | None] = mapped_column(String(500))  # custom only
    # Fernet token (src/core/secrets.py). Empty for a custom server that takes no key.
    encrypted_key: Mapped[str] = mapped_column(Text, default="")
    key_hint: Mapped[str] = mapped_column(String(8), default="")
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | invalid, from the last check
    last_verified_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

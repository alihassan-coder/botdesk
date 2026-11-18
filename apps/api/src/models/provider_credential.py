import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class ProviderCredential(IdMixin, CreatedAtMixin, Base):
    """A key for a model provider (a **model key**), encrypted at rest: the organization's
    (`user_id` empty), or one member's own in that organization (`user_id` set).

    One per built-in provider per organization, and one per built-in provider per member there;
    custom (OpenAI-compatible) servers are organization keys only and may be several, told apart
    by their label and base URL. The key itself is only ever decrypted for the call that needs
    it; people see `key_hint` (its last 4 characters). A member's key serves only runs that
    member requested.
    """

    __tablename__ = "provider_credentials"
    __table_args__ = (
        Index(
            "uq_provider_credentials_org_id_builtin",
            "org_id",
            "provider",
            unique=True,
            postgresql_where=text("provider <> 'custom' AND user_id IS NULL"),
            sqlite_where=text("provider <> 'custom' AND user_id IS NULL"),
        ),
        Index(
            "uq_provider_credentials_org_id_user_id_provider",
            "org_id",
            "user_id",
            "provider",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
            sqlite_where=text("user_id IS NOT NULL"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # Set for a member's own key: whose it is. Empty for the organization's keys.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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

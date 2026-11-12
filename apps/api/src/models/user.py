import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class User(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # always lowercase
    name: Mapped[str] = mapped_column(String(120))
    handle: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Session(IdMixin, CreatedAtMixin, Base):
    """One signed-in browser or device. Holds a hash of the token, never the token."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime]


class PasswordResetToken(IdMixin, CreatedAtMixin, Base):
    """A password reset link. Like sessions, only the SHA-256 hash of the token is stored.
    Works once (`used_at`) and only until `expires_at`."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]

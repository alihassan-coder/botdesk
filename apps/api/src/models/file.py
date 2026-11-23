import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow


class File(IdMixin, CreatedAtMixin, Base):
    """A bot's file (ADR 0017 §3), or a shared one (`bot_id` empty): the list of record. The bytes
    live in the organization's storage at `storage_key` (`botdesk/<bot handle>/<path>`).

    `path` is what people and the bot use, inside the bot's folder (`reports/march.csv`); it is
    unique per bot, and per organization among shared files. `storage_key` stays put when the
    bot's handle changes, so its old files are still found. `storage` says which storage holds
    the bytes ("local", or "s3:<host>/<bucket>/<prefix>"): a file saved before the organization
    switched storage stays listed but can't be opened. Removing a bot removes its rows; the
    bytes stay in the organization's storage."""

    __tablename__ = "files"
    __table_args__ = (
        Index(
            "uq_files_org_id_bot_id_path",
            "org_id",
            "bot_id",
            "path",
            unique=True,
            postgresql_where=text("bot_id IS NOT NULL"),
            sqlite_where=text("bot_id IS NOT NULL"),
        ),
        Index(
            "uq_files_org_id_shared_path",
            "org_id",
            "path",
            unique=True,
            postgresql_where=text("bot_id IS NULL"),
            sqlite_where=text("bot_id IS NULL"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(600))
    storage: Mapped[str] = mapped_column(String(400))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    # Who saved it last: a bot's run, or a member (an upload).
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

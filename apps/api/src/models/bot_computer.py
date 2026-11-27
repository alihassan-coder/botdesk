import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class BotComputer(IdMixin, CreatedAtMixin, Base):
    """A bot's cloud computer (ADR 0020 §3): one per bot, at the organization's provider.

    Made on first use: whoever inserts the row (status `creating`, no `remote_id` yet) makes the
    computer at the provider; the unique `bot_id` decides who that is. `created_at` is when that
    creator claimed it, so a creator that crashed can be taken over later (with the same
    idempotency key). `started_at` is when it last started running (None while it
    isn't), for its usage; `last_used_at` is its last tool call, take-over or watcher, for the idle
    stop. When its bot is removed the row stays, without the bot, as `deleting` until the provider
    confirms the computer is deleted (the idle job tries again every minute).
    """

    __tablename__ = "bot_computers"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # None once its bot is removed: a tombstone (`deleting`) until Orgo confirms it's deleted.
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), unique=True)
    provider: Mapped[str] = mapped_column(String(40))  # "orgo"
    remote_id: Mapped[str] = mapped_column(String(200), default="")  # "" until the provider made it
    name: Mapped[str] = mapped_column(String(80))  # botdesk-<handle>
    # creating | starting | running | stopping | stopped | error | deleting (its bot was removed)
    status: Mapped[str] = mapped_column(String(20), default="creating")
    cpu: Mapped[float | None] = mapped_column(Float)
    ram: Mapped[int | None] = mapped_column()  # GB
    region: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime | None] = mapped_column()
    last_used_at: Mapped[datetime | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    # Making it at the provider: the idempotency key is botdesk-<id>-<attempt>, and a new attempt
    # (after a refusal, when nothing was made) gets a new key.
    attempt: Mapped[int] = mapped_column(default=1, server_default=text("1"))

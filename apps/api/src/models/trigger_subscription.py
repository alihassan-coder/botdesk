import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow


class TriggerSubscription(IdMixin, CreatedAtMixin, Base):
    """A bot reacting to something in another app (slice 6.3): this binding's plugin trigger is on
    ("React to new email" on the bot's Gmail). The row exists while it's on; switching it off
    deletes it, and removing the bot or its binding removes it too.

    The member who switched it on is the **subscriber**: each event is posted in their DM with the
    bot and starts a run that acts for them (the requester, ADR 0010). `cursor` is the plugin's
    position in the other app (a Gmail `historyId`), for `connection_id`'s account: when the
    binding moves to another account, polling starts again from "now". `seen` holds the newest
    event ids already handled, so none is handled twice. `problem` says why the last poll did
    nothing (needs reconnecting, Gmail said no); cleared by the next good poll."""

    __tablename__ = "trigger_subscriptions"
    __table_args__ = (UniqueConstraint("binding_id", "trigger", name="uq_trigger_subscriptions_binding_id_trigger"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    binding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bot_tools.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(String(80))  # the plugin's trigger name: "new_email"
    subscriber_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), index=True
    )
    cursor: Mapped[str | None] = mapped_column(String(200))
    seen: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=list)
    problem: Mapped[str | None] = mapped_column(Text)
    last_polled_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

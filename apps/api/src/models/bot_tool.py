import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow


class BotTool(IdMixin, CreatedAtMixin, Base):
    """A binding (slice 5.2): this bot may use this plugin, through this connection when the
    plugin needs an account. A bot's bindings are its Tools. One per bot and plugin (v1 has no
    per-tool switches). A plugin with no row here is off for the bot.

    Disconnecting a connection sets `connection_id` to NULL on its bindings: the plugin stays on,
    and its tools that need an account fail with "connect it first" until another is chosen."""

    __tablename__ = "bot_tools"
    __table_args__ = (UniqueConstraint("bot_id", "plugin_id", name="uq_bot_tools_bot_id_plugin_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # Queried by bot through the unique constraint's index (bot_id first).
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    plugin_id: Mapped[str] = mapped_column(String(80))
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), index=True
    )
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

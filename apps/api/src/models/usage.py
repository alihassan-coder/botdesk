import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, IdMixin, utcnow


class UsageRecord(IdMixin, Base):
    """One model call: its tokens and what it cost (agents-and-plugins.md §4.2).

    Written once per call, never changed. `cost_usd` is None when the price isn't known (a custom
    server, or a model missing from the price table): the tokens still count, the dollars don't.
    The bot and run are kept as None when they're deleted, so the organization's spend stays right.
    """

    __tablename__ = "usage_records"
    __table_args__ = (
        # Month-to-date sums and daily charts read by organization or by bot, over a time range.
        Index("ix_usage_records_org_id_created_at", "org_id", "created_at"),
        Index("ix_usage_records_bot_id_created_at", "bot_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="model")  # model; computer later
    provider: Mapped[str] = mapped_column(String(80))  # "anthropic", "openrouter", "custom-<id>"…
    model_id: Mapped[str] = mapped_column(String(200))  # "provider:model"
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin

ApprovalStatus = Literal["pending", "approved", "denied", "edited", "expired"]


class Approval(IdMixin, CreatedAtMixin, Base):
    """A run paused on a risky tool call, waiting for a person (ADR 0004 §3).

    Deciding is one conditional UPDATE (`status = 'pending'`), so two people clicking at once,
    or one double-click, can only decide it once. `edited` means approved with changed
    arguments, which are in `final_args`.
    """

    __tablename__ = "approvals"
    __table_args__ = (
        # The approvals inbox: an organization's pending approvals, newest first.
        Index("ix_approvals_org_id_status_created_at", "org_id", "status", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    # One approval per tool call: preparing the call again finds this row.
    tool_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_executions.id", ondelete="CASCADE"), unique=True
    )
    tool_name: Mapped[str] = mapped_column(String(120))
    risk: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))  # "Send an email"
    summary: Mapped[str] = mapped_column(Text)  # "Send an email to sara@acme.dev: Launch"
    reason: Mapped[str] = mapped_column(Text)  # the policy's decision trace
    tainted: Mapped[bool] = mapped_column(Boolean, default=False)  # the run had read outside text
    args: Mapped[dict[str, Any]]  # what the bot asked to do
    final_args: Mapped[dict[str, Any] | None]  # what was approved (edited or not)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None]
    # Nobody answered in time = no (approvals fail closed). Checked when someone decides.
    expires_at: Mapped[datetime]

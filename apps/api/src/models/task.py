import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin

TaskStatus = Literal["queued", "working", "done", "failed", "cancelled"]
OPEN_TASK_STATUSES = ("queued", "working")
TaskErrorCode = Literal["budget", "timeout", "stopped"]


class Task(IdMixin, CreatedAtMixin, Base):
    """A handoff (ADR 0014): one bot's run handed a piece of work to another bot of the
    organization, its **owner**, which does it in a child run in the same chat. The parent run
    waits (`waiting_handoff`) until its open tasks end, then reads their results.

        queued ──→ working ──→ done | failed | cancelled
           └──────────────────→ failed | cancelled

    Only `services/task_service.py` changes these rows, each change one conditional UPDATE under
    the parent run's row lock (see that module)."""

    __tablename__ = "tasks"
    __table_args__ = (
        # The idempotency key: one handoff call never makes two tasks.
        UniqueConstraint("parent_run_id", "tool_call_id", name="uq_tasks_parent_run_id_tool_call_id"),
        # "Does the parent still have open tasks?"
        Index("ix_tasks_parent_run_id_status", "parent_run_id", "status"),
        # The organization's cap on open tasks.
        Index("ix_tasks_org_id_status", "org_id", "status"),
        # The timeout job.
        Index("ix_tasks_status_deadline_at", "status", "deadline_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    parent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    tool_call_id: Mapped[str] = mapped_column(String(120))
    # The bots stay optional: removing a bot keeps the tasks it was part of (its open ones are
    # ended first, by `task_service.bot_removed`), and the owner's name and handle are kept here
    # so the parent (and the history) can still say who it was.
    from_bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), index=True)
    to_bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), index=True)
    to_bot_name: Mapped[str] = mapped_column(String(80), server_default="")
    to_bot_handle: Mapped[str] = mapped_column(String(64), server_default="")
    child_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), unique=True)
    # The message holding this task's handoff card (the child run's trigger).
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    requester_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    task: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[str | None] = mapped_column(Text)  # the owner's reply, cut to 8000 characters
    result_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(20))  # budget | timeout | stopped
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    deadline_at: Mapped[datetime]

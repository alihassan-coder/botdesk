import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin

RunStatus = Literal["queued", "running", "waiting_approval", "needs_attention", "succeeded", "failed", "cancelled"]
ACTIVE_STATUSES = ("queued", "running")
# Paused: waiting for a person (an approval, or a decision after a tool may have half run).
PAUSED_STATUSES = ("waiting_approval", "needs_attention")
FINISHED_STATUSES = ("succeeded", "failed", "cancelled")


class Run(IdMixin, CreatedAtMixin, Base):
    """One piece of work by one bot, from a trigger (a message) to a final answer.
    Its id is also the LangGraph thread id, so its checkpoints are found by run id."""

    __tablename__ = "runs"
    __table_args__ = (
        # "Is anything still going on in this chat?" and "how many runs does this bot have going?"
        Index("ix_runs_thread_id_status", "thread_id", "status"),
        Index("ix_runs_bot_id_status", "bot_id", "status"),
        # The database's own guard for "one run at a time per chat": at most one running run
        # per thread, even with several API copies. A second one fails to start, and waits.
        Index(
            "uq_runs_one_running_per_thread",
            "thread_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    reply_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # Limits, copied from settings when the run is created, and what has been used so far.
    max_steps: Mapped[int] = mapped_column(Integer)
    max_seconds: Mapped[int] = mapped_column(Integer)
    steps_used: Mapped[int] = mapped_column(Integer, default=0)
    # Set once a tool returned outside text (an email, a web page): from then on risky calls ask.
    tainted: Mapped[bool] = mapped_column(default=False)
    stop_requested: Mapped[bool] = mapped_column(default=False)
    graph_version: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class RunEvent(CreatedAtMixin, Base):
    """Something people should see live: a reply streaming in, a message saved, a run ending.
    The id only grows, so a browser that reconnects asks for everything after the last id it saw."""

    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_thread_id_id", "thread_id", "id"),)

    # BIGSERIAL on Postgres. SQLite only auto-numbers a column declared exactly as INTEGER.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    # Empty for chat events that no run caused (someone posting a message).
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]]


class ToolExecution(IdMixin, CreatedAtMixin, Base):
    """One tool call, recorded before and after it runs, so it never runs twice (ADR 0004 §2).

    `run_id` + `tool_call_id` is the idempotency key: preparing the same call again finds this
    row instead of adding one. The status moves:

        ready ──────────────→ started → succeeded | failed
        waiting_approval → ready (approved) | denied
        denied / failed       (decided without running: policy said no, or bad arguments)

    A row left `started` means we can't tell whether the tool finished (§4.1).
    """

    __tablename__ = "tool_executions"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_tool_executions_run_id_tool_call_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    tool_call_id: Mapped[str] = mapped_column(String(120))
    tool_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="ready")
    # The policy's answer and why, e.g. "level=Ask before acting · risk=external-send · tainted=no → ask".
    risk: Mapped[str] = mapped_column(String(20), default="read")
    decision: Mapped[str] = mapped_column(String(10), default="auto")  # auto | ask | deny | invalid
    decision_trace: Mapped[str] = mapped_column(Text, default="")
    # The arguments it runs with (after an edit, the edited ones) and their SHA-256.
    args: Mapped[dict[str, Any]] = mapped_column(default=dict)
    args_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

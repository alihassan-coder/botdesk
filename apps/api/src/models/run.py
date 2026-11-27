import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin

RunStatus = Literal[
    "queued", "running", "waiting_approval", "waiting_handoff", "needs_attention", "succeeded", "failed", "cancelled"
]
ACTIVE_STATUSES = ("queued", "running")
# Paused: waiting for a person (an approval, or a decision after a tool may have half run), or
# for the tasks it handed off to end (ADR 0014).
PAUSED_STATUSES = ("waiting_approval", "waiting_handoff", "needs_attention")
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
    # ADR 0009: the run whose reply @mentioned this bot (empty when a person's message started it),
    # and how far this run is from a person: 0 for a person's message, the parent's hop + 1 after.
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), index=True)
    hop: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # The member this run acts for (slice 5.2): who wrote the message that started its chain, or
    # who set up the routine. A member's own connection serves only that member's runs.
    requester_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # A cap on the run's security level, fixed when it was created: the run's effective level is
    # the strictest of its bot's and this. A routine's run keeps the strictest of its bot's and its
    # routine's (so removing or loosening the routine mid-run can't loosen it); a handoff's child
    # run keeps its parent's effective level (ADR 0014: a child is never looser than its parent).
    # Empty for other runs. The organization's ceiling (`Organization.max_security_level`) applies on
    # top, read when the run loads its context. (The handoffs contract's `level_cap` is this column.)
    security_level: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # Limits, copied from settings when the run is created, and what has been used so far.
    max_steps: Mapped[int] = mapped_column(Integer)
    max_seconds: Mapped[int] = mapped_column(Integer)
    steps_used: Mapped[int] = mapped_column(Integer, default=0)
    # Set once a tool returned outside text (an email, a web page): from then on risky calls ask.
    tainted: Mapped[bool] = mapped_column(default=False)
    stop_requested: Mapped[bool] = mapped_column(default=False)
    # Its message was sent with "send now" while a run of the same bot was working (ADR 0022): that
    # run may take the message at its next step, which cancels this one.
    deliver_now: Mapped[bool] = mapped_column(default=False, server_default=false())
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
    # The account the call worked on (ADR 0010 §9), when its plugin has one.
    connection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("connections.id", ondelete="SET NULL"))

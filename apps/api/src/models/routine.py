import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class Routine(IdMixin, CreatedAtMixin, Base):
    """A saved task a bot repeats on a schedule (a 5-field cron line in its creator's time zone).

    Each time it's due, the `fire_routines` job starts a run of its bot in the creator's DM with
    that bot, acting for the creator (the requester). A routine whose bot was removed, or whose
    creator left, is switched off with `disabled_reason`; a slot over budget is skipped."""

    __tablename__ = "routines"
    # "Which routines are due?" every minute.
    __table_args__ = (Index("ix_routines_enabled_next_run_at", "enabled", "next_run_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # Empty once the bot is removed: the routine stays (switched off) so people see what happened.
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    instructions: Mapped[str] = mapped_column(Text)  # what the bot should do each time
    cron: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64))  # IANA, e.g. "Asia/Karachi"
    enabled: Mapped[bool] = mapped_column(default=True)
    # Optional: makes the bot stricter for this routine's runs, never looser (ADR 0004).
    security_level: Mapped[str | None] = mapped_column(String(30))
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None]
    next_run_at: Mapped[datetime | None]  # empty while switched off


class RoutineRun(IdMixin, Base):
    """One time a routine was due (or run by hand): the run it started, or why it didn't."""

    __tablename__ = "routine_runs"
    __table_args__ = (Index("ix_routine_runs_routine_id_started_at", "routine_id", "started_at"),)

    routine_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routines.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), unique=True)
    started_at: Mapped[datetime]
    # started: `run_id` holds the run (its own status says how it went).
    # skipped: it didn't start; `reason` says why (its previous run was still going, or a
    # budget ran out).
    status: Mapped[str] = mapped_column(String(20), default="started")
    reason: Mapped[str | None] = mapped_column(Text)

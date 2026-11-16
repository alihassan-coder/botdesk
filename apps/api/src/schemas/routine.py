import uuid
from datetime import datetime

from pydantic import Field, field_validator

from src.models.bot import SecurityLevel
from src.schemas.common import ApiModel


def _not_blank(value: str | None) -> str | None:
    if value is not None and not value.strip():
        raise ValueError("This can't be empty.")
    return value.strip() if value is not None else None


class RoutineIn(ApiModel):
    bot_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=20000)  # what the bot should do each time
    cron: str = Field(max_length=120)  # 5 fields: minute hour day month weekday
    timezone: str = Field(max_length=64)  # IANA, the creator's (e.g. "Asia/Karachi")
    enabled: bool = True
    # Optional: makes the bot stricter for this routine, never looser.
    security_level: SecurityLevel | None = None

    _strip = field_validator("name", "instructions")(_not_blank)


class RoutineUpdate(ApiModel):
    """Only the fields you send change. `securityLevel: null` clears it."""

    bot_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    instructions: str | None = Field(default=None, min_length=1, max_length=20000)
    cron: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    security_level: SecurityLevel | None = None

    _strip = field_validator("name", "instructions")(_not_blank)


class RoutineOut(ApiModel):
    id: uuid.UUID
    bot_id: uuid.UUID | None  # empty once its bot was removed
    created_by: uuid.UUID | None
    name: str
    # Only for its creator, owners and admins; null for other members.
    instructions: str | None
    cron: str
    timezone: str
    enabled: bool
    security_level: SecurityLevel | None
    disabled_reason: str | None  # why BotDesk switched it off
    last_run_at: datetime | None
    next_run_at: datetime | None
    # How its latest run went: the run's status (queued, running, waiting_approval,
    # needs_attention, succeeded, failed, cancelled), or "skipped". Empty before the first.
    last_result: str | None = None
    created_at: datetime


class RoutineRunOut(ApiModel):
    id: uuid.UUID
    run_id: uuid.UUID | None
    thread_id: uuid.UUID | None  # the creator's DM, where the reply is
    started_at: datetime
    status: str  # the run's status, or "skipped"
    error: str | None  # the run's error
    reason: str | None = None  # why a skipped slot didn't run (still going, over budget)


class RunNowOut(ApiModel):
    run_id: uuid.UUID
    thread_id: uuid.UUID

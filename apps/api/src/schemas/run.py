import uuid
from datetime import datetime
from typing import Any

from src.models.run import RunStatus
from src.schemas.common import ApiModel


class RunOut(ApiModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    thread_id: uuid.UUID
    trigger_message_id: uuid.UUID | None
    reply_message_id: uuid.UUID | None
    status: RunStatus
    steps_used: int
    max_steps: int
    max_seconds: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ThreadRunsOut(ApiModel):
    """A chat's runs, and where its event stream should start: `after=lastEventId` so nothing
    that happens after this answer is missed, or `after=replayFrom` to also replay the events so
    far of the runs still streaming (queued or running): their words and tool lines. Paused runs
    don't move `replayFrom`; they're rebuilt from `runs` and the approvals list."""

    runs: list[RunOut]
    last_event_id: int
    replay_from: int


class RunEventOut(ApiModel):
    """One live update, as sent over the event stream (the SSE `data:` line)."""

    id: int
    kind: str
    run_id: uuid.UUID | None
    thread_id: uuid.UUID
    created_at: datetime
    data: dict[str, Any]

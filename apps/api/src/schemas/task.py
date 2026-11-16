import uuid
from datetime import datetime

from src.models.task import TaskErrorCode, TaskStatus
from src.schemas.common import ApiModel


class TaskOut(ApiModel):
    """A handed-off task (ADR 0014), as the `task_updated` event's `data.task`. Always the whole
    state of the task, never a patch. `context` and the full result never go to the web: the
    handoff card shows the preview and links to the owner's reply."""

    id: uuid.UUID
    thread_id: uuid.UUID
    parent_run_id: uuid.UUID
    child_run_id: uuid.UUID | None
    message_id: uuid.UUID | None
    from_bot_id: uuid.UUID | None
    to_bot_id: uuid.UUID | None  # None once the bot is removed
    task: str
    status: TaskStatus
    result_message_id: uuid.UUID | None
    result_preview: str | None
    error: str | None
    error_code: TaskErrorCode | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    deadline_at: datetime

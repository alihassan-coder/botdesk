"""Run events: the live updates of a chat, saved so a reconnecting browser misses nothing.

Every event is a row in `run_events` with a growing id. The live stream and the replay
after a reconnect read the same table, so they can never disagree.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import RunEvent
from src.schemas.run import RunEventOut

PAGE_SIZE = 200


def add_event(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    thread_id: uuid.UUID,
    run_id: uuid.UUID | None,
    kind: str,
    data: dict[str, Any],
) -> RunEvent:
    """Adds the event to the current transaction. It is saved, and can be announced, on commit."""
    event = RunEvent(org_id=org_id, thread_id=thread_id, run_id=run_id, kind=kind, payload=data)
    db.add(event)
    return event


async def events_after(db: AsyncSession, *, thread_id: uuid.UUID, after_id: int) -> list[RunEvent]:
    """The thread's events with an id above `after_id`, oldest first, a page at a time."""
    rows = await db.scalars(
        select(RunEvent)
        .where(RunEvent.thread_id == thread_id, RunEvent.id > after_id)
        .order_by(RunEvent.id)
        .limit(PAGE_SIZE)
    )
    return list(rows)


async def latest_event_id(db: AsyncSession, *, thread_id: uuid.UUID) -> int:
    """Where a stream with no Last-Event-ID starts: after everything already saved."""
    return await db.scalar(select(func.coalesce(func.max(RunEvent.id), 0)).where(RunEvent.thread_id == thread_id)) or 0


def event_out(event: RunEvent) -> RunEventOut:
    return RunEventOut.model_validate(
        {
            "id": event.id,
            "kind": event.kind,
            "run_id": event.run_id,
            "thread_id": event.thread_id,
            "created_at": event.created_at,
            "data": event.payload,
        }
    )

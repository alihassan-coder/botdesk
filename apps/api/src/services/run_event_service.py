"""Run events: the live updates of a chat, saved so a reconnecting browser misses nothing.

Every event is a row in `run_events` with a growing id. The live stream and the replay
after a reconnect read the same table, so they can never disagree.

On Postgres, ids come from a sequence when a row is inserted, but become visible when its
transaction commits, and two transactions can commit in either order. A stream that has seen
id 8 would never see an id 7 committed after it. So a transaction that adds events to a chat
first takes that chat's advisory lock (held until it commits): within a chat, ids are taken
and committed one transaction at a time, in order.
"""

import uuid
from typing import Any

from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

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


def thread_lock_key(thread_id: uuid.UUID) -> int:
    """The chat's advisory lock: a signed 64-bit number from its id."""
    return int.from_bytes(thread_id.bytes[:8], "big", signed=True)


LOCKED_THREADS = "botdesk.locked_threads"  # session.info key: chats whose lock this transaction holds


@event.listens_for(Session, "before_flush")
def _lock_chats_before_adding_events(session: Session, _context: Any, _instances: Any) -> None:
    """Before new events get their ids, wait for any other transaction adding events to the same
    chat to commit (see the module docstring). One short lock per flush; the token batcher already
    groups a reply's words into a few events a second. SQLite writes one at a time anyway.

    Deadlock rule: a transaction takes chat locks in ascending order of `thread_lock_key`, so two
    transactions touching the same chats can't wait on each other. Within one flush that's done
    here by sorting. Across flushes it's on the caller: once a transaction holds a chat's lock it
    may add events to that chat again, or to chats with a *higher* key, never a lower one. A
    transaction that breaks the rule raises here instead of deadlocking now and then in production.
    (Today every transaction adds events to one chat only.)"""
    threads = {obj.thread_id for obj in session.new if isinstance(obj, RunEvent)}
    if not threads or session.get_bind().dialect.name != "postgresql":
        return
    held: set[uuid.UUID] = session.info.setdefault(LOCKED_THREADS, set())
    new_keys = sorted(thread_lock_key(t) for t in threads - held)
    if not new_keys:
        return
    highest_held = max((thread_lock_key(t) for t in held), default=None)
    if highest_held is not None and new_keys[0] < highest_held:
        raise RuntimeError(
            "A transaction added run events to a chat whose lock sorts before one it already holds; "
            "this can deadlock. Add events to chats in order of thread_lock_key, or commit in between."
        )
    for key in new_keys:
        session.connection().execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    held.update(threads)


@event.listens_for(Session, "after_transaction_end")
def _forget_chat_locks(session: Session, transaction: SessionTransaction) -> None:
    """Advisory xact locks end with the transaction, and so does our record of them."""
    if transaction.parent is None:
        session.info.pop(LOCKED_THREADS, None)


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

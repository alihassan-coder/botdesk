"""Handles thread and message requests."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime

from fastapi.sse import ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.runtime.runner import RunManager
from src.schemas.run import ThreadRunsOut
from src.schemas.thread import GroupIn, MessageIn, MessageOut, SentMessageOut, ThreadOut
from src.services import run_event_service, run_service, thread_service

RECHECK_SECONDS = 5.0  # how often an idle stream looks for events saved by another API process


async def list_threads(db: AsyncSession, access: Access) -> list[ThreadOut]:
    threads = await thread_service.threads_for_user(db, org_id=access.org.id, user_id=access.user.id)
    return await thread_service.thread_outs(db, threads)


async def get_thread(db: AsyncSession, access: Access, thread_id: uuid.UUID) -> ThreadOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    return await thread_service.thread_out(db, thread)


async def open_dm(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> ThreadOut:
    thread = await thread_service.open_dm(db, org_id=access.org.id, user_id=access.user.id, bot_id=bot_id)
    await db.commit()
    return await thread_service.thread_out(db, thread)


async def create_group(db: AsyncSession, access: Access, body: GroupIn) -> ThreadOut:
    thread = await thread_service.create_group(
        db,
        org_id=access.org.id,
        creator_id=access.user.id,
        title=body.title,
        user_ids=body.user_ids,
        bot_ids=body.bot_ids,
    )
    await db.commit()
    return await thread_service.thread_out(db, thread)


async def list_messages(
    db: AsyncSession, access: Access, thread_id: uuid.UUID, *, limit: int, before: datetime | None
) -> list[MessageOut]:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    messages = await thread_service.list_messages(db, thread, limit=limit, before=before)
    return [thread_service.message_out(message) for message in messages]


async def list_runs(db: AsyncSession, access: Access, thread_id: uuid.UUID, *, active: bool) -> ThreadRunsOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    found = await run_service.thread_runs(db, thread.id, active=active)
    return ThreadRunsOut(
        runs=[run_service.run_out(run) for run in found.runs],
        last_event_id=found.last_event_id,
        replay_from=found.replay_from,
    )


async def post_message(
    db: AsyncSession, access: Access, runs: RunManager, thread_id: uuid.UUID, body: MessageIn
) -> SentMessageOut:
    """Save the message and a queued run for each bot that should reply, in one transaction,
    then start the runs in the background. The reply streams in over the event stream."""
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    message = await thread_service.post_message(db, thread=thread, user_id=access.user.id, text=body.text)
    new_runs = await run_service.create_runs(db, thread=thread, message=message, settings=runs.settings, text=body.text)
    out = thread_service.message_out(message)
    run_event_service.add_event(
        db,
        org_id=thread.org_id,
        thread_id=thread.id,
        run_id=None,
        kind="message_saved",
        data={"message": out.model_dump(mode="json", by_alias=True)},
    )
    await db.commit()
    runs.bus.announce(thread.id)
    runs.start(new_runs)
    return SentMessageOut(**out.model_dump(), run_ids=[run.id for run in new_runs])


async def event_stream_start(
    db: AsyncSession, access: Access, thread_id: uuid.UUID, *, last_event_id: str | None, after: int | None
) -> int:
    """Check the user is in the chat, and work out where their stream starts: after the
    browser's Last-Event-ID (a reconnect), else after `after`, else from now on."""
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    if last_event_id and last_event_id.isdigit():
        start = int(last_event_id)
    elif after is not None:
        start = after
    else:
        start = await run_event_service.latest_event_id(db, thread_id=thread.id)
    # A stream can stay open for hours. Give this request's database connection back now;
    # the stream borrows one only for each short read.
    await db.close()
    return start


async def follow_events(
    runs: RunManager, thread_id: uuid.UUID, *, after_id: int, follow: bool
) -> AsyncIterator[ServerSentEvent]:
    """Send the chat's saved events after `after_id`, then each new one as it's saved."""
    with runs.bus.listen(thread_id) as wake_up:
        while True:
            wake_up.clear()  # before reading, so an event saved during the read still wakes us
            async with runs.sessionmaker() as db:
                events = await run_event_service.events_after(db, thread_id=thread_id, after_id=after_id)
            for event in events:
                after_id = event.id
                data = run_event_service.event_out(event).model_dump(mode="json", by_alias=True)
                yield ServerSentEvent(id=str(event.id), event=event.kind, data=data)
            if len(events) == run_event_service.PAGE_SIZE:
                continue  # more saved events to catch up on
            if not follow:
                return
            # Wait for a wake-up, or look again anyway after a few seconds: events saved by
            # another API process don't reach this process's bus.
            with suppress(TimeoutError):
                await asyncio.wait_for(wake_up.wait(), RECHECK_SECONDS)

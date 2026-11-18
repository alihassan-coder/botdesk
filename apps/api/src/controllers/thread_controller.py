"""Handles thread and message requests."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime

from fastapi.sse import ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.models import RunEvent, Thread
from src.models.thread import ParticipantType
from src.runtime.runner import RunManager
from src.schemas.run import ThreadRunsOut
from src.schemas.thread import (
    GroupIn,
    GroupPatchIn,
    LeadIn,
    MessageIn,
    MessageOut,
    ParticipantsIn,
    SentMessageOut,
    ThreadOut,
)
from src.services import run_event_service, run_service, thread_service

# How often an idle stream looks for new events anyway: Postgres notifications wake it at once,
# but one sent while the listening connection reconnects is lost.
RECHECK_SECONDS = 5.0


async def list_threads(db: AsyncSession, access: Access) -> list[ThreadOut]:
    threads = await thread_service.threads_for_user(db, org_id=access.org.id, user_id=access.user.id)
    return await thread_service.thread_outs(db, threads, user_id=access.user.id)


async def get_thread(db: AsyncSession, access: Access, thread_id: uuid.UUID) -> ThreadOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    return await thread_service.thread_out(db, thread, user_id=access.user.id)


async def open_dm(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> ThreadOut:
    thread = await thread_service.open_dm(db, org_id=access.org.id, user_id=access.user.id, bot_id=bot_id)
    await db.commit()
    return await thread_service.thread_out(db, thread, user_id=access.user.id)


async def create_group(db: AsyncSession, access: Access, body: GroupIn) -> ThreadOut:
    thread = await thread_service.create_group(
        db,
        org_id=access.org.id,
        creator_id=access.user.id,
        title=body.title,
        user_ids=body.user_ids,
        bot_ids=body.bot_ids,
        lead_bot_id=body.lead_bot_id,
    )
    await db.commit()
    return await thread_service.thread_out(db, thread, user_id=access.user.id)


async def set_lead(db: AsyncSession, access: Access, runs: RunManager, thread_id: uuid.UUID, body: LeadIn) -> ThreadOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    await thread_service.set_lead(db, thread, user_id=access.user.id, role=access.role, bot_id=body.bot_id)
    return await _saved_change(db, access, runs, thread)


async def rename_group(
    db: AsyncSession, access: Access, runs: RunManager, thread_id: uuid.UUID, body: GroupPatchIn
) -> ThreadOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    await thread_service.rename_group(db, thread, user_id=access.user.id, role=access.role, title=body.title)
    return await _saved_change(db, access, runs, thread)


async def add_participants(
    db: AsyncSession, access: Access, runs: RunManager, thread_id: uuid.UUID, body: ParticipantsIn
) -> ThreadOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    await thread_service.add_participants(
        db, thread, user_id=access.user.id, role=access.role, user_ids=body.user_ids, bot_ids=body.bot_ids
    )
    return await _saved_change(db, access, runs, thread)


async def remove_participant(
    db: AsyncSession,
    access: Access,
    runs: RunManager,
    thread_id: uuid.UUID,
    kind: ParticipantType,
    participant_id: uuid.UUID,
) -> ThreadOut:
    """A bot taken out of a group stops what it was doing there, so it doesn't post into a group
    it's no longer in: its unfinished runs in the group are listed once the change is saved (so a
    run queued while it was saving is in the list) and stopped, each in its own transaction like
    the Stop button. One queued even later never starts (`run_service.left_its_group`)."""
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    await thread_service.remove_participant(
        db, thread, user_id=access.user.id, role=access.role, kind=kind, participant_id=participant_id
    )
    out = await _saved_change(db, access, runs, thread)
    if kind == "bot":
        going = await run_service.unfinished_in_thread(db, thread.id, bot_id=participant_id)
        await db.commit()  # end the read before stopping
        for run_id in going:
            await runs.stop(run_id)
    return out


async def _saved_change(db: AsyncSession, access: Access, runs: RunManager, thread: Thread) -> ThreadOut:
    """Save a change to a group, and tell everyone with it open (`thread_updated` on its stream).
    The group is read once: the event leaves out your unread count (the stream is shared)."""
    out = await thread_service.thread_out(db, thread, user_id=access.user.id)
    run_event_service.add_event(
        db,
        org_id=thread.org_id,
        thread_id=thread.id,
        run_id=None,
        kind="thread_updated",
        data={"thread": out.model_dump(mode="json", by_alias=True, exclude={"unread"})},
    )
    await db.commit()
    runs.bus.announce(thread.id)
    return out


async def mark_read(db: AsyncSession, access: Access, thread_id: uuid.UUID) -> None:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    await thread_service.mark_read(db, thread, user_id=access.user.id)
    await db.commit()


async def list_messages(
    db: AsyncSession, access: Access, thread_id: uuid.UUID, *, limit: int, before: datetime | None
) -> list[MessageOut]:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    messages = await thread_service.list_messages(db, thread, limit=limit, before=before)
    return [thread_service.message_out(message) for message in messages]


async def list_runs(db: AsyncSession, access: Access, thread_id: uuid.UUID, *, active: bool) -> ThreadRunsOut:
    thread = await thread_service.get_thread(db, org_id=access.org.id, user_id=access.user.id, thread_id=thread_id)
    found = await run_service.thread_runs(db, thread.id, active=active)
    waiting_for = await run_service.waiting_task_ids(db, found.runs)
    return ThreadRunsOut(
        runs=[run_service.run_out(run, task_ids=waiting_for.get(run.id)) for run in found.runs],
        last_event_id=found.last_event_id,
        replay_from=found.replay_from,
    )


async def post_message(
    db: AsyncSession, access: Access, runs: RunManager, thread_id: uuid.UUID, body: MessageIn
) -> SentMessageOut:
    """Save the message, a queued run for each bot that should reply and the runs' jobs, in one
    transaction. A worker picks the jobs up; the reply streams in over the event stream."""
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
    await runs.start(db, new_runs)
    await db.commit()
    runs.bus.announce(thread.id)
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


def _leaves_out(event: RunEvent, user_id: uuid.UUID) -> bool:
    """A group change after which this person is no longer in it."""
    if event.kind != "thread_updated":
        return False
    people = event.payload["thread"]["participants"]
    return not any(p["type"] == "user" and p["id"] == str(user_id) for p in people)


async def follow_events(
    runs: RunManager, thread_id: uuid.UUID, *, user_id: uuid.UUID, after_id: int, follow: bool
) -> AsyncIterator[ServerSentEvent]:
    """Send the chat's saved events after `after_id`, then each new one as it's saved. Stops once
    the person is no longer in the chat (removed from a group while they had it open) or no longer
    in its organization. Events are read before that check, so a batch never reaches past it."""
    with runs.bus.listen(thread_id) as wake_up:
        while True:
            wake_up.clear()  # before reading, so an event saved during the read still wakes us
            async with runs.sessionmaker() as db:
                events = await run_event_service.events_after(db, thread_id=thread_id, after_id=after_id)
                still_in = await thread_service.can_follow(db, thread_id, user_id)
            if not still_in:
                # Removed: send up to the change that removed them (so their browser drops the
                # group), nothing after it, and stop.
                removal = next((i for i, e in enumerate(events) if _leaves_out(e, user_id)), -1)
                for event in events[: removal + 1]:
                    data = run_event_service.event_out(event).model_dump(mode="json", by_alias=True)
                    yield ServerSentEvent(id=str(event.id), event=event.kind, data=data)
                return
            for event in events:
                after_id = event.id
                data = run_event_service.event_out(event).model_dump(mode="json", by_alias=True)
                yield ServerSentEvent(id=str(event.id), event=event.kind, data=data)
            if len(events) == run_event_service.PAGE_SIZE:
                continue  # more saved events to catch up on
            if not follow:
                return
            # Wait for a wake-up (this process's bus, fed by Postgres notifications from other
            # processes), or look again anyway after a few seconds.
            with suppress(TimeoutError):
                await asyncio.wait_for(wake_up.wait(), RECHECK_SECONDS)

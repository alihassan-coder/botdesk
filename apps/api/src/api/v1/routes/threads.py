import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from src.api.deps import Db, OrgAccess, Runs
from src.controllers import thread_controller
from src.schemas.run import ThreadRunsOut
from src.schemas.thread import GroupIn, MessageIn, MessageOut, OpenDmIn, SentMessageOut, ThreadOut

router = APIRouter(prefix="/orgs/{org_id}/threads", tags=["threads"])


@router.get("")
async def list_threads(access: OrgAccess, db: Db) -> list[ThreadOut]:
    """Your chats in this organization, most recent first."""
    return await thread_controller.list_threads(db, access)


@router.post("/dm")
async def open_dm(body: OpenDmIn, access: OrgAccess, db: Db) -> ThreadOut:
    """Your chat with a bot. Returns the existing one, or starts it."""
    return await thread_controller.open_dm(db, access, body.bot_id)


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupIn, access: OrgAccess, db: Db) -> ThreadOut:
    """A group chat with you plus the people and bots you pick."""
    return await thread_controller.create_group(db, access, body)


@router.get("/{thread_id}")
async def get_thread(thread_id: uuid.UUID, access: OrgAccess, db: Db) -> ThreadOut:
    return await thread_controller.get_thread(db, access, thread_id)


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: uuid.UUID,
    access: OrgAccess,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: datetime | None = None,
) -> list[MessageOut]:
    """Messages, oldest first. For older ones, pass the first message's `createdAt` as `before`."""
    return await thread_controller.list_messages(db, access, thread_id, limit=limit, before=before)


@router.post("/{thread_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(thread_id: uuid.UUID, body: MessageIn, access: OrgAccess, db: Db, runs: Runs) -> SentMessageOut:
    """Send a message. In a DM the bot replies; in a group, the bots you @mention do.
    Returns at once with the ids of the runs it started; replies arrive on `/events`."""
    return await thread_controller.post_message(db, access, runs, thread_id, body)


@router.get("/{thread_id}/runs")
async def list_runs(thread_id: uuid.UUID, access: OrgAccess, db: Db, active: bool = False) -> ThreadRunsOut:
    """The chat's runs, newest first (at most 100). `active=true`: only the ones not finished
    (queued, running, waiting_approval, needs_attention), so a chat opened later can show
    them. Follow `/events?after={lastEventId}` from here and nothing is missed."""
    return await thread_controller.list_runs(db, access, thread_id, active=active)


async def _stream_start(
    thread_id: uuid.UUID,
    access: OrgAccess,
    db: Db,
    last_event_id: Annotated[str | None, Header()] = None,
    after: int | None = None,
) -> int:
    """Runs before the stream opens, so a chat you're not in gets a normal 404."""
    return await thread_controller.event_stream_start(db, access, thread_id, last_event_id=last_event_id, after=after)


@router.get("/{thread_id}/events", response_class=EventSourceResponse)
async def stream_events(
    thread_id: uuid.UUID,
    start: Annotated[int, Depends(_stream_start)],
    runs: Runs,
    follow: bool = True,
) -> AsyncIterator[ServerSentEvent]:
    """Live updates for this chat (Server-Sent Events): replies streaming in, messages saved,
    runs starting and ending. A reconnect resumes after `Last-Event-ID`; `after` does the same
    on a first connection. `follow=false` sends what's saved and closes."""
    async for event in thread_controller.follow_events(runs, thread_id, after_id=start, follow=follow):
        yield event

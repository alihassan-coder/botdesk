"""Tells a chat's open live streams "new events are saved, read them".

The bus carries no data: streams always read events from `run_events`, so a missed
wake-up only delays an update, it never loses one. `EventBus` lives in memory and reaches
streams in this process. Across processes (a separate worker, several API copies) Postgres
carries the wake-ups: every transaction that saves events for a chat sends
`NOTIFY botdesk_run_events, '<chat id>'` (`run_event_service`), and `listen_to_postgres` passes
them on to this process's bus. Streams also re-check the table every few seconds, in case a
notification is lost while the listening connection reconnects.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import AsyncConnection

from src.core.database import postgres_connect_args
from src.services.run_event_service import RUN_EVENTS_CHANNEL

logger = logging.getLogger(__name__)

PING_SECONDS = 60.0  # an idle listening connection is tested this often (a dead one is replaced)
RECONNECT_SECONDS = (1.0, 30.0)  # first and longest wait before connecting again


class EventBus:
    def __init__(self) -> None:
        self._listeners: defaultdict[uuid.UUID, set[asyncio.Event]] = defaultdict(set)

    def announce(self, thread_id: uuid.UUID) -> None:
        """Call after committing new events for this thread."""
        for wake_up in self._listeners.get(thread_id, ()):
            wake_up.set()

    def announce_all(self) -> None:
        """Wake every stream (after notifications may have been missed)."""
        for listeners in self._listeners.values():
            for wake_up in listeners:
                wake_up.set()

    @contextmanager
    def listen(self, thread_id: uuid.UUID) -> Iterator[asyncio.Event]:
        """An event that is set whenever this thread gets new events. Clear it before each read."""
        wake_up = asyncio.Event()
        self._listeners[thread_id].add(wake_up)
        try:
            yield wake_up
        finally:
            self._listeners[thread_id].discard(wake_up)
            if not self._listeners[thread_id]:
                del self._listeners[thread_id]


async def listen_to_postgres(url: str, bus: EventBus, *, ping_seconds: float = PING_SECONDS) -> None:
    """Pass Postgres notifications about new run events on to `bus`, until cancelled. One
    connection per process, on the direct address (`LISTEN` doesn't work through a transaction
    pooler). A dropped connection (Neon suspends after 5 idle minutes and closes them) is noticed
    by the ping and replaced; after each reconnect every stream re-reads, in case it missed one."""
    wait = RECONNECT_SECONDS[0]
    while True:
        try:
            async with await AsyncConnection.connect(url, autocommit=True, **postgres_connect_args(url)) as connection:
                await connection.execute(f"LISTEN {RUN_EVENTS_CHANNEL}")
                wait = RECONNECT_SECONDS[0]
                bus.announce_all()
                while True:
                    async for notification in connection.notifies(timeout=ping_seconds):
                        bus.announce(uuid.UUID(notification.payload))
                    await connection.execute("SELECT 1")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Lost the live events connection (%s); connecting again in %.0f s", error, wait)
        await asyncio.sleep(wait)
        wait = min(wait * 2, RECONNECT_SECONDS[1])

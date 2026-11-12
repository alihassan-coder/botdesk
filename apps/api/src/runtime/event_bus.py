"""Tells a chat's open live streams "new events are saved, read them".

The bus carries no data: streams always read events from `run_events`, so a missed
wake-up only delays an update, it never loses one. This one lives in memory, so it reaches
streams in this API process only; streams also re-check the table every few seconds,
which covers the rest. A Postgres LISTEN/NOTIFY bus can replace it with the same two methods.
"""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager


class EventBus:
    def __init__(self) -> None:
        self._listeners: defaultdict[uuid.UUID, set[asyncio.Event]] = defaultdict(set)

    def announce(self, thread_id: uuid.UUID) -> None:
        """Call after committing new events for this thread."""
        for wake_up in self._listeners.get(thread_id, ()):
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

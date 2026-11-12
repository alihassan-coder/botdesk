"""Saves one run's events and wakes the chat's live streams."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.runtime.event_bus import EventBus
from src.services import run_event_service


@dataclass(frozen=True)
class RunReporter:
    sessionmaker: async_sessionmaker[AsyncSession]
    bus: EventBus
    org_id: uuid.UUID
    thread_id: uuid.UUID
    run_id: uuid.UUID

    def add(self, db: AsyncSession, kind: str, data: dict[str, Any]) -> None:
        """Add an event to a transaction you're about to commit (then call `announce`)."""
        run_event_service.add_event(
            db, org_id=self.org_id, thread_id=self.thread_id, run_id=self.run_id, kind=kind, data=data
        )

    def announce(self) -> None:
        self.bus.announce(self.thread_id)

    async def send(self, kind: str, data: dict[str, Any]) -> None:
        """Save one event in its own short transaction, then wake the streams."""
        async with self.sessionmaker() as db:
            self.add(db, kind, data)
            await db.commit()
        self.announce()

"""Collect streamed tokens into small batches.

A model sends a token every few milliseconds. Saving and sending each one would mean
hundreds of tiny database writes per reply, so we send a batch when enough time has
passed or enough text has piled up, whichever comes first.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress


class TokenBatcher:
    def __init__(self, *, max_wait: float = 0.05, max_chars: int = 200) -> None:
        self.max_wait = max_wait  # seconds
        self.max_chars = max_chars
        self._pending: list[str] = []
        self._size = 0
        self._started_at: float | None = None

    def add(self, text: str, *, now: float) -> str | None:
        """Add a token. Returns a batch when one is ready to send, otherwise None."""
        if self._started_at is None:
            self._started_at = now
        self._pending.append(text)
        self._size += len(text)
        if self._size >= self.max_chars or now - self._started_at >= self.max_wait:
            return self.flush()
        return None

    def flush(self) -> str | None:
        """Whatever is waiting (call it when the stream ends)."""
        if not self._pending:
            return None
        batch = "".join(self._pending)
        self._pending, self._size, self._started_at = [], 0, None
        return batch


class BackgroundSender:
    """Sends text in order on a background task, so the model's stream never waits for the
    database. Text that arrives while a send is in flight is joined into the next send: a
    slow database means fewer, bigger writes instead of a backlog.

        async with BackgroundSender(save_text) as sender:
            sender.send("Hel")
            sender.send("lo")
        # leaving the block waits for the last send, and raises if a send failed
    """

    def __init__(self, send_text: Callable[[str], Awaitable[None]]) -> None:
        self._send_text = send_text
        self._waiting: list[str] = []
        self._wake_up = asyncio.Event()
        self._closing = False
        self._task: asyncio.Task[None] | None = None

    def send(self, text: str) -> None:
        self._waiting.append(text)
        self._wake_up.set()

    async def __aenter__(self) -> "BackgroundSender":
        self._task = asyncio.create_task(self._send_all())
        return self

    async def __aexit__(self, error_type: type[BaseException] | None, *_: object) -> None:
        assert self._task is not None
        self._closing = True
        self._wake_up.set()
        if error_type is not None:  # the stream failed: drop what's left, keep the original error
            self._task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._task
            return
        await self._task

    async def _send_all(self) -> None:
        while True:
            if not self._waiting:
                if self._closing:
                    return
                await self._wake_up.wait()
                self._wake_up.clear()
                continue
            text = "".join(self._waiting)
            self._waiting.clear()
            await self._send_text(text)

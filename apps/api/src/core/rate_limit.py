"""An in-process rate limiter: at most `hits` attempts per key in any `seconds`-long window.

It lives in the API process's memory, which is right while there is one API process (ADR 0007).
Several API copies would each count on their own; that needs a shared store (Postgres or Redis)
and comes with the job queue (ADR 0005).

Memory is bounded: a key keeps at most `hits` timestamps, keys whose window has passed are swept
out, and past `max_keys` the least recently used keys are dropped (under a flood of new addresses
that forgets the oldest, which errs towards letting someone through, never towards locking out).
"""

import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    hits: int
    seconds: int


@dataclass
class _Bucket:
    seconds: int
    times: deque[float]


class RateLimiter:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 50_000,
        sweep_every: int = 1_000,
    ) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._sweep_every = sweep_every
        self._since_sweep = 0
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    def __len__(self) -> int:
        return len(self._buckets)

    def hit(self, *checks: tuple[str, Limit]) -> int | None:
        """Count one attempt against every key, if all of them allow it, and return None.
        Otherwise count nothing and return how many seconds until all of them would allow it.

        No `await` inside, so on the event loop a check and its count can't interleave."""
        now = self._clock()
        self._maybe_sweep(now)
        wait = 0.0
        for key, limit in checks:
            times = self._recent(key, now)
            if len(times) >= limit.hits:
                wait = max(wait, times[-limit.hits] + limit.seconds - now)
        if wait > 0:
            return max(1, math.ceil(wait))
        for key, limit in checks:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = self._buckets[key] = _Bucket(limit.seconds, deque(maxlen=limit.hits))
            bucket.seconds = max(bucket.seconds, limit.seconds)
            bucket.times.append(now)
            self._buckets.move_to_end(key)
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)
        return None

    def _recent(self, key: str, now: float) -> deque[float]:
        bucket = self._buckets.get(key)
        if bucket is None:
            return deque()
        while bucket.times and bucket.times[0] <= now - bucket.seconds:
            bucket.times.popleft()
        return bucket.times

    def _maybe_sweep(self, now: float) -> None:
        self._since_sweep += 1
        if self._since_sweep < self._sweep_every:
            return
        self._since_sweep = 0
        expired = [key for key, b in self._buckets.items() if not b.times or b.times[-1] <= now - b.seconds]
        for key in expired:
            del self._buckets[key]

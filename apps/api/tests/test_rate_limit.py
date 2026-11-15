"""The in-process rate limiter (core/rate_limit.py): sliding windows per key, bounded memory."""

import pytest

from src.core.rate_limit import Limit, RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


PER_MINUTE = Limit(hits=3, seconds=60)


def test_allows_up_to_the_limit_then_says_how_long_to_wait(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock)
    assert [limiter.hit(("ip:1", PER_MINUTE)) for _ in range(3)] == [None, None, None]
    clock.now += 20
    assert limiter.hit(("ip:1", PER_MINUTE)) == 40  # the first hit leaves the window in 40 s


def test_the_window_slides(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock)
    limiter.hit(("ip:1", PER_MINUTE))
    clock.now += 30
    limiter.hit(("ip:1", PER_MINUTE))
    limiter.hit(("ip:1", PER_MINUTE))
    clock.now += 31  # the first hit is now older than a minute; the other two still count
    assert limiter.hit(("ip:1", PER_MINUTE)) is None
    assert limiter.hit(("ip:1", PER_MINUTE)) == 29


def test_refused_attempts_dont_extend_the_wait(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock)
    for _ in range(3):
        limiter.hit(("ip:1", PER_MINUTE))
    for _ in range(10):
        assert limiter.hit(("ip:1", PER_MINUTE)) == 60
    clock.now += 60
    assert limiter.hit(("ip:1", PER_MINUTE)) is None


def test_keys_are_counted_separately(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock)
    for _ in range(3):
        limiter.hit(("ip:1", PER_MINUTE))
    assert limiter.hit(("ip:1", PER_MINUTE)) is not None
    assert limiter.hit(("ip:2", PER_MINUTE)) is None


def test_several_keys_at_once_count_only_when_all_allow(clock: Clock) -> None:
    """Sign-in checks the address and the email together: a refusal by one counts against neither."""
    limiter = RateLimiter(clock=clock)
    tight = Limit(hits=1, seconds=60)
    assert limiter.hit(("email:a", tight), ("ip:1", PER_MINUTE)) is None
    assert limiter.hit(("email:a", tight), ("ip:1", PER_MINUTE)) == 60
    # The refused attempt didn't use up the address's allowance: two more fit.
    assert limiter.hit(("email:b", tight), ("ip:1", PER_MINUTE)) is None
    assert limiter.hit(("email:c", tight), ("ip:1", PER_MINUTE)) is None
    assert limiter.hit(("email:d", tight), ("ip:1", PER_MINUTE)) == 60


def test_the_longest_wait_wins(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock)
    hourly = Limit(hits=1, seconds=3600)
    limiter.hit(("email:a", hourly), ("ip:1", Limit(hits=1, seconds=60)))
    assert limiter.hit(("email:a", hourly), ("ip:1", Limit(hits=1, seconds=60))) == 3600


def test_old_buckets_are_dropped(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock, sweep_every=1)
    for ip in range(100):
        limiter.hit((f"ip:{ip}", PER_MINUTE))
    assert len(limiter) == 100
    clock.now += 61
    limiter.hit(("ip:new", PER_MINUTE))
    assert len(limiter) == 1


def test_memory_stays_bounded_under_a_flood_of_new_keys(clock: Clock) -> None:
    limiter = RateLimiter(clock=clock, max_keys=50)
    for ip in range(1000):
        limiter.hit((f"ip:{ip}", PER_MINUTE))
    assert len(limiter) <= 50
    # The newest keys are the ones kept.
    for _ in range(2):
        limiter.hit(("ip:999", PER_MINUTE))
    assert limiter.hit(("ip:999", PER_MINUTE)) is not None

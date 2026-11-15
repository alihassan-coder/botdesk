"""A routine's schedule: a 5-field cron line read in the creator's time zone (services/routine_schedule.py)."""

from datetime import UTC, datetime

import pytest

from src.core.errors import BadRequest
from src.services.routine_schedule import check_schedule, next_run


def utc(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def test_every_day_at_nine_in_karachi_is_four_utc() -> None:
    assert next_run("0 9 * * *", "Asia/Karachi", after=utc(2026, 11, 15, 3, 0)) == utc(2026, 11, 15, 4, 0)
    # Already past today's 09:00 there: tomorrow.
    assert next_run("0 9 * * *", "Asia/Karachi", after=utc(2026, 11, 15, 4, 0)) == utc(2026, 11, 16, 4, 0)


def test_weekdays_skip_the_weekend() -> None:
    # Friday 2026-11-13 after 09:00 in London → Monday 2026-11-16 09:00 (GMT = UTC in November).
    assert next_run("0 9 * * 1-5", "Europe/London", after=utc(2026, 11, 13, 10, 0)) == utc(2026, 11, 16, 9, 0)


def test_every_hour() -> None:
    assert next_run("0 * * * *", "UTC", after=utc(2026, 11, 15, 10, 30)) == utc(2026, 11, 15, 11, 0)


def test_the_same_wall_time_across_a_dst_change() -> None:
    # New York: 09:00 is 14:00 UTC in winter (EST) and 13:00 UTC in summer (EDT).
    assert next_run("0 9 * * *", "America/New_York", after=utc(2026, 3, 7, 15, 0)) == utc(2026, 3, 8, 13, 0)
    assert next_run("0 9 * * *", "America/New_York", after=utc(2026, 10, 31, 14, 0)) == utc(2026, 11, 1, 14, 0)


def test_a_time_that_doesnt_exist_on_the_spring_forward_day_runs_an_hour_later() -> None:
    # 02:30 doesn't exist in New York on 2026-03-08: it runs at 03:30 EDT (07:30 UTC), once.
    assert next_run("30 2 * * *", "America/New_York", after=utc(2026, 3, 8, 5, 0)) == utc(2026, 3, 8, 7, 30)
    assert next_run("30 2 * * *", "America/New_York", after=utc(2026, 3, 8, 7, 30)) == utc(2026, 3, 9, 6, 30)


def test_a_time_that_happens_twice_on_the_fall_back_day_runs_once() -> None:
    # 01:30 happens twice in New York on 2026-11-01 (EDT 05:30 UTC, then EST 06:30 UTC): the first.
    first = next_run("30 1 * * *", "America/New_York", after=utc(2026, 11, 1, 4, 0))
    assert first == utc(2026, 11, 1, 5, 30)
    assert next_run("30 1 * * *", "America/New_York", after=first) == utc(2026, 11, 2, 6, 30)


@pytest.mark.parametrize(
    ("cron", "timezone", "error"),
    [
        ("0 9 * *", "UTC", "Use a schedule with 5 fields"),
        ("0 0 9 * * 1", "UTC", "Use a schedule with 5 fields"),
        ("61 9 * * *", "UTC", "isn't a schedule we understand"),
        ("0 9 * * *", "Mars/Olympus", "Unknown time zone"),
        ("0 9 * * *", "", "Unknown time zone"),
    ],
)
def test_bad_schedules_are_refused(cron: str, timezone: str, error: str) -> None:
    with pytest.raises(BadRequest, match=error):
        check_schedule(cron, timezone)


def test_a_good_schedule_passes() -> None:
    check_schedule("*/15 8-18 * * mon-fri", "Asia/Karachi")

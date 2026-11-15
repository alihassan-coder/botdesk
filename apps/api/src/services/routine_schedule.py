"""When a routine runs: a 5-field cron line ("0 9 * * 1-5") read in an IANA time zone.

Pure functions, no database. The cron line is walked in the zone's wall-clock time, so
"every day at 09:00" stays at 09:00 across daylight saving changes. On the day the clocks
spring forward, a time that doesn't exist (02:30) runs an hour later, once; on the day they
fall back, a time that happens twice runs the first time only.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from src.core.errors import BadRequest


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise BadRequest(f"Unknown time zone: {timezone or 'none'}.") from error


def check_schedule(cron: str, timezone: str) -> None:
    """Raise BadRequest unless `cron` is a valid 5-field line and `timezone` a known zone."""
    if len(cron.split()) != 5:
        raise BadRequest("Use a schedule with 5 fields: minute hour day month weekday.")
    if not croniter.is_valid(cron):
        raise BadRequest(f"“{cron}” isn't a schedule we understand.")
    _zone(timezone)


def next_run(cron: str, timezone: str, *, after: datetime) -> datetime:
    """The first moment strictly after `after` (aware) when the schedule is due, in UTC."""
    zone = _zone(timezone)
    wall = after.astimezone(zone).replace(tzinfo=None)
    times = croniter(cron, wall)
    while True:
        local: datetime = times.get_next(datetime)
        # fold=0: a time that happens twice is its first; one that doesn't exist reads with the
        # offset before the change, which lands an hour later on the clock.
        moment = local.replace(tzinfo=zone).astimezone(UTC)
        if moment > after:
            return moment

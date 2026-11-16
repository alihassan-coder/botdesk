"""When a routine runs: a 5-field cron line ("0 9 * * 1-5") read in an IANA time zone.

Pure functions, no database. The cron line is walked in the zone's wall-clock time, so
"every day at 09:00" stays at 09:00 across daylight saving changes. On the day the clocks
spring forward, a time that doesn't exist (02:30) runs an hour later, once; on the day they
fall back, a time that happens twice runs the first time only.

A schedule must name fixed times (no random or hashed "R"/"H" fields), match some date (not
"30 February") and leave at least `MIN_GAP` between runs.
"""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterError, croniter

from src.core.errors import BadRequest


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise BadRequest(f"Unknown time zone: {timezone or 'none'}.") from error


MIN_GAP = timedelta(minutes=5)
# A random or hashed value ("R", "H", "H/2", "H(0-29)") in a field, but not a name like "THU".
_RANDOM = re.compile(r"(^|,)[RH]($|[/(,])", re.IGNORECASE)
# Far enough ahead to see every gap: all of one day's times, and the step into the next day.
_GAP_WINDOW = timedelta(days=1, hours=1)
_GAP_REFERENCE = datetime(2026, 1, 1)  # wall-clock time, no zone


def check_schedule(cron: str, timezone: str) -> None:
    """Raise BadRequest unless `cron` is a valid 5-field line of fixed times that comes at least
    `MIN_GAP` apart, and `timezone` a known zone."""
    fields = cron.split()
    if len(fields) != 5:
        raise BadRequest("Use a schedule with 5 fields: minute hour day month weekday.")
    if any(_RANDOM.search(field) for field in fields):
        raise BadRequest("Use fixed times in the schedule: random or hashed fields (R, H) aren't supported.")
    if not croniter.is_valid(cron):
        raise BadRequest(f"“{cron}” isn't a schedule we understand.")
    _zone(timezone)
    _check_gaps(cron)


def _check_gaps(cron: str) -> None:
    """Walk the schedule's wall-clock times for a day: it must come at all, and never twice
    within `MIN_GAP`."""
    try:
        times = croniter(cron, _GAP_REFERENCE)
        previous: datetime = times.get_next(datetime)
        end = previous + _GAP_WINDOW
        while previous <= end:
            current: datetime = times.get_next(datetime)
            if current - previous < MIN_GAP:
                raise BadRequest("Routines run at most every 5 minutes: space the times at least 5 minutes apart.")
            previous = current
    except CroniterError as error:
        raise BadRequest(f"“{cron}” never comes: no date matches it.") from error


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

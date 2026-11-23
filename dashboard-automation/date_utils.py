"""
Europe/London calendar-day helpers for the dashboard job.

Comparisons in the brief are all in Europe/London "calendar days", but
calling Stripe/PostHog needs real UTC instants for date-range filters.
The tricky part is the two days a year where London's UTC offset changes
mid-day (BST <-> GMT).

Two deliberately separate kinds of function below:
 - Calendar-only arithmetic (add days, find a week's Monday, clamp "same day
   last month") works on plain `date` objects with no timezone involved at
   all - a calendar day is a calendar day regardless of DST.
 - Converting a calendar day to a real instant (`london_day_range_utc`)
   builds a timezone-aware `datetime` directly in the Europe/London zone and
   lets Python's own tzdata (via `zoneinfo`) work out the correct UTC
   offset for that specific day, rather than hand-rolling BST/GMT rules.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def _parse(date_str: str) -> date:
    return date.fromisoformat(date_str)


def to_london_date_string(instant: datetime) -> str:
    """Formats a real instant as its Europe/London calendar date (`YYYY-MM-DD`)."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(LONDON).strftime("%Y-%m-%d")


def london_midnight_utc(date_str: str) -> datetime:
    """The real UTC instant for 00:00 on a London calendar date."""
    d = _parse(date_str)
    local_midnight = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=LONDON)
    return local_midnight.astimezone(timezone.utc)


def london_day_range_utc(date_str: str) -> tuple[datetime, datetime]:
    """The `[start, end)` real-instant range covering a full London calendar day."""
    start = london_midnight_utc(date_str)
    end = london_midnight_utc(add_london_calendar_days(date_str, 1))
    return start, end


def add_london_calendar_days(date_str: str, delta: int) -> str:
    """Adds (or subtracts) whole calendar days - pure calendar arithmetic, no timezone involved."""
    return (_parse(date_str) + timedelta(days=delta)).isoformat()


def yesterday_london(now: datetime | None = None) -> str:
    """Yesterday's London date, relative to a real instant (defaults to now)."""
    now = now or datetime.now(timezone.utc)
    return add_london_calendar_days(to_london_date_string(now), -1)


def london_week_start(date_str: str) -> str:
    """The Monday on or before this date - start of the brief's Monday-start week."""
    d = _parse(date_str)
    return (d - timedelta(days=d.isoweekday() - 1)).isoformat()


def same_london_weekday_last_week(date_str: str) -> str:
    """The same point in the previous week (exactly 7 days earlier)."""
    return add_london_calendar_days(date_str, -7)


def london_month_start(date_str: str) -> str:
    """The 1st of this date's month."""
    return _parse(date_str).replace(day=1).isoformat()


def _days_in_month(year: int, month: int) -> int:
    next_month_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month_first - date(year, month, 1)).days


def same_london_day_last_month(date_str: str) -> str:
    """
    The same day number in the previous month, clamped if that month is
    shorter (31 March -> 28/29 February, never rolling into March).
    """
    d = _parse(date_str)
    prev_month = 12 if d.month == 1 else d.month - 1
    prev_year = d.year - 1 if d.month == 1 else d.year
    clamped_day = min(d.day, _days_in_month(prev_year, prev_month))
    return date(prev_year, prev_month, clamped_day).isoformat()


def london_month_label(date_str: str) -> str:
    """The `YYYY-MM` label for a date, used to bucket the 12-month series."""
    d = _parse(date_str)
    return f"{d.year:04d}-{d.month:02d}"


def is_london_month_start(date_str: str) -> bool:
    """Whether `date_str` is the 1st of its London calendar month."""
    return _parse(date_str).day == 1


def dates_between_inclusive(start: str, end: str) -> list[str]:
    out = []
    current = start
    while current <= end:
        out.append(current)
        current = add_london_calendar_days(current, 1)
    return out

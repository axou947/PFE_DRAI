"""NYSE trading calendar, small and dependency-free (pandas only).

The daily job publishes after each US close, so "which day should the track record hold?" needs the
exchange's holidays. Regular holidays follow the exchange's rules (a Saturday holiday is observed on
the Friday, a Sunday one on the Monday, except New Year's Day on a Saturday, which is not observed);
the few exceptional closures since 2000 are listed by hand. Early closes (half days) are open days.
"""

from datetime import UTC, datetime, time

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    sunday_to_monday,
)
from pandas.tseries.holiday import nearest_workday as _nearest_workday

#: Closures outside the rules: 9/11, national days of mourning, Hurricane Sandy.
EXCEPTIONAL_CLOSURES = [
    *pd.bdate_range("2001-09-11", "2001-09-14"),
    pd.Timestamp("2004-06-11"),  # Ronald Reagan
    pd.Timestamp("2007-01-02"),  # Gerald Ford
    pd.Timestamp("2012-10-29"),  # Hurricane Sandy
    pd.Timestamp("2012-10-30"),
    pd.Timestamp("2018-12-05"),  # George H. W. Bush
    pd.Timestamp("2025-01-09"),  # Jimmy Carter
]

#: New York close, in UTC (16:00 EST in winter, 21:00 UTC in summer: 21:00 covers both).
CLOSE_UTC = time(21, 0)
#: The next session opens at 09:30 New York time, 14:30 UTC in winter, 13:30 UTC in summer.
OPEN_UTC = time(13, 30)


def _new_year_observance(day: pd.Timestamp) -> pd.Timestamp | None:
    """Sunday -> Monday; a Saturday New Year's Day is not observed on the Friday (31 December is open)."""
    return None if day.weekday() == 5 else sunday_to_monday(day)


class _NyseHolidays(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year's Day", month=1, day=1, observance=_new_year_observance),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=_nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=_nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=_nearest_workday),
    ]


_CALENDAR = _NyseHolidays()
_CACHE: dict[tuple[int, int], frozenset[pd.Timestamp]] = {}


def holidays(first_year: int, last_year: int) -> frozenset[pd.Timestamp]:
    """Every weekday the exchange is closed from 1 January of `first_year` to 31 December of `last_year`."""
    key = (first_year, last_year)
    if key not in _CACHE:
        found = _CALENDAR.holidays(start=f"{first_year}-01-01", end=f"{last_year}-12-31")
        exceptional = [d for d in EXCEPTIONAL_CLOSURES if first_year <= d.year <= last_year]
        # A rule can land on a weekend only through the observance; keep weekdays.
        _CACHE[key] = frozenset(d for d in [*found, *exceptional] if d.weekday() < 5)
    return _CACHE[key]


def is_session(day) -> bool:
    """True when the exchange is open on this calendar day."""
    day = pd.Timestamp(day).normalize()
    return day.weekday() < 5 and day not in holidays(day.year, day.year)


def holiday_name(day) -> str | None:
    """Why a weekday is closed ('Good Friday', 'Thanksgiving Day', ...), None when it is open or a weekend."""
    day = pd.Timestamp(day).normalize()
    if day.weekday() >= 5:
        return None
    named = _CALENDAR.holidays(start=day, end=day, return_name=True)
    if len(named):
        return str(named.iloc[0])
    return "Exceptional closure" if day in EXCEPTIONAL_CLOSURES else None


def sessions(start, end) -> pd.DatetimeIndex:
    """Open days from `start` to `end`, both included."""
    days = pd.bdate_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize())
    closed = holidays(days[0].year, days[-1].year) if len(days) else frozenset()
    return pd.DatetimeIndex([d for d in days if d not in closed])


def previous_session(day, inclusive: bool = False) -> pd.Timestamp:
    """The last open day before `day` (or `day` itself when `inclusive` and it is open)."""
    day = pd.Timestamp(day).normalize()
    if inclusive and is_session(day):
        return day
    day -= pd.Timedelta(days=1)
    while not is_session(day):
        day -= pd.Timedelta(days=1)
    return day


def next_session(day) -> pd.Timestamp:
    """The first open day after `day`."""
    day = pd.Timestamp(day).normalize() + pd.Timedelta(days=1)
    while not is_session(day):
        day += pd.Timedelta(days=1)
    return day


def sessions_between(after, until) -> int:
    """Open days in (`after`, `until`]: how many sessions `after` is behind `until`."""
    after, until = pd.Timestamp(after).normalize(), pd.Timestamp(until).normalize()
    if after >= until:
        return 0
    return len(sessions(after + pd.Timedelta(days=1), until))


def _utc(day: pd.Timestamp, at: time) -> datetime:
    return datetime.combine(day.date(), at, tzinfo=UTC)


def session_close(day) -> datetime:
    """When the data of a session exists, in UTC (the publication job runs after it)."""
    return _utc(pd.Timestamp(day), CLOSE_UTC)


def next_open(day) -> datetime:
    """Opening of the session after `day`, in UTC: the day's entry should be out before it."""
    return _utc(next_session(day), OPEN_UTC)


def last_closed_session(now: datetime | pd.Timestamp) -> pd.Timestamp:
    """The most recent session whose close has passed at `now` (a timezone-aware moment)."""
    moment = pd.Timestamp(now)
    moment = moment.tz_localize("UTC") if moment.tzinfo is None else moment.tz_convert("UTC")
    today = moment.tz_localize(None).normalize()
    if is_session(today) and moment >= pd.Timestamp(session_close(today)):
        return today
    return previous_session(today)


def holiday_dates(start, end) -> list[str]:
    """ISO dates of the weekday closures in a range, for the public page's own lateness check."""
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    return sorted(d.date().isoformat() for d in holidays(first.year, last.year) if first <= d <= last)


__all__ = [
    "CLOSE_UTC",
    "EXCEPTIONAL_CLOSURES",
    "holiday_dates",
    "holiday_name",
    "holidays",
    "is_session",
    "last_closed_session",
    "next_open",
    "next_session",
    "previous_session",
    "session_close",
    "sessions",
    "sessions_between",
]

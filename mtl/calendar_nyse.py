"""NYSE trading calendar: maturity dates and holiday rolls.

Full-day closures come from the exchange's own rules, so the calendar works for any year without edits:
New Year's Day, Martin Luther King Jr. Day (third Monday of January, from 1998), Washington's Birthday
(third Monday of February), Good Friday, Memorial Day (last Monday of May), Juneteenth (from 2022),
Independence Day, Labor Day (first Monday of September), Thanksgiving (fourth Thursday of November) and
Christmas. A holiday on a Saturday is observed the Friday before, on a Sunday the Monday after, except
New Year's Day on a Saturday, which is not made up. Unscheduled closures (a national day of mourning,
a storm) can't be predicted: add them to EXTRA_CLOSURES when the exchange announces one."""
from datetime import date, timedelta
from functools import lru_cache

EXTRA_CLOSURES = {
    "2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14",   # September 11
    "2004-06-11",                                              # President Reagan's funeral
    "2007-01-02",                                              # President Ford's funeral
    "2012-10-29", "2012-10-30",                                # Hurricane Sandy
    "2018-12-05",                                              # President George H. W. Bush's funeral
    "2025-01-09",                                              # President Carter's funeral
}


def _easter(y):
    """Easter Sunday (Gregorian), anonymous computus."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth(y, month, weekday, n):
    """The n-th `weekday` (Mon=0) of the month; n=-1 is the last."""
    if n > 0:
        d = date(y, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = (date(y, month, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d):
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


@lru_cache(maxsize=None)
def holidays(y):
    """The NYSE's scheduled full-day closures in year y, as 'YYYY-MM-DD' strings."""
    out = []
    ny = date(y, 1, 1)
    if ny.weekday() != 5:              # a Saturday New Year's Day isn't made up on the Friday before
        out.append(_observed(ny))
    if y >= 1998:
        out.append(_nth(y, 1, 0, 3))   # Martin Luther King Jr. Day
    out.append(_nth(y, 2, 0, 3))       # Washington's Birthday
    out.append(_easter(y) - timedelta(days=2))   # Good Friday
    out.append(_nth(y, 5, 0, -1))      # Memorial Day
    if y >= 2022:
        out.append(_observed(date(y, 6, 19)))   # Juneteenth
    out.append(_observed(date(y, 7, 4)))
    out.append(_nth(y, 9, 0, 1))       # Labor Day
    out.append(_nth(y, 11, 3, 4))      # Thanksgiving
    out.append(_observed(date(y, 12, 25)))
    return frozenset(d.isoformat() for d in out)


def known(d) -> bool:
    """Kept for callers: the rules cover every year."""
    return True


def is_trading_day(d) -> bool:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    s_ = d.isoformat()
    return d.weekday() < 5 and s_ not in holidays(d.year) and s_ not in EXTRA_CLOSURES


def next_trading_day(d):
    if isinstance(d, str):
        d = date.fromisoformat(d)
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def previous_trading_day(d):
    if isinstance(d, str):
        d = date.fromisoformat(d)
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def most_recent_completed_session(as_of=None) -> str:
    """The most recently completed NYSE session's date, as of `as_of` (default
    today). Used to pick S for a run that happens before today's close exists
    - today itself is never returned, even if today is a trading day, since a
    pre-close run has no close print for today yet."""
    d = date.fromisoformat(as_of) if isinstance(as_of, str) else (as_of or date.today())
    return previous_trading_day(d).isoformat()


def add_trading_days(start, n: int) -> str:
    """n NYSE sessions after `start`, skipping weekends and holidays."""
    d = date.fromisoformat(start) if isinstance(start, str) else start
    for _ in range(n):
        d = next_trading_day(d)
    return d.isoformat()


def maturities(s: str, horizons=(1, 5, 10)) -> dict:
    return {h: add_trading_days(s, h) for h in horizons}


def week_ended(d) -> bool:
    """True when d is the week's last NYSE session: the next session falls in a later ISO week
    (a Friday, or a Thursday before a Friday holiday such as Good Friday)."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return next_trading_day(d).isocalendar()[:2] != d.isocalendar()[:2]


def week_end_session(d) -> str:
    """The last NYSE session of d's ISO week, on or after d (d itself when it is that session)."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    if not is_trading_day(d):
        d = next_trading_day(d)
    while not week_ended(d):
        d = next_trading_day(d)
    return d.isoformat()


def month_end_session(d) -> str:
    """The last NYSE session of d's month."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    x = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    while not is_trading_day(x):
        x -= timedelta(days=1)
    return x.isoformat()

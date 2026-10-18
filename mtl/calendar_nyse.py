"""NYSE trading calendar: maturity dates and holiday rolls."""
from datetime import date, timedelta

# Full-day closures. Extend as years are added.
HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
}
HOLIDAY_YEARS = (2026, 2027, 2028)   # years whose closures are listed above


def known(d) -> bool:
    """True when d's year has its closures listed (outside them only weekends are skipped)."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.year in HOLIDAY_YEARS


def is_trading_day(d) -> bool:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


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

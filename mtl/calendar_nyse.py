"""NYSE trading calendar: maturity dates and holiday rolls."""
from datetime import date, timedelta

# Full-day closures. Extend as years are added.
HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


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

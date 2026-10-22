import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
from momentum_scan import minute_bar  # noqa: E402

NY = ZoneInfo('America/New_York')


def at(h, m, day=21):
    return datetime(2026, 10, day, h, m, tzinfo=NY)


def test_builds_the_day_from_regular_session_minutes():
    rows = [(at(9, 29), 1, 99, 0.5, 1),            # before the open: ignored
            (at(9, 30), 10, 11, 9, 10.5),
            (at(12, 0), 10.5, 13, 10, 12),
            (at(15, 59), 12, 12.5, 11.5, 12.25),
            (at(16, 0), 12.25, 50, 1, 40),          # after the close: ignored
            (at(15, 0, day=20), 5, 60, 0.1, 5)]     # the day before: ignored
    assert minute_bar('2026-10-21', rows) == ('2026-10-21', 10.0, 13.0, 9.0, 12.25)


def test_none_without_minutes_that_day():
    assert minute_bar('2026-10-21', [(at(15, 0, day=20), 5, 6, 4, 5)]) is None
    assert minute_bar('2026-10-21', [(at(10, 0), 5, 6, 4, float('nan'))]) is None

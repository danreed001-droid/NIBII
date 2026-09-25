"""most_recent_completed_session: picks S for a run before today's close exists."""
from mtl.calendar_nyse import most_recent_completed_session


def test_weekday_returns_prior_session():
    assert most_recent_completed_session('2026-09-23') == '2026-09-22'


def test_monday_rolls_back_over_the_weekend():
    assert most_recent_completed_session('2026-09-28') == '2026-09-25'


def test_day_after_holiday_rolls_back_past_it():
    assert most_recent_completed_session('2026-09-08') == '2026-09-04'


def test_never_returns_today_even_if_today_is_a_trading_day():
    assert most_recent_completed_session('2026-09-24') != '2026-09-24'

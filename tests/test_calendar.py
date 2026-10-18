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


def test_week_end_sessions_follow_nyse_holidays():
    from mtl.calendar_nyse import month_end_session, next_trading_day, week_end_session, week_ended
    assert week_ended('2026-10-16') and not week_ended('2026-10-15')          # a normal Friday / Thursday
    assert week_ended('2026-12-24') and week_ended('2027-03-25')               # Thursdays before Christmas / Good Friday
    assert week_end_session('2026-10-14') == '2026-10-16'
    assert week_end_session('2027-03-23') == '2027-03-25'
    assert week_end_session('2026-10-17') == '2026-10-23'                     # a Saturday: the next week's last session
    assert next_trading_day('2027-01-15').isoformat() == '2027-01-19'          # Martin Luther King Day Monday
    assert month_end_session('2026-12-10') == '2026-12-31'
    assert month_end_session('2027-04-02') == '2027-04-30'

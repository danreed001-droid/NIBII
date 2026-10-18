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


def test_holidays_follow_the_exchange_rules_in_any_year():
    from mtl.calendar_nyse import holidays, is_trading_day
    assert set(holidays(2027)) == {'2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31',
                                   '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24'}
    assert '2033-01-01' not in holidays(2033) and is_trading_day('2032-12-31')   # Saturday New Year: not made up
    assert '2034-01-02' in holidays(2034)                                         # Sunday New Year: Monday off
    assert '2030-04-19' in holidays(2030) and '2041-04-19' in holidays(2041)      # Good Friday from Easter
    assert '2021-06-18' not in holidays(2021) and '2022-06-20' in holidays(2022)  # Juneteenth from 2022
    assert not is_trading_day('2025-01-09')                                       # an unscheduled closure


def test_last_closed_session_waits_for_the_close():
    import importlib.util, os
    from datetime import datetime, timezone
    spec = importlib.util.spec_from_file_location(
        'momentum_scan', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'momentum_scan.py'))
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    assert ms.last_closed_session(datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc)) == '2026-10-16'   # Fri 6 pm ET
    assert ms.last_closed_session(datetime(2026, 10, 16, 19, 0, tzinfo=timezone.utc)) == '2026-10-15'   # Fri 3 pm ET
    assert ms.last_closed_session(datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)) == '2026-10-16'   # Sunday
    assert ms.last_closed_session(datetime(2027, 1, 18, 23, 0, tzinfo=timezone.utc)) == '2027-01-15'    # MLK Day

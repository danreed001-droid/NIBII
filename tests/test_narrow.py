from datetime import date, timedelta

from mtl.narrow import (NARROW_DAYS, NARROW_DELAY, apply_narrow, narrow_cash_days, narrow_reading, narrow_state,
                        narrow_warnings)


def _cal(n):
    d0 = date(2020, 1, 1)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def _series(cal, f):
    return {d: f(i) for i, d in enumerate(cal)}


def test_warning_needs_all_three_parts():
    cal = _cal(400)
    spy = _series(cal, lambda i: 100 + i * 0.1)                 # steady new highs
    rsp_lag = _series(cal, lambda i: 100 + i * 0.1 - (i - 300) * 0.2 if i > 300 else 100 + i * 0.1)   # lags after day 300
    calm = _series(cal, lambda i: 14.0)
    warn = narrow_warnings(spy, rsp_lag, calm, cal)
    assert warn and min(warn) > cal[300]
    # no lag: no warning
    assert narrow_warnings(spy, spy, calm, cal) == []
    # a VIX well above its 3-month low: no warning
    rising = _series(cal, lambda i: 10 + i * 0.05)            # 3 points above its 3-month low every day
    assert narrow_warnings(spy, rsp_lag, rising, cal) == []
    # SPY far below its 52-week high: no warning
    falling = _series(cal, lambda i: 200 - i * 0.2)
    assert narrow_warnings(falling, _series(cal, lambda i: 200 - i * 0.3), calm, cal) == []


def test_reading_matches_the_warning():
    cal = _cal(400)
    spy = _series(cal, lambda i: 100 + i * 0.1)
    rsp = _series(cal, lambda i: 100 + i * 0.1 - (i - 300) * 0.2 if i > 300 else 100 + i * 0.1)
    vix = _series(cal, lambda i: 14.0)
    warn = set(narrow_warnings(spy, rsp, vix, cal))
    for k in (260, 320, 399):
        r = narrow_reading(spy, rsp, vix, cal, k)
        assert r['on'] == (cal[k] in warn)
    assert narrow_reading(spy, rsp, vix, cal, 100) is None


def test_cash_week_starts_a_week_later_and_lasts_a_week():
    cal = _cal(60)
    cash = narrow_cash_days([cal[10]], cal)
    assert sorted(cash) == cal[11 + NARROW_DELAY:11 + NARROW_DELAY + NARROW_DAYS]
    # a repeat warning extends it
    cash2 = narrow_cash_days([cal[10], cal[12]], cal)
    assert sorted(cash2) == cal[11 + NARROW_DELAY:13 + NARROW_DELAY + NARROW_DAYS]


def test_apply_overrides_whatever_the_plan_holds_then_hands_back():
    cal = _cal(20)
    modes = {d: ('TLT' if 8 <= i < 10 else 'boost') for i, d in enumerate(cal)}
    cash = set(cal[6:11])
    m, why = apply_narrow(modes, {}, cash, cal)
    assert all(m[d] == 'BIL' for d in cal[6:11])
    assert m[cal[11]] == 'boost' and m[cal[5]] == 'boost'
    assert why[cal[6]] == 'narrow' and why[cal[11]] == 'narrow-end'
    assert modes[cal[8]] == 'TLT'          # the input is not changed


def test_state_reports_the_scheduled_week():
    cal = _cal(40)
    warn = [cal[10]]
    cash = narrow_cash_days(warn, cal)
    s = narrow_state(warn, cash, cal, 10)
    assert s['on'] and s['cash'] == [cal[16], cal[20]] and not s['inCash']
    s2 = narrow_state(warn, cash, cal, 18)
    assert s2['inCash'] and s2['cash'] == [cal[16], cal[20]] and not s2['on']
    s3 = narrow_state(warn, cash, cal, 30)
    assert s3['cash'] is None and s3['last'] == cal[10]

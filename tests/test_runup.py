import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import runup  # noqa: E402


def _cal(n, start=date(2020, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _prices(cal, spy_end, stock_end):
    """SPY and a stock flat until the last 42 sessions (stock) / 126 sessions (SPY), then a straight line to the end value."""
    n = len(cal)
    spy = {d: 100.0 + (spy_end - 100.0) * max(0, i - (n - 127)) / 126 for i, d in enumerate(cal)}
    st = {d: 10.0 + (stock_end - 10.0) * max(0, i - (n - 43)) / 42 for i, d in enumerate(cal)}
    return {'SPY': spy, 'A': st}


def test_blocks_a_big_run_only_while_spy_is_down_over_six_months():
    cal = _cal(300)
    k = len(cal) - 1
    r = runup.RunUp(_prices(cal, 90.0, 16.0), cal)        # SPY -10% over 6 months, the stock +60% in 2 months
    assert r.falling(k) and r.run('A', k) > 0.5 and r.blocked('A', k)
    assert not r.buy_ok()('A', k) and r.info(k, ['A'])['blocked'] == ['A']
    r = runup.RunUp(_prices(cal, 110.0, 16.0), cal)       # SPY up: not blocked
    assert not r.falling(k) and not r.blocked('A', k) and r.buy_ok()('A', k)
    r = runup.RunUp(_prices(cal, 90.0, 14.0), cal)        # only +40%: not blocked
    assert r.falling(k) and not r.blocked('A', k)


def test_needs_a_year_of_history_and_chains_the_other_filters():
    cal = _cal(200)
    r = runup.RunUp(_prices(cal, 90.0, 16.0), cal)
    assert not r.blocked('A', len(cal) - 1)               # under a year of sessions: off
    cal = _cal(300)
    r = runup.RunUp(_prices(cal, 110.0, 16.0), cal)
    assert r.buy_ok(lambda t, k: False)('A', len(cal) - 1) is False

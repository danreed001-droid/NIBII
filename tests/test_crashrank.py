import math
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import crashrank  # noqa: E402


def _cal(n, start=date(2018, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _spy(cal, path):
    """SPY following path(i) -> close."""
    return {d: path(i) for i, d in enumerate(cal)}


def _crash_then_recover(n, crash_at, low_at):
    """Flat at 100, a straight fall to 60 (-40%) from crash_at to low_at, then a straight climb."""
    def p(i):
        if i < crash_at:
            return 100.0
        if i <= low_at:
            return 100.0 - 40.0 * (i - crash_at) / (low_at - crash_at)
        return 60.0 + 0.3 * (i - low_at)
    return p


def _stocks(cal, m=40):
    """m stocks: stock j has daily swings growing with j, sits further under its high with j and is cheaper with j."""
    out = {}
    for j in range(m):
        amp = 0.002 + 0.001 * j
        base = 200.0 - 4.0 * j
        out[f'S{j:02d}'] = {d: base * (1 - 0.01 * j * min(1.0, i / 300)) * (1 + amp * (1 if i % 2 else -1)) for i, d in enumerate(cal)}
    return out


def test_off_without_a_crash():
    cal = _cal(600)
    r = crashrank.CrashRank({'SPY': _spy(cal, lambda i: 100.0 + 0.05 * i)}, cal)
    assert not any(r.on_days())


def test_on_after_a_crash_once_spy_turns_up_and_off_again_after_the_window():
    cal = _cal(900)
    r = crashrank.CrashRank({'SPY': _spy(cal, _crash_then_recover(900, 300, 400))}, cal)
    on = r.on_days()
    assert not on[350]              # still falling: under its 50-day average
    assert on[420]                  # 20 sessions after the low, back above its 50-day average, crash within 126 sessions
    last_crash = max(i for i in range(252, 900) if r.closes('SPY')[i] <= 0.7 * max(r.closes('SPY')[i - 251:i + 1]))
    assert not on[last_crash + 127]


def test_no_turn_up_no_rule():
    cal = _cal(900)
    r = crashrank.CrashRank({'SPY': _spy(cal, _crash_then_recover(900, 300, 400))}, cal)
    k = 380
    s = r.closes('SPY')
    assert s[k] < sum(s[k - 49:k + 1]) / 50
    assert not r.on(k)


def test_reorder_puts_the_rebound_stocks_first_and_qualifies_them():
    cal = _cal(900)
    px = {'SPY': _spy(cal, _crash_then_recover(900, 300, 400)), **_stocks(cal)}
    r = crashrank.CrashRank(px, cal)
    k = 420
    assert r.on(k)
    rows = [(t, 1.0 - 0.01 * i, i < 5) for i, t in enumerate(sorted(t for t in px if t != 'SPY'))]
    out = r.reorder()(k, rows)
    front = [t for t, _, _ in out[:crashrank.N]]
    assert front == r.front(k, [t for t, _, _ in rows])
    assert set(front) == {f'S{j:02d}' for j in range(30, 40)}     # the most volatile, deepest, cheapest ten
    assert all(q for _, _, q in out[:crashrank.N])
    assert [t for t, _, _ in out[crashrank.N:]] == [t for t, _, _ in rows if t not in set(front)]   # the rest in order
    assert len(out) == len(rows)


def test_leaves_the_order_alone_while_off_or_with_too_few_stocks():
    cal = _cal(900)
    px = {'SPY': _spy(cal, _crash_then_recover(900, 300, 400)), **_stocks(cal, m=20)}
    r = crashrank.CrashRank(px, cal)
    rows = [(t, 1.0, True) for t in sorted(t for t in px if t != 'SPY')]
    assert r.reorder()(420, rows) == rows        # 20 stocks: fewer than MIN_STOCKS
    assert r.reorder()(350, rows) == rows        # off


def test_twelve_month_settings_double_the_times():
    assert crashrank.settings(126) == dict(drop=0.30, win=126, up=50, n=10)
    assert crashrank.settings(252) == dict(drop=0.30, win=252, up=100, n=10)


def test_info_reports_the_state():
    cal = _cal(900)
    px = {'SPY': _spy(cal, _crash_then_recover(900, 300, 400)), **_stocks(cal)}
    r = crashrank.CrashRank(px, cal)
    i = r.info(420, [t for t in px if t != 'SPY'])
    assert i['on'] and len(i['front']) == crashrank.N and i['since'] == crashrank.START
    assert i['spyOffHigh'] < -0.3 + 0.2 and math.isfinite(i['spyVsAvg'])

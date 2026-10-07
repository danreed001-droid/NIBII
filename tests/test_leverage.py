"""Trend-gated leverage - synthetic prices, no network."""
from datetime import date, timedelta

from mtl.leverage import gated_curve, trend_up


def cal(n, start='2024-01-01'):
    d0, out, d = date.fromisoformat(start), [], 0
    while len(out) < n:
        day = d0 + timedelta(days=d)
        if day.weekday() < 5:
            out.append(day.isoformat())
        d += 1
    return out


def test_trend_up_flips_when_price_crosses_its_average():
    c = cal(30)
    px = {d: 100 + i for i, d in enumerate(c[:20])}
    px.update({d: 80 - i for i, d in enumerate(c[20:])})
    up = trend_up(px, c, n=5)
    assert up[c[2]] is True          # not enough history yet counts as up
    assert up[c[19]] is True and up[c[25]] is False


def test_gated_curve_levers_up_in_uptrend_and_cuts_back_in_downtrend():
    c = cal(40)
    plan = [[d, 1.01 ** i] for i, d in enumerate(c)]   # +1% a session
    cash = {d: 1.0 for d in c}
    up_all = {d: True for d in c}
    down_all = {d: False for d in c}
    hi = gated_curve(plan, cash, c, up_all, hi=1.5, lo=0.6, rate=0.0)
    lo = gated_curve(plan, cash, c, down_all, hi=1.5, lo=0.6, rate=0.0)
    assert abs(hi[1][1] - 1.015) < 1e-12 and abs(lo[1][1] - 1.006) < 1e-12


def test_leverage_changes_only_after_the_week_ends_and_borrowing_costs():
    c = cal(10)                       # 2024-01-01 (Mon) .. 2024-01-12 (Fri)
    plan = [[d, 1.0] for d in c]      # flat plan: only the borrowing cost moves the account
    up = {d: True for d in c}
    up['2024-01-05'] = False          # first Friday turns the trend down
    out = dict(gated_curve(plan, {d: 1.0 for d in c}, c, up, hi=2.0, lo=0.5, rate=0.252))
    assert abs(out['2024-01-05'] - (1 - 0.001) ** 4) < 1e-12    # 1x borrowed, 0.1% a session, Tue-Fri
    assert out['2024-01-08'] == out['2024-01-05']               # Monday on: 0.5x, nothing borrowed


def test_account_never_goes_below_zero():
    c = cal(5)
    plan = [[c[0], 1.0], [c[1], 0.4], [c[2], 0.4]]
    out = gated_curve(plan, {d: 1.0 for d in c}, c, {d: True for d in c}, hi=2.0, lo=0.6, rate=0.0)
    assert out[1][1] == 0.0 and out[2][1] == 0.0

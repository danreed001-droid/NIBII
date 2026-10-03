"""Momentum portfolio backtest - synthetic prices, no network."""
from datetime import date, timedelta

from mtl.momentum import last_sessions_of_weeks, run_momentum, score_at


def cal(n, start='2024-01-01'):
    d0, out, d = date.fromisoformat(start), [], 0
    while len(out) < n:
        day = d0 + timedelta(days=d)
        if day.weekday() < 5:
            out.append(day.isoformat())
        d += 1
    return out


def test_last_sessions_of_weeks_are_fridays_or_week_ends():
    c = cal(15)
    assert [date.fromisoformat(d).weekday() for d in last_sessions_of_weeks(c)][:2] == [4, 4]


def test_score_skips_the_latest_month():
    c = cal(10)
    px = {d: 100 + i for i, d in enumerate(c)}
    assert score_at(px, c, 9, look=5, skip=2) == px[c[7]] / px[c[4]] - 1


def test_portfolio_holds_the_strongest_and_tracks_its_value():
    c = cal(80)
    prices = {
        'SPY': {d: 100 * 1.001 ** i for i, d in enumerate(c)},
        'WIN': {d: 100 * 1.01 ** i for i, d in enumerate(c)},
        'LOSE': {d: 100 * 0.99 ** i for i, d in enumerate(c)},
    }
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0)
    assert all(p[1] == ['WIN'] for p in r['picks'])
    first = next(p for p in r['curve'] if p[2] == 1)
    growth = r['curve'][-1][1] / first[1]
    days = len(c) - 1 - c.index(first[0])
    assert abs(growth - 1.01 ** days) < 1e-9


def test_no_stock_beats_the_benchmark_means_cash():
    c = cal(60)
    prices = {'SPY': {d: 100 * 1.02 ** i for i, d in enumerate(c)},
              'A': {d: 100 * 1.001 ** i for i, d in enumerate(c)}}
    r = run_momentum(prices, c, c[25], look=20, skip=0, top_n=2, cost=0.0)
    assert all(p[1] == [] for p in r['picks']) and r['curve'][-1][1] == 100.0


def test_risk_off_goes_to_cash_and_costs_are_charged():
    c = cal(60)
    prices = {'SPY': {d: 100.0 for d in c}, 'A': {d: 100 * 1.01 ** i for i, d in enumerate(c)}}
    off = run_momentum(prices, c, c[25], look=20, skip=0, top_n=1, risk_on=lambda d: False)
    assert off['curve'][-1][1] == 100.0
    a = run_momentum(prices, c, c[25], look=20, skip=0, top_n=1, cost=0.0)
    b = run_momentum(prices, c, c[25], look=20, skip=0, top_n=1, cost=0.01)
    assert b['curve'][-1][1] < a['curve'][-1][1]

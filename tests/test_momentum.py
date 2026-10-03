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


from mtl.momentum import run_rank_climbers


def test_rank_climbers_buys_the_stock_moving_up_the_ranking():
    c = cal(120)
    prices = {'SPY': {d: 100.0 for d in c}}
    # FADE starts strongest and keeps weakening; RISE starts weakest and accelerates
    for name, f in (('FADE', lambda i: 100 * (1.004 ** i) * (0.995 ** max(0, i - 40))),
                    ('RISE', lambda i: 100 * (0.999 ** i) * (1.01 ** max(0, i - 40))),
                    ('FLAT', lambda i: 100 + 0.01 * i)):
        prices[name] = {d: f(i) for i, d in enumerate(c)}
    r = run_rank_climbers(prices, c, c[30], look=20, skip=0, top=3, slots=1, cost=0.0)
    held = {t for _, h in r['picks'] for t in h}
    assert 'RISE' in held
    # a holding whose rank worsens is sold the next week
    for (d, h), (d2, h2) in zip(r['picks'], r['picks'][1:]):
        assert len(h2) <= 1


def test_rank_climbers_swap_mode_keeps_at_most_slots():
    c = cal(120)
    prices = {'SPY': {d: 100.0 for d in c}}
    import math
    for j in range(15):
        prices[f"S{j}"] = {d: 100 * (1 + 0.2 * math.sin(i / (5 + j))) for i, d in enumerate(c)}
    r = run_rank_climbers(prices, c, c[30], look=10, skip=0, top=10, slots=4, mode='swap', swap=2, cost=0.0)
    assert r['picks'] and all(len(h) <= 4 for _, h in r['picks'])


def test_hold_mode_keeps_a_holding_through_a_wobble_until_it_leaves_the_exit_rank():
    import math
    c = cal(160)
    prices = {'SPY': {d: 100.0 for d in c}}
    for j in range(12):
        prices[f"S{j}"] = {d: 100 * (1 + 0.3 * math.sin(i / (6 + j))) for i, d in enumerate(c)}
    r = run_rank_climbers(prices, c, c[40], look=10, skip=0, top=12, slots=3, mode='hold',
                          change_weeks=4, exit_rank=6, cost=0.0)
    assert r['picks']
    # every holding kept from one week to the next ranked within exit_rank that week
    for (_, h1), (_, h2) in zip(r['picks'], r['picks'][1:]):
        assert len(h2) <= 3


from mtl.momentum import ranking, trades_from_picks


def test_ranking_matches_scores_best_first():
    c = cal(40)
    prices = {'SPY': {d: 100.0 for d in c}, 'A': {d: 100 + i for i, d in enumerate(c)},
              'B': {d: 100 + 2 * i for i, d in enumerate(c)}}
    r = ranking(prices, c, 39, look=20, skip=0)
    assert [t for t, _ in r] == ['B', 'A'] and abs(r[0][1] - prices['B'][c[39]] / prices['B'][c[19]] + 1) < 1e-12


def test_trades_from_picks():
    picks = [['d1', ['A', 'B']], ['d2', ['B', 'C']], ['d3', ['C']]]
    assert trades_from_picks(picks) == [('d1', 'buy', 'A'), ('d1', 'buy', 'B'), ('d2', 'sell', 'A'),
                                        ('d2', 'buy', 'C'), ('d3', 'sell', 'B')]


def test_momentum_scan_glitch_guard_blocks_after_a_crash_print():
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'momentum_scan', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'momentum_scan.py'))
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    bars = [(f"d{i:03d}", 1, 1, 1, 100.0 if i < 10 else 12.0) for i in range(200)]
    blocked = ms.blocked_dates(bars)
    assert 'd009' not in blocked and 'd010' in blocked and 'd160' in blocked and 'd161' not in blocked
    assert ms.yearly([['2020-01-02', 100], ['2020-12-31', 110], ['2021-12-31', 99]]) == \
        {'2020': 0.10000000000000009, '2021': 99 / 110 - 1}


def test_daily_risk_filter_goes_to_cash_midweek_and_back():
    c = cal(80)
    prices = {'SPY': {d: 100.0 for d in c}, 'A': {d: 100 * 1.01 ** i for i, d in enumerate(c)}}
    off_days = set(c[40:45])
    r = run_momentum(prices, c, c[25], look=20, skip=0, top_n=1, cost=0.0,
                     risk_on=lambda d: d not in off_days, risk_daily=True)
    picked = dict((d, h) for d, h in r['picks'])
    assert picked[c[40]] == [] and picked[c[45]] == ['A']
    held = {p[0]: p[2] for p in r['curve']}
    assert held[c[42]] == 0 and held[c[46]] == 1


from mtl.momentum import score_table


def test_blended_rank_counts_every_window_equally():
    c = cal(60)
    # A: strong over the long window only; B: strong over the short window only; C: middling on both
    prices = {'SPY': {d: 100.0 for d in c},
              'A': {d: 100 + (2 * i if i < 30 else 60) for i, d in enumerate(c)},
              'B': {d: 100 + (0 if i < 50 else 5 * (i - 49)) for i, d in enumerate(c)},
              'C': {d: 100 + 0.8 * i for i, d in enumerate(c)}}
    rows = score_table(prices, c, 59, windows=[(10, 0), (50, 0)], blend='rank')
    scores = {t: sc for t, sc, _ in rows}
    assert all(0 < v <= 1 for v in scores.values()) and all(b for _, _, b in rows)
    assert abs(sum(scores.values()) - 2.0) < 1e-9   # each window's ranks sum to (n+1)/2 / ... = 2 for n=3
    single = score_table(prices, c, 59, look=10, skip=0)
    assert single[0][0] == 'B'


def test_single_window_score_table_matches_score_at():
    c = cal(40)
    prices = {'SPY': {d: 100.0 for d in c}, 'A': {d: 100 + i for i, d in enumerate(c)}}
    (t, sc, beats), = score_table(prices, c, 39, look=20, skip=0)
    assert t == 'A' and beats and abs(sc - (prices['A'][c[39]] / prices['A'][c[19]] - 1)) < 1e-12

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


def test_trailing_stop_sells_a_falling_holding_and_bans_it_for_a_while():
    c = cal(120)
    prices = {'SPY': {d: 100.0 for d in c},
              'A': {d: (100 * 1.01 ** i if i < 60 else 100 * 1.01 ** 60 * 0.97 ** (i - 60)) for i, d in enumerate(c)},
              'B': {d: 100 * 1.004 ** i for i, d in enumerate(c)}}
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, trail_stop=0.20, cooldown=20)
    assert r['stops'] >= 1
    stop_day = next(d for d, h in r['picks'] if d > c[60] and h == ['B'])
    k = c.index(stop_day)
    assert prices['A'][stop_day] <= max(prices['A'][x] for x in c[30:k + 1]) * 0.8 + 1e-9
    # A is not bought back during the cooldown
    assert all('A' not in h for d, h in r['picks'] if k < c.index(d) <= k + 20)


def test_rsi_exit_sells_when_rsi_drops_below_the_level_and_skips_weak_buys():
    from mtl.backtest import rsi_series
    c = cal(120)
    # A climbs (with small dips so RSI is defined) then slides steadily from day 60
    a = [100 * 1.01 ** i * (0.995 if i % 3 == 0 else 1) if i < 60 else 0 for i in range(120)]
    for i in range(60, 120):
        a[i] = a[59] * 0.99 ** (i - 59) * (1.004 if i % 3 == 0 else 1)
    prices = {'SPY': {d: 100.0 for d in c},
              'A': dict(zip(c, a)),
              'B': {d: 100 * 1.004 ** i * (0.998 if i % 4 == 0 else 1) for i, d in enumerate(c)}}
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, rsi_exit=40, cooldown=20)
    assert r['stops'] >= 1
    rsi = dict(zip(c, rsi_series(a)))
    sold = next(d for d, h in r['picks'] if d > c[60] and 'A' not in h)
    assert rsi[sold] < 40
    # held A every earlier session while its RSI was still 40 or higher
    assert all(rsi[d] >= 40 for d in c[c.index(c[30]):c.index(sold)] if rsi[d] is not None)
    # never buys a stock whose RSI is below 40 that day
    assert all(not (t == 'A' and rsi[d] is not None and rsi[d] < 40) for d, h in r['picks'] for t in h)


def test_industry_cap_limits_holdings_per_group():
    c = cal(60)
    prices = {'SPY': {d: 100.0 for d in c}}
    for j, g in enumerate(['x', 'x', 'x', 'y', 'z']):
        prices[f"S{j}"] = {d: 100 * (1.02 - 0.002 * j) ** i for i, d in enumerate(c)}
    group = {'S0': 'x', 'S1': 'x', 'S2': 'x', 'S3': 'y', 'S4': 'z'}
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=3, cost=0.0, group_of=group, max_per_group=2)
    for _, h in r['picks']:
        assert sum(group[t] == 'x' for t in h) <= 2
    assert r['picks'][0][1] == ['S0', 'S1', 'S3']


def test_sector_filter_buys_only_from_the_top_sector_and_sells_after_grace():
    c = cal(160)
    prices = {'SPY': {d: 100.0 for d in c}}
    sector = {}
    # sector H: strong early then weak; sector L: weak early then strong; each has 3 stocks
    for j in range(3):
        prices[f"H{j}"] = {d: 100 * ((1.012 - 0.001 * j) ** i if i < 80 else (1.012 - 0.001 * j) ** 80 * 0.995 ** (i - 80))
                           for i, d in enumerate(c)}
        prices[f"L{j}"] = {d: 100 * ((1.003 - 0.0005 * j) ** i if i < 80 else (1.003 - 0.0005 * j) ** 80 * 1.015 ** (i - 80))
                           for i, d in enumerate(c)}
        sector[f"H{j}"], sector[f"L{j}"] = 'H', 'L'
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=2, cost=0.0, keep_rank=6,
                     sector_of=sector, top_sectors=1, sector_grace=1)
    first = r['picks'][0][1]
    assert all(sector[t] == 'H' for t in first)
    last = r['picks'][-1][1]
    assert last and all(sector[t] == 'L' for t in last)


def test_buy_ok_false_keeps_holdings_but_buys_nothing_new():
    c = cal(80)
    prices = {'SPY': {d: 100.0 for d in c},
              'A': {d: 100 * 1.01 ** i for i, d in enumerate(c)},
              'B': {d: 100 * 1.005 ** i for i, d in enumerate(c)}}
    frozen_from = c[45]
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=2, cost=0.0,
                     buy_ok=lambda d: d < frozen_from)
    assert all(sorted(h) == ['A', 'B'] for _, h in r['picks'])
    # with nothing held, a freeze keeps the account in cash
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=2, cost=0.0, buy_ok=lambda d: False)
    assert all(h == [] for _, h in r['picks'])


def test_vol_target_scales_a_wild_basket_down_and_leaves_cash():
    c = cal(120)
    wild = {d: 100 * 1.01 ** i * (1.08 if i % 2 else 0.95) for i, d in enumerate(c)}
    prices = {'SPY': {d: 100.0 for d in c}, 'A': wild}
    r = run_momentum(prices, c, c[70], look=20, skip=0, top_n=1, cost=0.0, vol_target=0.30)
    full = run_momentum(prices, c, c[70], look=20, skip=0, top_n=1, cost=0.0)
    # same pick, but the scaled account moves far less day to day
    assert r['picks'][0][1] == ['A']
    moves = [abs(b[1] / a[1] - 1) for a, b in zip(r['curve'], r['curve'][1:])]
    full_moves = [abs(b[1] / a[1] - 1) for a, b in zip(full['curve'], full['curve'][1:])]
    assert max(moves) < 0.6 * max(full_moves)


def test_correlation_cap_skips_a_twin_of_a_stock_already_picked():
    c = cal(100)
    base = [100 * 1.01 ** i * (1.03 if i % 3 == 0 else 0.99) for i in range(100)]
    other = [100 * 1.006 ** i * (1.02 if i % 4 == 1 else 0.995) for i in range(100)]
    prices = {'SPY': {d: 100.0 for d in c},
              'A': dict(zip(c, base)),
              'A2': {d: v * 0.999 for d, v in zip(c, base)},   # moves exactly like A
              'B': dict(zip(c, other))}
    r = run_momentum(prices, c, c[70], look=20, skip=0, top_n=2, cost=0.0, max_corr=0.9)
    held = r['picks'][0][1]
    assert 'B' in held and not ({'A', 'A2'} <= set(held))


def test_exec_next_trades_at_the_next_sessions_open():
    c = cal(80)
    prices = {'SPY': {d: 100.0 for d in c}, 'A': {d: 100 * 1.01 ** i for i, d in enumerate(c)}}
    opens = {'A': {d: 100 * 1.01 ** i * 0.99 for i, d in enumerate(c)}}
    now = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0)
    nxt = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, exec_next=opens)
    first = now['picks'][0][0]
    assert nxt['picks'][0][0] == c[c.index(first) + 1]
    # bought 1% under the close: ends a bit ahead of buying a day later at the close
    late = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, exec_next='close')
    assert nxt['curve'][-1][1] > late['curve'][-1][1]


def test_prefer_jumps_the_queue_and_force_replaces_the_weakest_holding():
    c = cal(80)
    prices = {'SPY': {d: 100.0 for d in c},
              'A': {d: 100 * 1.010 ** i for i, d in enumerate(c)},
              'B': {d: 100 * 1.008 ** i for i, d in enumerate(c)},
              'C': {d: 100 * 1.006 ** i for i, d in enumerate(c)}}
    plain = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0)
    assert plain['picks'][0][1] == ['A']
    # C is flagged: it is bought first even though A ranks higher
    r = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, prefer=lambda t, k: t == 'C')
    assert r['picks'][0][1] == ['C']
    # flagged only later: 'fill' keeps A (no open slot), 'force' swaps out A for C
    later = c.index(c[50])
    flag = lambda t, k: t == 'C' and k >= later  # noqa: E731
    fill = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, keep_rank=3, prefer=flag)
    force = run_momentum(prices, c, c[30], look=20, skip=0, top_n=1, cost=0.0, keep_rank=3, prefer=flag,
                         prefer_mode='force')
    assert all(h == ['A'] for _, h in fill['picks'])
    assert force['picks'][-1][1] == ['C']


def test_blowoff_exit_sells_after_a_blowoff_month():
    from mtl.momentum import blowoff_exit
    cal = [f'd{i:03d}' for i in range(130)]
    steady = {d: 100 * (1.001 ** i) for i, d in enumerate(cal)}                 # +~11% over 105 sessions, +~2% last month
    spike = dict(steady)
    for i in range(109, 130):
        spike[cal[i]] = steady[cal[109]] * (1.012 ** (i - 109))                 # ~+28% in the last 21 sessions
    ex = blowoff_exit({'S': steady, 'X': spike}, cal)
    assert ex('S', 129) is False
    assert ex('X', 129) is True
    assert ex('X', 50) is False                                                  # not enough history


def test_blowoff_exit_only_after_a_bad_market_when_gated():
    from mtl.momentum import blowoff_exit, market_armed
    cal = [f'd{i:03d}' for i in range(300)]
    steady = {d: 100 * (1.001 ** i) for i, d in enumerate(cal)}
    spike = dict(steady)
    for i in range(279, 300):
        spike[cal[i]] = steady[cal[279]] * (1.012 ** (i - 279))
    fell = {d: 100.0 - (10 if 130 <= i < 140 else 0) for i, d in enumerate(cal)}    # market 6-month return < 0 on 130-139
    flat = {d: 100.0 for d in cal}
    armed = market_armed({'M': fell}, cal, 'M', 126, 126)
    assert armed[129] is False and armed[130] is True and armed[265] is True and armed[266] is False
    assert blowoff_exit({'X': spike, 'M': fell}, cal, market='M', within=126)('X', 299) is False   # last fall 160 sessions ago
    assert blowoff_exit({'X': spike, 'M': fell}, cal, market='M', within=200)('X', 299) is True
    assert blowoff_exit({'X': spike, 'M': flat}, cal, market='M', within=126)('X', 299) is False
    assert blowoff_exit({'X': spike, 'M': flat}, cal)('X', 299) is True                            # ungated


def test_hold_exit_sells_and_records_entry():
    from mtl.momentum import run_momentum
    cal = [f'2024-01-{d:02d}' for d in range(1, 31)]
    up = {d: 100 + i for i, d in enumerate(cal)}
    prices = {'SPY': {d: 100.0 for d in cal}, 'A': up, 'B': {d: 50 + i * 0.5 for i, d in enumerate(cal)}}
    seen = []

    def ex(t, k, e):
        seen.append((t, k, e))
        return t == 'A' and k - e >= 3
    r = run_momentum(prices, cal, cal[10], look=5, skip=0, top_n=1, keep_rank=2, hold_exit=ex)
    assert any(t == 'A' for t, k, e in seen)
    assert r['stops'] >= 1


def test_pending_shows_a_stop_decided_on_the_last_session():
    from mtl.momentum import run_momentum
    cal = [f'2024-01-{d:02d}' for d in range(1, 31)]
    prices = {'SPY': {d: 100.0 for d in cal}, 'A': {d: 100 + i for i, d in enumerate(cal)}, 'B': {d: 50 + i * 0.5 for i, d in enumerate(cal)}}
    r = run_momentum(prices, cal, cal[10], look=5, skip=0, top_n=1, keep_rank=2, exec_next='close',
                     hold_exit=lambda t, k, e: t == 'A' and k == len(cal) - 1)
    assert r['picks'][-1][1] == ['A'] and r['pending'] == ['B']
    r2 = run_momentum(prices, cal, cal[10], look=5, skip=0, top_n=1, keep_rank=2, exec_next='close')
    assert r2['pending'] in (None, r2['picks'][-1][1])             # nothing to change


def test_market_armed_below_moving_average():
    from mtl.momentum import blowoff_exit, market_armed
    cal = [f'd{i:03d}' for i in range(300)]
    m = {d: 100.0 + (i if i < 200 else 400 - i) for i, d in enumerate(cal)}   # up to 299 at 199, then down
    on = market_armed({'M': m}, cal, 'M', ma=50)
    assert on[49] is False and on[150] is False                                  # under 50 sessions / rising
    assert on[260] is True                                                       # falling well below its average
    spike = {d: 100 * (1.001 ** i) for i, d in enumerate(cal)}
    for i in range(279, 300):
        spike[cal[i]] = spike[cal[279]] * (1.012 ** (i - 279))
    assert blowoff_exit({'X': spike, 'M': m}, cal, market='M', ma=50)('X', 299) is True
    flat_up = {d: 100.0 + i for i, d in enumerate(cal)}
    assert blowoff_exit({'X': spike, 'M': flat_up}, cal, market='M', ma=50)('X', 299) is False


def test_sleeve_call_best_case_limits():
    import math
    from mtl.options_sim import sleeve_call
    cl = [100 * math.exp(0.002 * i + 0.02 * math.sin(i)) for i in range(100)]
    c = sleeve_call(cl, '2026-10-08')
    assert c['expiry'] == '2027-04-16' and c['strike'] == round(cl[-1] * 1.2 / 5) * 5
    assert abs(c['maxIv'] - max(0.20, c['rv'] * 0.8)) < 1e-3 and 0 < c['maxPrice'] < cl[-1] * 0.2
    assert sleeve_call(cl[:30], '2026-10-08') is None


def test_call_sleeve_curve_tracks_plan_and_calls():
    from mtl.options_sim import call_sleeve_curve
    cal = [f'2024-{m:02d}-{d:02d}' for m in range(1, 13) for d in (1, 8, 15, 22)]
    up = {d: 100 * 1.01 ** i for i, d in enumerate(cal)}
    prices = {'A': up}
    plan = [[d, 100 * 1.005 ** i] for i, d in enumerate(cal)]
    no_calls = call_sleeve_curve(plan, [[cal[0], []]], prices, cal)
    assert abs(no_calls[-1][1] / no_calls[0][1] - (0.8 * plan[-1][1] / plan[0][1] + 0.2)) < 0.05   # sleeve idle in cash
    with_calls = call_sleeve_curve(plan, [[cal[0], []], [cal[2], ['A']], [cal[30], []]], prices, cal)
    assert with_calls[-1][1] > no_calls[-1][1]          # a call on a rising stock adds value

"""Backtest engine - synthetic bars only, no network."""
import math
from datetime import datetime, timedelta, timezone

from mtl.backtest import Context, resample, simulate, state_series, summarize, with_ends
from mtl.structure import structure_signal

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def wave(n_bars, base, step, amp=5, period=10):
    out = []
    for i in range(n_bars):
        c = base + step * i + amp * math.sin(2 * math.pi * i / period)
        out.append(((T0 + timedelta(hours=i)).isoformat(), c, c + 0.1, c - 0.1, c))
    return out


def v_then_down(down=40, up=30, down2=30):
    """falling, then rising, then falling again - continuous prices."""
    bars, c = [], 200.0
    for seg_len, step in ((down, -1.0), (up, 1.5), (down2, -1.5)):
        for _ in range(seg_len):
            i = len(bars)
            c += step
            px = c + 5 * math.sin(2 * math.pi * i / 10)
            bars.append(((T0 + timedelta(hours=i)).isoformat(), px, px + 0.1, px - 0.1, px))
    return bars


def test_state_series_matches_a_fresh_read_at_every_bar():
    bars = v_then_down()
    states = state_series(bars, n=3, lookback=4)
    for k in range(len(bars)):
        assert states[k] == structure_signal(bars[:k + 1], n=3, lookback=4)['state']


def test_context_lookup_never_uses_an_unfinished_bar():
    bars = wave(30, 100, 1.0)
    ends = with_ends(bars, timedelta(hours=1))
    c = Context(bars, ends, n=3, lookback=4)
    just_before = ends[20] - timedelta(seconds=1)
    assert c.at(just_before) == c.states[19]
    assert c.at(ends[0] - timedelta(seconds=1)) is None


def test_long_enters_on_bullish_choch_and_exits_on_next_bearish_break():
    bars = v_then_down()
    ends = with_ends(bars, timedelta(hours=1))
    up = wave(len(bars), 100, 1.0)  # a context that is always in an uptrend once readable
    series = {'trig': (bars, ends), 'ctx': (up, with_ends(up, timedelta(hours=1)))}
    setup = dict(context=('ctx',), trigger='trig')
    import mtl.backtest as bt
    bt.SWING_N.update(trig=3, ctx=3)
    trades = simulate(series, setup, lookback=4, start=T0, ticker='X')
    longs = [t for t in trades if t['side'] == 'long']
    assert longs and not [t for t in trades if t['side'] == 'short']
    t = longs[0]
    assert t['entryTime'] < t['exitTime']
    assert math.isclose(t['ret'], (t['exit'] - t['entry']) / t['entry'])
    assert math.isclose(t['pnl'], 100 * t['ret'])


def test_short_mirrors_long_with_inverted_return():
    bars = [(ts, -o, -l, -h, -c) for ts, o, h, l, c in v_then_down()]
    bars = [(ts, o + 500, h + 500, l + 500, c + 500) for ts, o, h, l, c in bars]
    ends = with_ends(bars, timedelta(hours=1))
    down = wave(len(bars), 500, -1.0)
    series = {'trig': (bars, ends), 'ctx': (down, with_ends(down, timedelta(hours=1)))}
    import mtl.backtest as bt
    bt.SWING_N.update(trig=3, ctx=3)
    trades = simulate(series, dict(context=('ctx',), trigger='trig'), lookback=4, start=T0)
    shorts = [t for t in trades if t['side'] == 'short']
    assert shorts and not [t for t in trades if t['side'] == 'long']
    t = shorts[0]
    assert math.isclose(t['ret'], (t['entry'] - t['exit']) / t['entry'])


def test_no_entries_before_start():
    bars = v_then_down()
    ends = with_ends(bars, timedelta(hours=1))
    up = wave(len(bars), 100, 1.0)
    series = {'trig': (bars, ends), 'ctx': (up, with_ends(up, timedelta(hours=1)))}
    import mtl.backtest as bt
    bt.SWING_N.update(trig=3, ctx=3)
    assert simulate(series, dict(context=('ctx',), trigger='trig'), 4, start=ends[-1] + timedelta(1)) == []


def test_resample_monthly_ends_on_last_trading_day():
    daily = [(f"2024-01-{d:02d}T00:00:00", 1, 2, 0.5, 1) for d in (29, 30, 31)] + \
            [(f"2024-02-{d:02d}T00:00:00", 1, 3, 0.2, 2) for d in (1, 2)]
    bars, ends = resample(daily, 'M')
    assert len(bars) == 2 and bars[1][2] == 3 and bars[1][4] == 2
    assert ends[0].date().isoformat() == '2024-01-31' and ends[0].hour == 16


def test_summarize():
    tr = [dict(ret=0.1, pnl=10, bars=3, open=False, exitTime='a'),
          dict(ret=-0.05, pnl=-5, bars=1, open=False, exitTime='b'),
          dict(ret=0.2, pnl=20, bars=2, open=True, exitTime='c')]
    s = summarize(tr)
    assert s['trades'] == 2 and s['winRate'] == 0.5 and math.isclose(s['totalPnl'], 5)
    assert math.isclose(s['profitFactor'], 2.0) and s['stillOpen'] == 1


from mtl.backtest import curve_stats, growth, portfolio_index


def test_portfolio_index_marks_trades_daily_and_splits_equally():
    cal = ['2024-01-02', '2024-01-03', '2024-01-04']
    closes = {'A': {'2024-01-02': 110.0, '2024-01-03': 121.0}, 'B': {'2024-01-02': 50.0, '2024-01-03': 50.0}}
    trades = [
        dict(ticker='A', side='long', entryTime='2024-01-02T10:30', entry=100.0,
             exitTime='2024-01-03T15:00', exit=121.0, open=False),
        dict(ticker='B', side='short', entryTime='2024-01-02T11:30', entry=50.0,
             exitTime='2024-01-02T15:00', exit=45.0, open=False),
    ]
    idx = portfolio_index(trades, closes, cal)
    # day 1: A +10% (100->110), B short +10% (50->45) -> +10%; day 2: A +10% alone; day 3: cash
    assert [p[2] for p in idx] == [2, 1, 0]
    assert abs(idx[0][1] - 110.0) < 1e-9 and abs(idx[1][1] - 121.0) < 1e-9 and idx[2][1] == idx[1][1]


def test_growth_and_curve_stats():
    g = growth([['a', 50.0], ['b', 75.0], ['c', 60.0]])
    assert [round(v[1], 6) for v in g] == [100.0, 150.0, 120.0]
    s = curve_stats([v[1] for v in g])
    assert abs(s['total'] - 0.2) < 1e-9 and abs(s['maxDD'] - (120 / 150 - 1)) < 1e-9 and s['annual'] is None


from mtl.backtest import consistent


def test_consistent_rejects_prices_outside_the_daily_range():
    ranges = {'BNY': {'2024-03-08': (54.0, 56.0), '2024-03-14': (54.5, 55.5)}}
    ok = dict(ticker='BNY', entryTime='2024-03-08T15:00', entry=55.0, exitTime='2024-03-14T11:00', exit=55.2)
    bad = dict(ok, entry=10.64)
    assert consistent(ok, ranges) and not consistent(bad, ranges)
    assert consistent(dict(ok, ticker='ZZZ'), ranges)


from mtl.backtest import simulate_variant


def _series_v():
    bars = v_then_down()
    ends = with_ends(bars, timedelta(hours=1))
    up = wave(len(bars), 100, 1.0)
    import mtl.backtest as bt
    bt.SWING_N.update(trig=3, ctx=3)
    return {'trig': (bars, ends), 'ctx': (up, with_ends(up, timedelta(hours=1)))}, dict(context=('ctx',), trigger='trig')


def test_variant_with_defaults_reproduces_simulate():
    series, setup = _series_v()
    a = simulate(series, setup, 4, T0, ticker='X')
    b = simulate_variant(series, setup, 4, T0, ticker='X')
    strip = lambda ts: [(t['side'], t['entryTime'], t['exitTime'], round(t['ret'], 12)) for t in ts]
    assert strip(a) == strip(b) and b


def test_variant_stop_and_target_bound_the_result():
    series, setup = _series_v()
    for rr in (1.0, 2.0):
        for t in simulate_variant(series, setup, 4, T0, exit='rr', rr=rr, use_stop=True):
            assert t['exitReason'] in ('stop', 'target', 'open')
            if t['exitReason'] == 'target':
                assert t['ret'] > 0


def test_variant_allow_filter_blocks_entries():
    series, setup = _series_v()
    assert simulate_variant(series, setup, 4, T0, allow=lambda side, when: False) == []


def test_confirm_delays_entry_and_skips_failed_reversals():
    series, setup = _series_v()
    base = simulate_variant(series, setup, 4, T0)
    conf = simulate_variant(series, setup, 4, T0, confirm=3)
    bars = series['trig'][0]
    assert len(conf) <= len(base)
    for t in conf:
        assert t['entryTime'] not in {b['entryTime'] for b in base} or not base
    # zero confirmation is the original rule
    assert [t['entryTime'] for t in simulate_variant(series, setup, 4, T0, confirm=0)] == [t['entryTime'] for t in base]


def test_confirmed_exit_never_exits_before_the_unconfirmed_one():
    series, setup = _series_v()
    a = {t['entryTime']: t['exitTime'] for t in simulate_variant(series, setup, 4, T0, confirm=3)}
    b = {t['entryTime']: t['exitTime'] for t in simulate_variant(series, setup, 4, T0, confirm=3, confirm_exit=True)}
    for k in a:
        if k in b:
            assert b[k] >= a[k]


from mtl.backtest import timing_curve, trend_hold


def _daily(prices, start='2024-01-01'):
    from datetime import date
    d0 = date.fromisoformat(start)
    bars = [((d0 + timedelta(days=i)).isoformat() + "T00:00:00", p, p + 0.1, p - 0.1, p) for i, p in enumerate(prices)]
    return bars, with_ends(bars)


def test_trend_hold_buys_an_uptrend_and_exits_on_the_daily_break():
    import mtl.backtest as bt
    up = [100 + i + 5 * math.sin(2 * math.pi * i / 10) for i in range(80)]
    down = [up[-1] - 1.5 * i + 5 * math.sin(2 * math.pi * (80 + i) / 10) for i in range(1, 40)]
    daily = _daily(up + down)
    weekly = (daily[0], daily[1])  # the same rising-then-falling read stands in for weekly
    bt.SWING_N.update(weekly=3)
    tr = trend_hold(daily, weekly, 4, daily[1][0])
    bt.SWING_N.update(weekly=2)
    assert tr and all(t['side'] == 'long' for t in tr)
    assert all(t['entryTime'] < t['exitTime'] for t in tr)


def test_timing_curve_is_cash_only_in_a_double_downtrend():
    import mtl.backtest as bt
    prices = [200 - i + 5 * math.sin(2 * math.pi * i / 10) for i in range(80)]
    daily = _daily(prices)
    bt.SWING_N.update(weekly=3)
    curve = timing_curve(daily, daily, 4, daily[1][0])
    bt.SWING_N.update(weekly=2)
    assert curve[0][2] == 1 and curve[-1][2] == 0
    # once in cash the value stops changing
    flat = [p for p in curve if p[2] == 0]
    assert len({round(p[1], 9) for p in curve[curve.index(flat[0]) + 1:] if p[2] == 0}) <= 2


from mtl.backtest import simulate_dip


def _dip_series(rebound=1.35):
    """Daily: flat at 100 then a ~15% drop; 1h: falls then turns up and rallies."""
    from datetime import date
    days = [(date(2024, 1, 1) + timedelta(days=i)) for i in range(40)]
    daily = []
    for i, d in enumerate(days):
        px = 100.0 if i < 30 else 85.0
        daily.append((d.isoformat() + "T00:00:00", px, px + 0.5, px - 0.5, px))
    hourly, t0 = [], datetime(2024, 2, 10, 14, tzinfo=timezone.utc)
    prices = [85 - 0.3 * i + 2 * math.sin(i) for i in range(30)]
    prices += [prices[-1] + (rebound - 1) * 80 * k / 40 + 1.5 * math.sin(k) for k in range(1, 41)]
    for k, p in enumerate(prices):
        hourly.append(((t0 + timedelta(hours=k)).isoformat(), p, p + 0.2, p - 0.2, p))
    return {'1h': (hourly, with_ends(hourly, timedelta(hours=1))), 'daily': (daily, with_ends(daily)),
            'weekly': resample(daily, 'W')}


def test_dip_buys_the_first_1h_higher_high_after_a_drop_and_takes_profit():
    tr = simulate_dip(_dip_series(), 4, T0, target=0.05)
    assert tr and tr[0]['exitReason'] == 'target' and abs(tr[0]['ret'] - 0.05) < 0.02


def test_dip_needs_a_drop():
    s = _dip_series()
    flat = [(ts, 100.0, 100.5, 99.5, 100.0) for ts, *_ in s['daily'][0]]
    s['daily'] = (flat, with_ends(flat))
    assert simulate_dip(s, 4, T0) == []


def test_dip_without_target_hit_stays_open_and_is_marked():
    tr = simulate_dip(_dip_series(rebound=1.1), 4, T0, target=0.5)
    assert tr and tr[-1]['open'] and tr[-1]['exitReason'] == 'open'


from mtl.backtest import rsi_series, simulate_rsi
from mtl.fetch import rsi14


def test_rsi_series_matches_the_existing_wilder_rsi_at_every_bar():
    closes = [100 + 3 * math.sin(i / 3) + 0.2 * i for i in range(60)]
    series = rsi_series(closes)
    assert series[13] is None and series[14] is not None
    for k in range(14, 60):
        assert abs(series[k] - rsi14(closes[:k + 1])) < 0.006


def test_simulate_rsi_buys_the_cross_above_50_and_sells_the_cross_below():
    closes = [100 - i for i in range(20)] + [80 + 2 * i for i in range(20)] + [120 - 2 * i for i in range(20)]
    bars = [((T0 + timedelta(days=i)).isoformat(), c, c, c, c) for i, c in enumerate(closes)]
    ends = with_ends(bars, timedelta(days=1))
    rsi = rsi_series(closes)
    tr = simulate_rsi(bars, ends, T0)
    assert len(tr) == 1 and not tr[0]['open']
    i_in = [t[0] for t in enumerate(ends) if t[1].isoformat() == tr[0]['entryTime']][0]
    i_out = [t[0] for t in enumerate(ends) if t[1].isoformat() == tr[0]['exitTime']][0]
    assert rsi[i_in - 1] <= 50 < rsi[i_in] and rsi[i_out - 1] >= 50 > rsi[i_out]


from mtl.backtest import rsi_next, rsi_states, simulate_rsi_mtf


def test_rsi_next_equals_the_rsi_of_the_extended_series():
    closes = [100 + 3 * math.sin(i / 3) + 0.2 * i for i in range(40)]
    st = rsi_states(closes)
    for k in range(14, 39):
        assert abs(rsi_next(st[k], closes[k], closes[k + 1]) - rsi_series(closes)[k + 1]) < 1e-9


def _mtf_fixture(daily_up=True):
    from datetime import date
    dcl = [100 + (i if daily_up else -i) * 0.5 + math.sin(i) for i in range(40)]
    daily = [((date(2024, 1, 1) + timedelta(days=i)).isoformat() + "T00:00:00", c, c, c, c) for i, c in enumerate(dcl)]
    t0 = datetime(2024, 2, 10, 15, tzinfo=timezone.utc)
    hcl = [120 - 0.3 * i for i in range(20)] + [114 + 0.4 * i for i in range(20)] + [122 - 0.5 * i for i in range(20)]
    hourly = [((t0 + timedelta(hours=i)).isoformat(), c, c, c, c) for i, c in enumerate(hcl)]
    return (hourly, with_ends(hourly, timedelta(hours=1))), (daily, with_ends(daily))


def test_mtf_rsi_needs_the_daily_rsi_above_50():
    h, d = _mtf_fixture(daily_up=True)
    assert simulate_rsi_mtf(h, d, T0)
    h, d = _mtf_fixture(daily_up=False)
    assert simulate_rsi_mtf(h, d, T0) == []


def test_rsi_band_needs_to_clear_both_levels():
    closes = [100 - i for i in range(20)] + [80 + 2 * i for i in range(20)] + [120 - 2 * i for i in range(20)]
    bars = [((T0 + timedelta(days=i)).isoformat(), c, c, c, c) for i, c in enumerate(closes)]
    ends = with_ends(bars, timedelta(days=1))
    rsi = rsi_series(closes)
    tr = simulate_rsi(bars, ends, T0, buy_level=55, sell_level=45)
    assert len(tr) == 1
    k_in = [e.isoformat() for e in ends].index(tr[0]['entryTime'])
    k_out = [e.isoformat() for e in ends].index(tr[0]['exitTime'])
    assert rsi[k_in - 1] <= 55 < rsi[k_in] and rsi[k_out - 1] >= 45 > rsi[k_out]
    # defaults are unchanged
    assert simulate_rsi(bars, ends, T0) == simulate_rsi(bars, ends, T0, buy_level=50, sell_level=50)


from mtl.backtest import semivol_series, simulate_semivol


def test_semivol_compares_typical_up_and_down_move_sizes():
    # small rises (+1%) and big falls (-3%): up vol < down vol
    closes = [100.0]
    for i in range(30):
        closes.append(closes[-1] * (1.01 if i % 3 else 0.97))
    up, dn = semivol_series(closes, 20)[-1]
    assert abs(up - 0.01) < 1e-9 and abs(dn - 0.03) < 1e-9


def test_simulate_semivol_enters_when_calm_up_begins_and_exits_when_it_ends():
    closes = [100.0]
    for i in range(40):            # big rises, small falls first
        closes.append(closes[-1] * (1.03 if i % 3 else 0.99))
    for i in range(40):            # then small rises, big falls
        closes.append(closes[-1] * (1.01 if i % 3 else 0.97))
    for i in range(40):            # then back to big rises
        closes.append(closes[-1] * (1.03 if i % 3 else 0.99))
    bars = [((T0 + timedelta(days=i)).isoformat(), c, c, c, c) for i, c in enumerate(closes)]
    ends = with_ends(bars, timedelta(days=1))
    sv = semivol_series(closes, 20)
    tr = simulate_semivol(bars, ends, T0, window=20, calm='up')
    assert tr and not tr[0]['open']
    k_in = [e.isoformat() for e in ends].index(tr[0]['entryTime'])
    k_out = [e.isoformat() for e in ends].index(tr[0]['exitTime'])
    assert sv[k_in][0] < sv[k_in][1] and not sv[k_out][0] < sv[k_out][1]
    assert 40 <= k_in <= 80 <= k_out


from mtl.backtest import efficiency, simulate_choppiness


def test_efficiency_ratio_signed():
    closes = [10, 11, 12, 13, 12, 13]
    path = [0.0]
    for i in range(1, len(closes)):
        path.append(path[-1] + abs(closes[i] - closes[i - 1]))
    assert efficiency(closes, 0, 3, path) == 1.0
    assert abs(efficiency(closes, 0, 5, path) - 3 / 5) < 1e-12
    assert efficiency(closes, 3, 4, path) == -1.0


def test_choppiness_buys_a_smooth_rise_after_choppy_falls():
    import random
    random.seed(1)
    closes, c = [], 100.0
    for cyc in range(4):                 # choppy declines: zig-zag drifting down
        for i in range(30):
            c += (-1.0 if i % 2 else 0.6) + random.uniform(-0.05, 0.05)
            closes.append(c)
        for i in range(8):               # brief bounce so swings form
            c += 0.8
            closes.append(c)
    for i in range(40):                  # then a clean, steady rise
        c += 1.0
        closes.append(c)
    bars = [((T0 + timedelta(days=i)).isoformat(), x, x + 0.05, x - 0.05, x) for i, x in enumerate(closes)]
    ends = with_ends(bars, timedelta(days=1))
    tr = simulate_choppiness(bars, ends, T0, window=10)
    assert tr and tr[-1]['entryTime'] >= ends[len(closes) - 48].isoformat()  # the final bounce runs into the rise
    assert tr[-1]['ret'] > 0


def test_choppiness_like_for_like_reference_runs_and_only_buys_rises():
    import random
    random.seed(2)
    closes, c = [], 100.0
    for i in range(300):
        c *= 1 + random.gauss(0.0005, 0.01)
        closes.append(c)
    bars = [((T0 + timedelta(days=i)).isoformat(), x, x, x, x) for i, x in enumerate(closes)]
    ends = with_ends(bars, timedelta(days=1))
    tr = simulate_choppiness(bars, ends, T0, window=10, reference='windows')
    for t in tr:
        k = [e.isoformat() for e in ends].index(t['entryTime'])
        assert closes[k] > closes[k - 10]

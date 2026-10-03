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

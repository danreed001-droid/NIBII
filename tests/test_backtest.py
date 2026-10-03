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

"""Price-level breaks (BOS/CHoCH) and the multi-timeframe buy scanner -
synthetic OHLC data only, no network needed."""
import math
from datetime import datetime, timedelta, timezone

from mtl.mtf import SETUPS, drop_forming, evaluate_setup, tf_read
from mtl.structure import structure_breaks


def wave(n_bars, base_start, base_step, amplitude=5, period=10, start=0):
    bars = []
    for i in range(n_bars):
        c = base_start + base_step * i + amplitude * math.sin(2 * math.pi * i / period)
        bars.append((f"t{start + i:04d}", c, c + 0.1, c - 0.1, c))
    return bars


def v_shape(down=40, up=12):
    """A falling channel, then a rising one starting from where it left off."""
    first = wave(down, 200, -1.0)
    last_c = first[-1][4]
    second = wave(up, last_c, 1.5, start=down)
    shift = last_c - second[0][4]
    return first + [(ts, o + shift, h + shift, l + shift, c + shift) for ts, o, h, l, c in second]


def test_uptrend_breaks_are_bullish_continuations():
    ev = structure_breaks(wave(60, 100, 1.0), n=3)
    assert ev and all(e['direction'] == 'bull' for e in ev)
    assert all(e['kind'] == 'BOS' for e in ev[1:])


def test_break_only_after_reference_swing_is_confirmed():
    for e in structure_breaks(v_shape(), n=3):
        assert e['i'] >= e['ref_swing_i'] + 3


def test_reversal_prints_bullish_choch_after_bearish_run():
    ev = structure_breaks(v_shape(), n=3)
    bear = [e for e in ev if e['direction'] == 'bear']
    assert bear
    first_bull_after = next(e for e in ev if e['direction'] == 'bull' and e['i'] > bear[-1]['i'])
    assert first_bull_after['kind'] == 'CHoCH'
    assert first_bull_after['protected'] is not None


def test_wick_through_level_is_not_a_close_break():
    # swing high at index 3 (high 12); bar 7 wicks to 13 but closes at 11
    bars = [(f"t{i}", 10, h, 9, 10) for i, h in enumerate([10, 10.5, 11, 12, 11, 10.5, 10])]
    bars.append(("t7", 10, 13, 9, 11))
    assert structure_breaks(bars, n=3) == []
    wick = structure_breaks(bars, n=3, break_on='wick')
    assert len(wick) == 1 and wick[0]['level'] == 12 and wick[0]['direction'] == 'bull'


def test_fresh_choch_flags_flipped_bull_and_stale_one_does_not():
    bars = v_shape()
    read = tf_read(bars, n=3, recent_bars=50, lookback=4)
    assert read['lastBreak']['direction'] == 'bull' and read['flippedBull']
    stale = tf_read(bars, n=3, recent_bars=1, lookback=4)
    assert read['barsAgo'] >= 1 and not stale['flippedBull']
    assert not read['flippedBear']


def test_fresh_bearish_choch_flags_flipped_bear():
    # mirror image of v_shape: a rising channel that rolls over
    bars = [(ts, -o, -l, -h, -c) for ts, o, h, l, c in v_shape()]
    read = tf_read(bars, n=3, recent_bars=50, lookback=4)
    assert read['lastBreak']['direction'] == 'bear' and read['lastBreak']['kind'] == 'CHoCH'
    assert read['flippedBear'] and not read['flippedBull']


def _read(state, flipped=False, brk=None, bars_ago=None, close=100.0, flipped_bear=False):
    return dict(state=state, labels=[], lastBreak=brk, flippedBull=flipped,
                flippedBear=flipped_bear, close=close, barsAgo=bars_ago, bars=50, note=None)


CHOCH = dict(kind='CHoCH', direction='bull', level=99.0, protected=95.0)


def test_setup_buy_when_context_up_and_trigger_flipped():
    reads = {'weekly': _read('uptrend'), 'daily': _read('uptrend'),
             '1h': _read('choppy', flipped=True, brk=CHOCH, bars_ago=2)}
    r = evaluate_setup(reads, SETUPS['daily'])
    assert r['verdict'] == 'BUY' and r['entry'] == 100.0 and r['stop'] == 95.0


def test_setup_watch_when_context_up_but_no_flip():
    reads = {'weekly': _read('uptrend'), 'daily': _read('uptrend'), '1h': _read('downtrend')}
    assert evaluate_setup(reads, SETUPS['daily'])['verdict'] == 'WATCH'


def test_setup_no_names_the_failing_timeframe():
    reads = {'weekly': _read('uptrend'), 'daily': _read('choppy'), '1h': _read('uptrend'),
             '15m': _read('downtrend', flipped=True, brk=CHOCH, bars_ago=1)}
    r = evaluate_setup(reads, SETUPS['hourly'])
    assert r['verdict'] == 'NO' and r['side'] is None and 'daily choppy' in r['reason']


BEAR_CHOCH = dict(kind='CHoCH', direction='bear', level=101.0, protected=105.0)


def test_setup_sell_when_context_down_and_trigger_flipped_bearish():
    reads = {'weekly': _read('downtrend'), 'daily': _read('downtrend'),
             '1h': _read('choppy', flipped_bear=True, brk=BEAR_CHOCH, bars_ago=3)}
    r = evaluate_setup(reads, SETUPS['daily'])
    assert r['verdict'] == 'SELL' and r['side'] == 'sell' and r['stop'] == 105.0


def test_setup_watch_sell_side_ignores_a_bullish_flip():
    reads = {'weekly': _read('downtrend'), 'daily': _read('downtrend'),
             '1h': _read('uptrend', flipped=True, brk=CHOCH, bars_ago=1)}
    r = evaluate_setup(reads, SETUPS['daily'])
    assert r['verdict'] == 'WATCH' and r['side'] == 'sell'


def test_mixed_up_and_down_context_is_no():
    reads = {'weekly': _read('uptrend'), 'daily': _read('downtrend'),
             '1h': _read('choppy', flipped_bear=True, brk=BEAR_CHOCH, bars_ago=1)}
    assert evaluate_setup(reads, SETUPS['daily'])['verdict'] == 'NO'


def test_drop_forming_removes_only_an_unfinished_bar():
    now = datetime(2026, 10, 2, 15, 50, tzinfo=timezone.utc)
    bars = [("2026-10-02T15:30:00+00:00", 1, 1, 1, 1), ("2026-10-02T15:45:00+00:00", 1, 1, 1, 1)]
    assert len(drop_forming(bars, timedelta(minutes=15), now)) == 1
    assert len(drop_forming(bars, timedelta(minutes=15), now + timedelta(minutes=10))) == 2


def test_drop_forming_handles_date_only_daily_bars():
    now = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)
    bars = [("2026-10-01T00:00:00", 1, 1, 1, 1), ("2026-10-02T00:00:00", 1, 1, 1, 1)]
    assert len(drop_forming(bars, timedelta(days=1), now)) == 1

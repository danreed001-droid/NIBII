"""Market structure: swing detection and HH/HL/LH/LL labeling - synthetic
OHLC data only, no network needed."""
import math
from datetime import date, timedelta

from mtl.structure import (find_swings, label_structure, last_break,
                           structure_signal, trend_state, weekly_from_daily)


def make_wave(n_bars, base_start, base_step, amplitude, period, start="2026-01-01"):
    """A sine wave riding a linear baseline - base_step > 0 makes both the
    peaks and troughs rise (an up channel); base_step < 0 makes both fall
    (a down channel); base_step == 0 with a stable amplitude is range-bound
    (choppy - peaks and troughs don't consistently rise or fall)."""
    d0 = date.fromisoformat(start)
    bars = []
    for i in range(n_bars):
        base = base_start + base_step * i
        c = base + amplitude * math.sin(2 * math.pi * i / period)
        ts = (d0 + timedelta(days=i)).isoformat()
        bars.append((ts, c, c + 0.1, c - 0.1, c))
    return bars


def test_uptrend_produces_hh_hl_and_uptrend_state():
    bars = make_wave(n_bars=40, base_start=100, base_step=1.0, amplitude=5, period=10)
    sig = structure_signal(bars, n=3, lookback=4)
    assert sig['state'] == 'uptrend'
    labeled = [s['label'] for s in sig['swings'] if s['label']]
    assert set(labeled[-4:]) <= {'HH', 'HL'}


def test_downtrend_produces_lh_ll_and_downtrend_state():
    bars = make_wave(n_bars=40, base_start=100, base_step=-1.0, amplitude=5, period=10)
    sig = structure_signal(bars, n=3, lookback=4)
    assert sig['state'] == 'downtrend'
    labeled = [s['label'] for s in sig['swings'] if s['label']]
    assert set(labeled[-4:]) <= {'LH', 'LL'}


def test_range_bound_is_choppy_not_a_trend():
    # flat baseline, non-integer period so cycles don't repeat identically
    # (real price data never does either) - peaks/troughs wobble without a
    # consistent direction
    bars = make_wave(n_bars=40, base_start=100, base_step=0.0, amplitude=5, period=9.3)
    sig = structure_signal(bars, n=3, lookback=4)
    assert sig['state'] in ('choppy', None)  # never mistaken for a real trend


def test_too_few_bars_returns_none_with_a_note_not_a_guess():
    bars = make_wave(n_bars=4, base_start=100, base_step=1.0, amplitude=5, period=10)
    sig = structure_signal(bars, n=3, lookback=4)
    assert sig['state'] is None
    assert sig['note'] is not None


def test_last_break_flags_a_downturn_after_an_uptrend():
    up = make_wave(n_bars=30, base_start=100, base_step=1.0, amplitude=5, period=10)
    down_tail = make_wave(n_bars=15, base_start=up[-1][4], base_step=-3.0, amplitude=5,
                          period=10, start="2026-02-15")
    bars = up + down_tail
    labeled = label_structure(find_swings(bars, n=3))
    brk = last_break(labeled)
    assert brk is not None
    assert brk['label'] in ('LH', 'LL')


def test_weekly_from_daily_buckets_by_iso_week_and_aggregates_correctly():
    # Mon 2026-01-05 through Sun 2026-01-11 is one ISO week; Mon 2026-01-12 starts the next
    daily = [
        ("2026-01-05", 10, 12, 9, 11),   # Mon wk1
        ("2026-01-06", 11, 13, 10, 12),  # Tue wk1
        ("2026-01-07", 12, 14, 11, 13),  # Wed wk1 - week high 14
        ("2026-01-12", 13, 15, 8, 9),    # Mon wk2 - week low 8, week close 9 (only bar)
    ]
    weekly = weekly_from_daily(daily)
    assert len(weekly) == 2
    wk1 = weekly[0]
    assert wk1[0] == "2026-01-05"  # opens on the week's first bar
    assert wk1[2] == 14            # week high across all 3 days
    assert wk1[3] == 9             # week low across all 3 days
    assert wk1[4] == 13            # week close = last bar's close seen so far
    wk2 = weekly[1]
    assert wk2[0] == "2026-01-12"
    assert wk2[2] == 15 and wk2[3] == 8 and wk2[4] == 9


def test_trend_state_needs_at_least_two_labeled_swings():
    one_swing = [dict(i=0, ts='t', type='high', price=1, label='HH')]
    assert trend_state(one_swing) is None

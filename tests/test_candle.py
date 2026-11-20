import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import candle  # noqa: E402


def _cal(n, start=date(2020, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(cal, closes, opens=None):
    opens = opens or closes
    return [(d, o, max(o, c), min(o, c), c) for d, o, c in zip(cal, opens, closes)]


def _drop_then_pattern(peak=100.0, low=80.0, third_close=86.0):
    """Flat at the peak, a slide to about `low`, then two red days to fresh lows and a third day closing at third_close."""
    c = [peak] * 260 + [peak - (peak - low + 2) * i / 30 for i in range(1, 31)]
    o = list(c)
    last = c[-1]
    o += [last + 1, last - 0.5, last - 2]          # two red days (open above close) to new lows, then the third day
    c += [last - 1, last - 2.5, third_close]
    cal = _cal(len(c))
    return cal, _bars(cal, c, o)


def test_fires_on_two_red_fresh_lows_then_a_close_above_both_opens():
    cal, bars = _drop_then_pattern()
    k = len(cal) - 1
    days, sig = candle.candle_days(bars, cal, cal[0])
    assert sig == [cal[k]] and days == {cal[k]}          # the window runs past the calendar's end
    st = candle.candle_state(bars, cal, k, {cal[k]}, sig)
    assert st['signal'] and st['active'] and st['left'] == 9 and st['onNext']


def test_no_signal_when_the_third_day_stays_under_the_red_opens():
    cal, bars = _drop_then_pattern(third_close=78.0)
    assert candle.candle_days(bars, cal, cal[0])[1] == []
    r = candle.reading(*candle._series(bars, cal), len(cal) - 1)
    assert r['reds'] and r['fresh'] and r['deep'] and not r['above']


def test_no_signal_without_a_deep_enough_drop():
    cal, bars = _drop_then_pattern(low=97.0, third_close=98.0)   # only about 7% under the high
    assert candle.candle_days(bars, cal, cal[0])[1] == []


def test_no_signal_in_a_crash_deeper_than_the_cap():
    cal, bars = _drop_then_pattern(low=60.0, third_close=62.0)   # about 44% under the high: past the 30% cap
    assert candle.candle_days(bars, cal, cal[0])[1] == []
    r = candle.reading(*candle._series(bars, cal), len(cal) - 1)
    assert r['reds'] and r['fresh'] and r['deep'] and r['above'] and not r['capped'] and not r['signal']
    r = candle.reading(*candle._series(bars, cal), len(cal) - 1, cap=None)   # without the cap it would fire
    assert r['signal']


def test_fires_inside_the_cap():
    cal, bars = _drop_then_pattern(low=75.0, third_close=78.0)   # about 27% under the high
    assert candle.candle_days(bars, cal, cal[0])[1] == [cal[-1]]


def test_holds_ten_sessions_over_the_other_rules_and_marks_the_switches():
    cal = _cal(30)
    modes = {d: ('TLT' if 5 <= i < 25 else 'boost') for i, d in enumerate(cal)}
    half = {cal[6]: 'GLD'}
    days = set(cal[5:15])
    m, w, h, held = candle.apply_candle(modes, {}, half, days, cal)
    assert all(m[d] == 'boost' for d in cal[5:15]) and m[cal[15]] == 'TLT'
    assert w[cal[5]] == 'candle' and w[cal[15]] == 'candle-end' and cal[6] not in h
    assert held == set(cal[5:15])


def _crash_shape(peak=100.0, drop=0.15, green_close=None, setup_highs_pad=0.3):
    """Flat at the peak, a slide `drop` down, three setup days (two red, one small green) at fresh lows, then a long
    green day closing at green_close (default: above all three highs)."""
    n0 = 260
    c = [peak] * n0 + [peak * (1 - drop * i / 20) for i in range(1, 21)]
    o = list(c)
    hi = [x for x in c]
    last = c[-1]
    so = [last + 0.5, last - 0.6, last - 1.6]          # setup opens: red, red, small green
    sc = [last - 0.5, last - 1.5, last - 1.4]
    o += so
    c += sc
    hi += [max(a, b) + setup_highs_pad for a, b in zip(so, sc)]
    need = max(hi[-3:])
    gc = need + 0.5 if green_close is None else green_close
    o.append(last - 1.6)
    c.append(gc)
    hi.append(gc + 0.1)
    cal = _cal(len(c))
    bars = [(d, oo, h, min(oo, cc) - 0.1, cc) for d, oo, h, cc in zip(cal, o, hi, c)]
    return cal, bars, need


def test_rule26_fires_on_a_long_green_day_above_all_three_setup_highs():
    cal, bars, need = _crash_shape()
    k = len(cal) - 1
    days, sig = candle.crash_days(bars, cal, cal[0])
    assert sig == [cal[k]] and days == {cal[k]}
    st = candle.candle_state(bars, cal, k, {cal[k]}, [], sig26=sig)
    assert st['r26']['signal'] and st['r26']['left'] == candle.C26_HOLD - 1 and st['onNext']
    assert abs(st['r26']['need'] - round(need, 2)) < 1e-9


def test_rule26_needs_a_close_above_the_highs_not_just_the_bodies():
    cal, bars, need = _crash_shape(green_close=None)
    # close above the setup bodies (their opens) but under the highest wick
    cal2, bars2, need2 = _crash_shape(green_close=None, setup_highs_pad=3.0)
    o = [b[1] for b in bars2[-4:-1]]
    gc = max(o) + 0.2
    assert gc < need2
    bars2[-1] = (bars2[-1][0], bars2[-1][1], gc + 0.1, bars2[-1][3], gc)
    assert candle.crash_days(bars2, cal2, cal2[0])[1] == []


def test_rule26_needs_an_8pct_drop_and_has_no_cap():
    cal, bars, _ = _crash_shape(drop=0.05)
    assert candle.crash_days(bars, cal, cal[0])[1] == []
    cal, bars, _ = _crash_shape(drop=0.55)          # deeper than rule 19's 30% cap still counts
    assert candle.crash_days(bars, cal, cal[0])[1] == [cal[-1]]


def test_rule26_days_join_rule_19s_through_apply_candle():
    cal, bars, _ = _crash_shape()
    days, sig = candle.crash_days(bars, cal, cal[0])
    modes = {d: 'side' for d in cal}
    m, w, h, held = candle.apply_candle(modes, {}, {}, days, cal)
    assert m[cal[-1]] == 'boost' and w[cal[-1]] == 'candle' and held == {cal[-1]}

"""RSI support-line breaks."""
import math

from mtl.rsi_line import rsi, rsi_warning, support_breaks


def test_rsi_bounds_and_direction():
    up = [100 * 1.01 ** i for i in range(40)]
    assert rsi(up)[-1] == 100.0
    wave = [100 + 5 * math.sin(i / 3) for i in range(80)]
    r = rsi(wave)
    assert all(v is None or 0 <= v <= 100 for v in r) and r[13] is None and r[14] is not None


def test_break_of_a_line_with_four_touches():
    # RSI swing lows at 40 every 12 sessions, then a plunge to 20
    r = [None] + [40 + 10 * abs(math.sin(math.pi * i / 12)) for i in range(1, 70)] + [45, 30, 20]
    br = support_breaks(r)
    assert len(r) - 2 in br and abs(br[len(r) - 2][0] - 40) < 2.6


def test_warning_needs_spy_near_or_below_its_average():
    closes = [100 + 0.05 * i for i in range(300)] + [100 + 0.05 * 300 - 3 * i for i in range(1, 6)]
    cal = [f'd{i:04d}' for i in range(len(closes))]
    k = len(closes) - 1
    w = rsi_warning(closes, cal, k, brk={k - 2: (40.0, k - 60)})
    assert w['date'] == cal[k - 2] and w['ago'] == 2
    assert w['on'] == (w['gap'] < 0.02)
    assert rsi_warning(closes, cal, k, brk={})['on'] is False

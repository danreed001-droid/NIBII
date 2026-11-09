"""Candlestick patterns and the candle-noise reading (mtl/candlepat.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl import candlepat as cp  # noqa: E402


def _flat(n, px=100.0):
    return [(f'2026-01-{i:02d}', px, px + 1, px - 1, px + 0.2) for i in range(1, n + 1)]


def _codes(bars):
    return {c for _, c in cp.patterns(bars)}


def test_engulfing_both_ways():
    b = _flat(25) + [('d1', 101, 101.5, 99, 99.5), ('d2', 99.2, 102.5, 99, 102)]
    assert 'BE' in _codes(b)
    b = _flat(25) + [('d1', 99.5, 101.5, 99, 101), ('d2', 101.3, 101.5, 98, 99)]
    assert 'SE' in _codes(b)


def test_hammer_after_a_fall_and_star_after_a_rise():
    down = [(f'd{i}', 110 - i, 111 - i, 109 - i, 109.5 - i) for i in range(10)]
    b = down + [('h', 100.5, 101, 96, 100.8)]          # lower wick 4.5 vs body 0.3, top of the range
    assert 'HM' in _codes(b)
    up = [(f'u{i}', 90 + i, 91 + i, 89 + i, 90.5 + i) for i in range(10)]
    b = up + [('s', 100, 104.5, 99.8, 100.2)]
    assert 'SS' in _codes(b)


def test_doji_needs_a_real_range():
    b = _flat(25) + [('dj', 100, 101.2, 98.8, 100.05)]
    assert 'DJ' in _codes(b)
    b = _flat(25) + [('dj', 100, 100.1, 99.95, 100.0)]   # tiny range: not a doji
    assert 'DJ' not in _codes(b)


def test_three_soldiers_and_crows():
    b = _flat(25) + [('a', 100, 102.2, 99.8, 102), ('b', 101, 104.2, 100.8, 104), ('c', 103, 106.2, 102.8, 106)]
    assert 'WS' in _codes(b)
    b = _flat(25) + [('a', 100, 100.2, 97.8, 98), ('b', 99, 99.2, 95.8, 96), ('c', 97, 97.2, 93.8, 94)]
    assert 'BC' in _codes(b)


def test_reentry_shape():
    b = _flat(25) + [('r1', 100, 100.2, 97, 97.5), ('r2', 97.4, 97.6, 95, 95.5), ('g', 96, 101.5, 95.8, 101)]
    assert 'RE' in _codes(b)


def test_noise_reading():
    zig = [(f'z{i}', 100, 101, 99, 100.5 if i % 2 else 99.5) for i in range(30)]
    nz = cp.noise(zig)
    assert nz['flips'] == 1.0 and nz['eff'] < 0.1
    trend = [(f't{i}', 100 + i, 101 + i, 99.9 + i, 100.9 + i) for i in range(30)]
    nt = cp.noise(trend)
    assert nt['flips'] == 0.0 and nt['eff'] == 1.0
    assert cp.noise(trend[:10]) is None

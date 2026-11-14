"""The falling stock-and-industry skip (mtl/fallgroup.py, rule 24): no new buy of a stock making lower highs and lower
lows with its industry doing the same and down over 2 months, unless at an extreme low, its channel low or broken out."""
import math
from datetime import date, timedelta

from mtl import fallgroup as F


def _cal(n):
    d, out = date(2023, 1, 1), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


N = 400


def _wave(i, base, slope, amp=0.06, period=20):
    """A falling zigzag: lower highs and lower lows."""
    return base * (1 + slope * i) * (1 + amp * math.sin(2 * math.pi * i / period))


def _bars(cal, closes, spread=0.01):
    return [(d, c, c * (1 + spread), c * (1 - spread), c) for d, c in zip(cal, closes)]


def _setup(stock_closes=None, peer_slope=-0.001):
    cal = _cal(N)
    peers = {f'P{j}': [_wave(i, 100 + j, peer_slope, 0.05, 22 + j) for i in range(N)] for j in range(4)}
    st = stock_closes or [_wave(i, 100, -0.0008, 0.05, 20) for i in range(N)]
    prices = {t: dict(zip(cal, c)) for t, c in peers.items()}
    prices['X'] = dict(zip(cal, st))
    bars = {'X': _bars(cal, st)}
    ind = {t: 'Widgets' for t in prices}
    return F.FallGroup(bars, prices, ind, cal), cal


def _first(fg, k0=300):
    """The first session from k0 the reading says skip (or the last reading)."""
    for k in range(k0, N):
        r = fg.reading('X', k)
        if r and r['skip']:
            return k, r
    return None, None


def test_skips_a_stock_falling_with_its_industry():
    fg, _ = _setup()
    k, r = _first(fg)
    assert k is not None and r['why'] == 'falling with its industry'
    assert not fg.buy_ok()('X', k)


def test_not_when_the_industry_is_rising():
    fg, _ = _setup(peer_slope=0.002)
    assert _first(fg)[0] is None


def test_lines_and_pivots():
    a = [1, 2, 3, 2, 1, 0, 1, 2, 1, 0, -1, 0, 1]
    assert F.pivots(a, len(a) - 1, look=20, hi=True, w=2) == [2, 7]
    assert F.line_at([10, 0, 8], 0, 2, 4) == 6
    assert F.lower_both([5, 9, 5, 4, 5, 7, 5, 4, 5, 4, 5], [5, 1, 5, 6, 5, 3, 5, 6, 5, 6, 5], 10, look=20) is None


def test_reasons_it_still_buys():
    fg, _ = _setup()
    reasons = {(fg.reading('X', k) or {}).get('why') for k in range(300, N)}
    assert reasons & {'channel low', 'extreme low', 'broke its down channel'}

import math
from datetime import date, timedelta

from mtl.trendline import TL_DAYS, breaks, find_line, trendline_state
from mtl.rotation import weekly


def _days(n):
    out, d = [], date(2020, 1, 6)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(anchors):
    """Daily bars along straight lines between (week, close) anchors (each anchor on that week's Wednesday)."""
    pts = [(5 * w + 2, p) for w, p in anchors]
    cl = []
    for (i0, p0), (i1, p1) in zip(pts[:-1], pts[1:]):
        cl += [p0 + (p1 - p0) * (i - i0) / (i1 - i0) for i in range(i0, i1)]
    cl.append(pts[-1][1])
    return [(d, c, c * 1.002, c * 0.998, c) for d, c in zip(_days(len(cl)), cl)]


LINE = lambda w: 100 * math.exp(0.004 * w)   # the rising support line


def _path(lows, end):
    """Up 10% between the dips at `lows` (weeks, each on the line), then a slide to `end` = (week, price)."""
    a = [(0, LINE(0) * 1.08)]
    for i, w in enumerate(lows):
        a.append((w, LINE(w)))
        nxt = lows[i + 1] if i + 1 < len(lows) else w + 10
        a.append(((w + nxt) // 2, LINE((w + nxt) / 2) * 1.10))
    return _bars(a + [end])


def test_three_evenly_spaced_touches_make_a_line_and_its_break_fires_once():
    bars = _path([10, 30, 50], (72, 125))
    found = breaks(bars)
    assert len(found) == 1
    k, ln = found[0]
    assert ln['a'][0] == bars[54][0] and ln['b'][0] == bars[254][0]        # the weeks of the week-10 and week-50 dips (dated Friday)
    assert len(ln['touches']) == 3 and bars[k][4] < ln['level'] <= bars[k - 1][4] * 1.01
    on = trendline_state(bars, k)
    assert on['on'] and on['last']['ago'] == 0 and on['last']['date'] == bars[k][0]
    off = trendline_state(bars, k + TL_DAYS)
    assert not off['on'] and off['last']['date'] == bars[k][0]


def test_uneven_touches_or_a_short_line_do_not_count():
    # dips at weeks 10, 14 and 50: gaps of 4 and 36 weeks, far from even
    assert find_line(weekly(_path([10, 14, 50], (60, LINE(60) * 1.05)))) is None
    # dips 8 weeks apart: the line spans only 16 weeks
    assert find_line(weekly(_path([10, 18, 26], (36, LINE(36) * 1.05)))) is None


def test_four_even_touches_count_and_the_line_is_watched_before_it_breaks():
    bars = _path([10, 24, 38, 52], (60, LINE(60) * 1.06))
    st = trendline_state(bars)
    assert not st['on'] and st['last'] is None
    assert st['line'] and len(st['line']['touches']) >= 3 and st['line']['gap'] > 0

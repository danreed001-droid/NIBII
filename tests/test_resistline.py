"""The resistance-line exit (mtl/resistline.py, rule 22): a Friday test of a clearly falling line near the high arms it;
out on the first red candle closing lower under the line; back in on a daily close 0.3% over the line or after two weeks."""
from datetime import date, timedelta

from mtl import resistline as R

K = 324   # a Friday (the calendar starts on a Monday, weekdays only)


def _cal(n):
    d, out = date(2024, 1, 1), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(n=K + 1, top=100.0, after=None, green=False):
    """Rise to `top`, then lower highs on a falling line (pivots at 270, 290, 310), a 3% down day at 318 and a Friday
    test of the line at K; after: closes as a share of the line for sessions after K."""
    line = lambda i: 99.5 - 0.05 * (i - 270)
    c = []
    for i in range(n):
        if i <= 259:
            v = 80 + (top - 80) * i / 259
        elif i in (270, 290, 310):
            v = line(i) * 0.999
        elif any(abs(i - p) <= 3 for p in (270, 290, 310)):
            v = line(i) * (0.985 - 0.004 * min(abs(i - p) for p in (270, 290, 310)))
        elif 318 <= i < K:
            v = line(i) * (0.94 + 0.01 * (i - 318))
        elif i == K:
            v = line(i) * 0.985
        elif i > K:
            v = line(i) * (after if after is not None else 0.97)
        else:
            v = line(i) * 0.97
        c.append(v)
    h = [x * 1.001 for x in c]
    for p in (270, 290, 310):
        h[p] = line(p)
    h[K] = line(K) * 0.999
    o = list(c)
    o[K] = c[K] * (0.996 if green else 1.004)      # the test day: a red candle closing lower (or green)
    cal = _cal(n)
    return [(cal[i], o[i], h[i], c[i] * 0.99, c[i]) for i in range(n)], cal


def test_fires_on_a_friday_test_near_the_high():
    bars, cal = _bars()
    r = R.reading(*R._series(bars, cal), K)
    assert r['signal'] and r['line']['touches'] >= R.TOUCHES and r['bigDrop'] and r['near']
    days, log = R.out_days(bars, cal, start=cal[0], dest=lambda k: 'TLT')
    assert log == [dict(date=cal[K], test=cal[K], to='TLT', line=log[0]['line'], touches=log[0]['touches'], back=None)]
    assert days == {cal[K]: 'TLT'}


def test_not_on_a_weekday_before_the_week_ends():
    bars, cal = _bars()
    days, log = R.out_days(bars[:K + 1], cal[:K + 1], start=cal[0], week_closed=False)
    assert not days and not log


def test_not_deep_under_the_high():
    bars, cal = _bars(top=120.0)   # SPY ~17% under its 1-year high: a bear-market rally, not a pullback
    assert not R.reading(*R._series(bars, cal), K)['signal']


def test_back_after_two_weeks_or_a_break():
    bars, cal = _bars(n=K + 12)            # stays under the line: back at the second week's end
    days, log = R.out_days(bars, cal, start=cal[0])
    assert log[0]['back'] == cal[K + 10] and len(days) == 10 and set(days.values()) == {'CASH'}
    bars, cal = _bars(n=K + 12, after=1.01)   # the next day closes 1% over the line: back that day
    days, log = R.out_days(bars, cal, start=cal[0])
    assert log[0]['back'] == cal[K + 1] and len(days) == 1


def test_waits_for_a_red_candle():
    bars, cal = _bars(n=K + 3, green=True)    # the test day is green and the next two don't close lower in red
    days, log = R.out_days(bars, cal, start=cal[0])
    assert not days and log == [dict(date=cal[K], armed=True, line=log[0]['line'], touches=log[0]['touches'], back=None)]


def test_not_on_a_flat_line():
    bars, cal = _bars()
    old = R.MIN_SLOPE
    try:
        R.MIN_SLOPE = 0.01                    # a line must fall 1% a session: this one (about 0.05%) is too flat
        assert not R.reading(*R._series(bars, cal), K)['signal']
    finally:
        R.MIN_SLOPE = old


def test_apply_only_where_the_plan_holds_stocks():
    cal = _cal(6)
    modes = {cal[0]: 'boost', cal[1]: 'boost', cal[2]: 'GLD', cal[3]: 'boost', cal[4]: 'boost'}
    m, w, h, held = R.apply_resist(modes, {}, {cal[1]: 'TLT'}, {cal[1]: 'CASH', cal[2]: 'CASH', cal[3]: 'CASH'}, cal)
    assert (m[cal[1]], m[cal[2]], m[cal[3]], m[cal[4]]) == ('CASH', 'GLD', 'CASH', 'boost')
    assert held == {cal[1], cal[3]} and cal[1] not in h
    assert w[cal[1]] == 'resist' and w[cal[4]] == 'resist-end'

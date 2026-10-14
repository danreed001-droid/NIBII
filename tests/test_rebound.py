"""mtl/rebound.py - the default plan's rebound rule: stay in stocks after a deep drop that has started to turn."""
import pandas as pd

from mtl import rebound as rb


def path(points):
    """Closes along straight lines between (day, price) points."""
    out = []
    for (d0, p0), (d1, p1) in zip(points, points[1:]):
        out += [p0 + (p1 - p0) * (i / (d1 - d0)) for i in range(d1 - d0)]
    return out + [points[-1][1]]


CAL = [d.date().isoformat() for d in pd.bdate_range('2024-01-01', periods=151)]
# up to 125 on day 99, down 17% to 104 by day 120, a bounce, a higher low (106) on day 132, then up
SPY = path([(0, 100), (99, 125), (120, 104), (126, 109), (132, 106), (150, 112)])
BARS = [(d, c, c + 0.5, c - 0.5, c) for d, c in zip(CAL, SPY)]


def havens(tlt_up):
    tlt = path([(0, 100), (99, 100), (150, 100 * (1 + tlt_up))])
    return {'TLT': dict(zip(CAL, tlt)), 'GLD': {d: 50.0 for d in CAL}}


def test_on_after_a_deep_drop_with_havens_up_and_a_daily_higher_low():
    r = rb.reading(BARS, havens(0.06), CAL, 137)
    assert r['drop'] >= rb.REB_DROP and r['high'] == [CAL[99], 125.0]
    assert r['best'] >= rb.REB_HAVEN and r['hl'] and r['on']
    assert r['lows'][-1][0] == CAL[132] and r['lows'][-1][1] > r['lows'][-2][1]


def test_off_without_the_higher_low_the_haven_move_or_the_depth():
    assert not rb.reading(BARS, havens(0.06), CAL, 122)['on']          # still falling: no higher low yet
    assert not rb.reading(BARS, havens(0.0), CAL, 137)['on']           # gold and bonds flat
    shallow = [(d, o, h, lo, c) for d, o, h, lo, c in BARS]
    shallow = [(d, 125 - (125 - c) * 0.5, 125 - (125 - h) * 0.5, 125 - (125 - lo) * 0.5, 125 - (125 - c) * 0.5)
               for d, o, h, lo, c in shallow]                         # the same shape, half as deep (~8%)
    assert not rb.reading(shallow, havens(0.06), CAL, 137)['on']


def test_apply_holds_stocks_over_the_other_rules_and_logs_the_switches():
    days = rb.rebound_days(BARS, havens(0.06), CAL, CAL[0])
    assert days and min(days) > CAL[132]
    modes = {d: ('TLT' if d >= CAL[110] else 'boost') for d in CAL}
    half = {CAL[140]: 'GLD'}
    m, why, h, held = rb.apply_rebound(modes, {}, half, days, CAL)
    first = min(days)
    assert m[first] == 'boost' and why[first] == 'rebound' and CAL[140] not in h
    assert held == {d for d in days if modes[d] != 'boost' or d in half}
    st = rb.rebound_state(BARS, havens(0.06), CAL, 140, held)
    assert st['active'] and st['log'][0][0] == first and st['n'] == 1

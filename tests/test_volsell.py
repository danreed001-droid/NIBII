import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import volsell  # noqa: E402


def _cal(n, start=date(2020, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _data(cal, day, chg, mult):
    px = {d: 100.0 for d in cal}
    vol = {d: 1_000_000 for d in cal}
    for i, d in enumerate(cal):
        if i >= day:
            px[d] = 100.0 * (1 + chg)
    vol[cal[day]] = int(1_000_000 * mult)
    return {'A': px}, {'A': vol}


def test_sell_needs_a_big_drop_on_heavy_volume_after_the_buy():
    cal = _cal(120)
    px, vol = _data(cal, 100, -0.07, 5)
    vs = volsell.VolSell(px, vol, cal)
    assert vs.sell('A', 100, entry_k=90)
    assert not vs.sell('A', 100, entry_k=100)          # not on the day it was bought
    px2, vol2 = _data(cal, 100, -0.04, 5)               # a 4% drop is not enough
    assert not volsell.VolSell(px2, vol2, cal).sell('A', 100, 90)
    px3, vol3 = _data(cal, 100, -0.07, 3)               # 3x volume is not enough
    assert not volsell.VolSell(px3, vol3, cal).sell('A', 100, 90)


def test_no_buy_within_five_sessions_of_a_heavy_volume_down_close():
    cal = _cal(120)
    px, vol = _data(cal, 100, -0.01, 4.5)
    vs = volsell.VolSell(px, vol, cal)
    ok = vs.buy_ok(lambda t, k: True)
    assert not ok('A', 100) and not ok('A', 104) and ok('A', 105) and ok('A', 99)
    pu, vu = _data(cal, 100, 0.03, 6)                   # a heavy-volume UP close doesn't block
    assert volsell.VolSell(pu, vu, cal).buy_ok()('A', 102)
    assert vs.info('A', 102)['heavyDown'] == cal[100]

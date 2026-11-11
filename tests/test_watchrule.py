"""The watch rule from the owner's review picks (mtl/watchrule.py): swings, channels and the decision it shows."""
import math
from datetime import date, timedelta

from mtl import watchrule


def _doc(spy, tlt=None, gold=None, start=date(2001, 1, 2)):
    n = len(spy)
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return {'dd': days, 'ds': spy, 'db': tlt or [100.0] * n, 'dg': gold or [100.0] * n, 'df': [None] * n}


def test_zigzag_confirms_swings_after_the_turn():
    x = [100, 104, 108, 110, 104, 101, 103, 109, 112]
    piv = watchrule.zigzag(x, 0.05)
    assert piv[0] == (0, 'L', 2)                           # 100 confirmed once a close is 5% above it
    assert piv[1] == (3, 'H', 4)                           # 110 confirmed once a close is 5% under it
    assert piv[2] == (5, 'L', 7)


def test_strip_holds_every_close():
    x = [100 * math.exp(0.001 * i) * (1.01 if i % 3 == 0 else 1.0) for i in range(40)]
    s, lo, up = watchrule.strip(x, 0, 39)
    for i in range(40):
        y = math.log(x[i])
        assert lo + s * i - 1e-9 <= y <= up + s * i + 1e-9


def test_quiet_uptrend_agrees_with_the_plan():
    spy = [100 * 1.0005 ** i * (1 + 0.04 * math.sin(i / 9)) for i in range(700)]
    W = watchrule.compute(_doc(spy), [{'d': '2003-09-01', 'mode': 'boost'}])
    assert W['rule'] is None and W['verdict'] == 'agree' and W['plan'] == 's'
    assert not W['conds']['cross']


def test_falling_market_with_rising_gold_steps_out_and_differs_from_stocks():
    up = [100 * 1.0008 ** i for i in range(400)]
    spy, v = list(up), up[-1]
    for leg in range(6):                       # a falling market: 9% down legs, 6% up legs, 15 sessions each
        for step in (0.991 ** (1 / 1.5),) * 15 + (1.06 ** (1 / 15),) * 15:
            v *= step
            spy.append(v)
    for _ in range(8):                         # then a break under the channel
        v *= 0.98
        spy.append(v)
    gold = [100 * 1.001 ** i for i in range(len(spy))]
    tlt = [100 * 1.0004 ** i for i in range(len(spy))]
    W = watchrule.compute(_doc(spy, tlt, gold), [{'d': '2003-01-01', 'mode': 'boost'}], history=True)
    assert any(s is not None for s in W['states'][400:])          # it stepped out during the fall
    assert all(s is None for s in W['states'][:400])               # never in the steady rise
    out = [s for s in W['states'] if s is not None]
    assert set(out) <= {'b', 'g'}
    if W['rule'] is not None:
        assert W['verdict'] == 'differ'


def test_plan_code_and_haven_verdict():
    spy = [100 * 1.0005 ** i for i in range(300)]
    W = watchrule.compute(_doc(spy), [{'d': '2002-01-01', 'mode': 'GLD'}])
    assert W['plan'] == 'g' and W['verdict'] == 'agree'

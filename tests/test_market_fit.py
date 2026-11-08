import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import market_fit as mf  # noqa: E402


def _r(year, give, good, plan=0.5, pick=0.1):
    return dict(year=year, giveBack=give, spike=0.5, doublers=3, good=good, events=50, plan=plan, pick=pick, index=0.08)


def test_choose_from_the_doublers_alone():
    assert mf.choose(_r(2020, 0.30, 6.0)) == 'index'               # poor runner quality: the index
    assert mf.choose(_r(2020, 0.15, 3.0)) == 'plan'                # good quality, enough good doublers
    assert mf.choose(_r(2020, 0.15, 1.0)) == 'pick'                # good quality, thin supply: the 12-month pick
    assert mf.choose(_r(2020, 0.15, 3.0, plan=-0.5, pick=0.9)) == 'plan'   # past returns are not used
    assert mf.choose(None) == 'index' and mf.choose(_r(2020, None, 3.0)) == 'index'


def test_a_change_needs_two_reviews_in_a_row():
    revs = [_r(2015, 0.1, 3), _r(2016, 0.3, 3), _r(2017, 0.1, 3), _r(2018, 0.3, 3), _r(2019, 0.3, 3)]
    modes = [m for _, _, m in mf.decide(revs)]
    assert modes == ['plan', 'plan', 'plan', 'plan', 'index']


def _cal(n, start=date(2000, 1, 3)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_records_and_summary_on_a_toy_market():
    cal = _cal(260 * 12)
    closes = {}
    for k in range(30):
        g = 1.0005 + 0.00005 * k if k % 3 else 1.004      # every 3rd stock doubles and keeps going (no give-back)
        v, s = 20.0, {}
        for d in cal:
            v *= g
            s[d] = v
        closes[f'S{k}'] = s
    index = {d: 100 * 1.0003 ** i for i, d in enumerate(cal)}
    plan = {d: 100 * 1.006 ** i for i, d in enumerate(cal)}          # a plan well ahead of the simple pick
    rows, events = mf.records(closes, cal, lambda t, d: True, index, plan)
    assert rows and events and not any(e[2] for e in events)           # the doublers never gave back half
    s = mf.summary(rows, events, list(range(2008, 2012)), live_mode='plan')
    assert s['reviews'][-1]['good'] >= 2 and s['mode'] == 'plan' and not s['alarm'] and s['reviews'][-1]['giveBack'] == 0.0

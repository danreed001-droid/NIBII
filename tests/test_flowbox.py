"""mtl/flowbox.py: the weekly rows behind the scanner page's money flow animation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl import flowbox  # noqa: E402


def _days(n, start=(2026, 1, 5)):
    from datetime import date, timedelta
    d0 = date(*start)
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_rsi_extremes():
    up = [(d, 100 + i) for i, d in enumerate(_days(30))]
    dn = [(d, 100 - i) for i, d in enumerate(_days(30))]
    assert flowbox.rsi(up)[up[-1][0]] == 100.0
    assert flowbox.rsi(dn)[dn[-1][0]] == 0.0
    assert up[13][0] not in flowbox.rsi(up) and up[14][0] in flowbox.rsi(up)


def test_join_scales_to_meet():
    old = [('2026-01-05', 100.0), ('2026-01-06', 110.0)]
    new = [('2026-01-06', 55.0), ('2026-01-07', 60.0)]
    j = flowbox.join(old, new)
    assert j[:2] == old and j[2][0] == '2026-01-07' and abs(j[2][1] - 120.0) < 1e-9


def test_held_codes_plan_then_ledger():
    rows = [['2026-01-05', 1, 0, 0, 0, 0], ['2026-01-07', 0, 1, 0, 0, 0]]
    entries = [{'d': '2026-01-09', 'mode': 'DBMF'}, {'d': '2026-01-12', 'mode': 'boost'}]
    h = flowbox.held_codes(rows, entries, ['2026-01-06', '2026-01-08', '2026-01-09', '2026-01-13'], end='2026-01-08')
    assert h == {'2026-01-06': 's', '2026-01-08': 'g', '2026-01-09': 'f', '2026-01-13': 's'}


def test_build_weekly_rows():
    days = _days(60)
    ph = {'end': days[39], 'held': [[days[0], 1, 0, 0, 0, 0]],
          'prices': {'dates': days[:40], 'SPY': [100 + i for i in range(40)], 'gold': [50.0] * 40, 'bonds': [80 - i * 0.1 for i in range(40)]}}
    fresh = {'SPY': [(d, 10 + i * 0.1) for i, d in enumerate(days)], 'TLT': [(d, 8.0) for d in days],
             'GLD': [(d, 5.0) for d in days], 'DBMF': [(d, 30.0) for d in days[20:]]}
    out = flowbox.build(ph, fresh, [{'d': days[45], 'mode': 'GLD'}])
    assert out['d'][-1] == days[-1] and len(out['d']) == 12        # 60 sessions from a Monday = 12 weeks
    assert all(len(out[k]) == len(out['d']) for k in ('s', 'b', 'g', 'f', 'rs', 'rb', 'rg', 'rf')) and len(out['h']) == 12
    assert out['f'][0] is None and out['f'][-1] == 30.0
    k = out['d'].index(days[44])                                   # SPY runs on from the plan history without a jump
    assert abs(out['s'][k] - 144.0) < 0.01                         # 139 at the join, then +1 a day as before
    assert out['h'][-1] == 'g' and out['h'][0] == 's'
    assert out['dd'] == (days[-flowbox.DAILY:] if flowbox.DAILY else days)
    assert len(out['ds']) == len(out['dd']) and out['df'][0] is None and out['df'][-1] == 30.0

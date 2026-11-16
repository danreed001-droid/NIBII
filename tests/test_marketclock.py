from math import sin
from mtl import marketclock as MC


def _cal(n):
    import pandas as pd
    return [d.date().isoformat() for d in pd.bdate_range('2023-01-02', periods=n)]


def test_angles_and_phases():
    assert MC.phase(MC.angle(65, 8)) == 'rallying'          # strong and rising
    assert MC.phase(MC.angle(65, -8)) == 'rolling over'
    assert MC.phase(MC.angle(35, -8)) == 'falling'
    assert MC.phase(MC.angle(35, 8)) == 'turning up'


def test_build_reads_each_scale_and_the_mood():
    cal = _cal(700)
    up = {d: 100 * 1.002 ** i * (1 + 0.01 * sin(i / 3)) for i, d in enumerate(cal)}     # stocks and oil rising
    dn = {d: 100 * 0.999 ** i * (1 + 0.01 * sin(i / 4)) for i, d in enumerate(cal)}     # gold and bonds sliding
    out = MC.build({'SPY': up, 'OIL': up, 'GLD': dn, 'TLT': dn}, cal, days=60)
    assert len(out['dates']) == 60 and out['dates'][-1] == cal[-1]
    spy = next(a for a in out['assets'] if a['key'] == 'SPY')
    assert all(v is not None for v in spy['d'] + spy['w'] + spy['m'])
    assert MC.phase(spy['m'][-1]) in ('rallying', 'rolling over')        # strong on the monthly
    assert len(out['assets']) == 4 and out['mood'][-1] is not None and out['mang'][-1] is not None


def test_short_history_is_skipped():
    cal = _cal(100)
    out = MC.build({'SPY': {d: 1.0 + i for i, d in enumerate(cal)}}, cal)
    assert out['assets'] == [] and out['mood'][-1] is None

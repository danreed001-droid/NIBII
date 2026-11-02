import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import hotcomm, jobwarn, nearhigh, volweight  # noqa: E402


def _cal(n, start=date(2019, 1, 7)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_near_high_doubles_a_stock_within_3pct_of_its_year_high():
    cal = _cal(300)
    px = {'A': {d: 100 + i * 0.1 for i, d in enumerate(cal)}, 'B': {d: 100.0 for d in cal}}
    px['B'][cal[100]] = 120.0                      # B's high was earlier, it now sits 17% under it
    nh = nearhigh.NearHigh(px)
    assert nh.factor('A', cal, 299) == 2.0 and nh.factor('B', cal, 299) == 1.0
    assert nh.factor('A', cal, 200) == 1.0         # needs a year of history
    assert nh.info('B', cal, 299)['off'] < -0.15


def test_cap_spreads_the_excess():
    w = volweight.capped({'A': 8 / 12, 'B': 1 / 12, 'C': 1 / 12, 'D': 1 / 12, 'E': 1 / 12}, 0.40)
    assert abs(w['A'] - 0.40) < 1e-9 and abs(sum(w.values()) - 1) < 1e-9 and abs(w['B'] - 0.15) < 1e-9


def test_hot_commodity_blocks_only_its_theme_while_hot():
    cal = _cal(400)
    cu = {d: 100.0 * (1 + (0.6 if i >= 380 else 0.0)) for i, d in enumerate(cal)}
    oil = {d: 100.0 for d in cal}
    hc = hotcomm.HotComm({'FCX': hotcomm.COPPER, 'XOM': hotcomm.OIL}, {hotcomm.COPPER: cu, hotcomm.OIL: oil}, cal)
    assert hc.blocked('FCX', 399) and not hc.blocked('XOM', 399) and not hc.blocked('AAPL', 399)
    assert not hc.blocked('FCX', 300)
    ok = hc.buy_ok(lambda t, k: True)
    assert not ok('FCX', 399) and ok('XOM', 399)
    assert hc.state(399)['HG=F']['hot']


def test_themes_read_the_industry_file(tmp_path):
    p = tmp_path / 'ind.csv'
    p.write_text('symbol,industry\nNUE,Steel/Iron Ore\nXOM,Oil & Gas Production\nAAPL,Computer Manufacturing\n')
    th = hotcomm.themes(str(p))
    assert th == {'NUE': hotcomm.COPPER, 'XOM': hotcomm.OIL}


def test_unemployment_flag_needs_a_rise_and_a_weak_market():
    cal = _cal(700)
    months = sorted({d[:7] for d in cal})
    ur = {m + '-01': (4.0 if i < 24 else 4.8) for i, m in enumerate(months)}
    spy = {d: (100.0 if i < 600 else 80.0) for i, d in enumerate(cal)}
    flag, rise, gap = jobwarn.readings(cal, spy, ur)
    st = jobwarn.starts(cal, flag)
    assert st and st[0] >= cal[600]                # only once SPY is under its average as well
    i = cal.index(st[0])
    assert rise[i] >= 0.3 and gap[i] < 0
    spy_up = {d: 100.0 + i for i, d in enumerate(cal)}
    f2, _, _ = jobwarn.readings(cal, spy_up, ur)
    assert not f2.any()                            # rising unemployment alone is not enough
    s = jobwarn.state(cal, len(cal) - 1, flag, rise, gap, set(), st)
    assert s['th'] == 0.3 and s['hold'] == 21

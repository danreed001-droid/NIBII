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
    full = MC.build({'SPY': up, 'OIL': up, 'GLD': dn, 'TLT': dn}, cal)
    assert full['dates'][0] == cal[0] and full['dates'][-60:] == out['dates']
    assert len(out['dates']) == 60 and out['dates'][-1] == cal[-1]
    spy = next(a for a in out['assets'] if a['key'] == 'SPY')
    assert all(v is not None for v in spy['d'] + spy['w'] + spy['m'])
    assert MC.phase(spy['m'][-1]) in ('rallying', 'rolling over')        # strong on the monthly
    assert spy['mr'][-1] > 50 and all(0 <= v <= 100 for v in spy['dr'] + spy['wr'] + spy['mr'])
    assert len(out['assets']) == 4 and out['mood'][-1] is not None and out['mang'][-1] is not None


def test_short_history_is_skipped():
    cal = _cal(100)
    out = MC.build({'SPY': {d: 1.0 + i for i, d in enumerate(cal)}}, cal)
    assert out['assets'] == [] and out['mood'][-1] is None


def test_splice_joins_a_proxy_before_the_fund_starts():
    fund = {'2020-01-03': 10.0, '2020-01-06': 11.0}
    proxy = {'2020-01-01': 50.0, '2020-01-02': 45.0, '2020-01-03': 50.0, '2020-01-06': 60.0}
    s = MC.splice(fund, proxy)
    assert s['2020-01-01'] == 10.0 and s['2020-01-02'] == 9.0 and s['2020-01-06'] == 11.0     # rescaled at Jan 3; the fund wins after
    assert MC.splice({}, proxy) == proxy and MC.splice(fund, {}) == fund


def test_weekly_reading_matches_a_direct_recompute():
    cal = _cal(500)
    px = {d: 100 * (1 + 0.05 * sin(i / 9)) * 1.0005 ** i for i, d in enumerate(cal)}
    c = [px[d] for d in cal]
    k = 480
    fast, lev = (x[0] for x in MC._scale_angles(c, cal, [k], 'w', 3))
    keys = [MC._period_key(d, 'w') for d in cal]
    ends = [i for i in range(len(cal)) if i + 1 == len(cal) or keys[i + 1] != keys[i]]
    pts = [c[i] for i in ends if i < k and keys[i] != keys[k]] + [c[k]]
    r = MC.rsi(pts)
    assert abs(((fast - MC.angle(r[-1], r[-1] - r[-4]) + 180) % 360) - 180) <= 1
    assert abs(lev - r[-1]) < 1e-9


def test_news_keeps_support_and_shock_events_only():
    evs = [{'d': '2020-03-23', 'type': 'QE / backstop', 'what': 'Fed unlimited QE'},
           {'d': '2020-03-09', 'type': 'Crash / glitch', 'what': 'Oil price war crash ' + 'x' * 200},
           {'d': '2020-03-24', 'type': 'Turning point', 'what': 'Bottom'}, {'d': '2020-03-25', 'type': 'War / terror'}]
    out = MC.news(evs)
    assert [r[:3] for r in out] == [['2020-03-09', -1, 'Crash / glitch'], ['2020-03-23', 1, 'QE / backstop']]
    assert len(out[0][3]) <= 110 and MC.news(None) == []


def test_trend_lines_chain_back_to_the_closes():
    dates = ['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-06']
    out = MC.trend_lines({'XLK': {'2020-01-02': 100.0, '2020-01-03': 101.5, '2020-01-06': 99.0}, 'SPY': {},
                          'GLD': {'2020-01-03': 50.0, '2020-01-06': 51.0}}, dates)
    assert out['names'] == [['XLK', 'Tech'], ['GLD', 'Gold']] and out['r']['XLK'] == [None, 0, 150, -246]
    assert out['r']['GLD'] == [None, None, 0, 200]
    v = 1.0
    for r in out['r']['XLK'][2:]:
        v *= 1 + r / 1e4
    assert abs(v - 0.99) < 1e-3

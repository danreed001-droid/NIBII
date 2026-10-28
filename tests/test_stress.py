"""Market stress card: dominoes across asset classes, the drop study's warning signs, news context, the page."""
import importlib.util
import os
from datetime import date, timedelta

from mtl import stress


def days(n, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def wiggle(ds, base=100.0, amp=0.01, tail=None):
    """{date: close}: small alternating moves (a normal swing), then an optional tail of extra daily moves."""
    out, p = {}, base
    for i, d in enumerate(ds):
        p *= 1 + (amp if i % 2 else -amp)
        out[d] = p
    if tail:
        for d, m in zip(ds[-len(tail):], tail):
            p *= 1 + m
            out[d] = p
    return out


def test_z5_flags_a_move_far_beyond_the_normal_swing():
    ds = days(100)
    calm = list(wiggle(ds).values())
    assert abs(stress.z5(calm)) < 1
    jump = list(wiggle(ds, tail=[-0.03] * 5).values())
    assert stress.z5(jump) < -2
    assert stress.z5(calm[:50]) is None                         # too little history
    assert stress.z5(calm[:-1] + [-5.0]) is None                # a price at or below zero (oil, Apr 2020)


def test_dominoes_counts_sharp_movers_and_flips_per_dollar_quotes():
    ds = days(120)
    series = {t: wiggle(ds) for t, _ in stress.DOMINOES}
    series['SPY'] = wiggle(ds, tail=[-0.03] * 5)
    series['JPY=X'] = wiggle(ds, tail=[-0.03] * 5)               # fewer yen per dollar: the yen rose
    d = stress.dominoes(series, ds[-1])
    assert d['of'] == 12 and d['n'] == 2
    names = {m[0]: m for m in d['moves']}
    assert names['S&P 500'][1] < 0 and names['S&P 500'][2] < 0
    assert names['Yen'][1] > 0 and names['Yen'][2] > 0


def flat_then(n, path):
    ds = days(n + len(path))
    vals = [90.0 + 10.0 * i / (n - 1) for i in range(n)] + path   # a steady climb to 100, then the path
    return ds, dict(zip(ds, vals))


def test_warnings_in_a_drop_counts_the_three_signs():
    ds, spy = flat_then(300, [100 * (1 - 0.012 * k) for k in range(1, 9)])   # -9.6% in 8 sessions, 5% by day 5
    w = stress.warnings(spy, ds[-1])
    assert w['mode'] == 'drop' and w['signs']['fast'] and w['signs']['below200'] and not w['signs']['credit']
    assert w['n'] == 2 and w['odds'] == [22, 41]


def test_warnings_near_the_high_reads_the_narrow_signs():
    ds, spy = flat_then(300, [100.5] * 5)
    lag = {d: v * (1 - 0.0003 * i) for i, (d, v) in enumerate(spy.items())}   # drifts behind the index
    w = stress.warnings(spy, ds[-1], rsp=lag, iwm=lag)
    assert w['mode'] == 'calm' and w['signs']['small'] and w['signs']['ew'] and not w['signs']['cg']
    assert w['n'] == 2 and w['odds'] == stress.NARROW_ODDS[2]
    assert stress.warnings(dict(list(spy.items())[:100]), ds[99]) is None


def test_news_context_groups_recent_events_by_trigger_family():
    ev = [dict(d='2026-10-14', type='Inflation / yields', what='Hot CPI'), dict(d='2026-10-10', type='Fed hike / hawkish', what='Hike'),
          dict(d='2026-09-01', type='War / terror', what='Too old'), dict(d='2026-10-20', type='Big up day', what='No family')]
    out = stress.news_context(ev, '2026-10-27')
    assert len(out) == 1 and out[0][0] == 'Fed & inflation' and out[0][1] == ['Hot CPI (2026-10-14)', 'Hike (2026-10-10)']
    assert out[0][2:] == list(stress.DROP_FAMILIES['Fed & inflation'])


def test_stress_page_renders_card_and_crowding_charts():
    spec = importlib.util.spec_from_file_location('render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    S = dict(asOf='2026-10-27', dominoes=dict(n=1, of=12, moves=[['Oil', -2.4, -0.081]]), hist=[['2026-10-26', 0], ['2026-10-27', 1]],
             warn=dict(date='2026-10-27', offHigh=-0.012, drop=-0.012, peak='2026-10-06', mode='calm', n=2, odds=0.181, base=0.097,
                       signs=dict(small=True, ew=True, cg=False), vals=dict(small=-0.087, ew=-0.047, cg=0.05)))
    G = dict(asOf='2026-10-20', window=156, crowded=0.9, rows=[dict(name='Silver', date='2026-10-20', net=0.17, pct=0.27, prev=0.37,
             lo=0, hi=0.4, flag=None, hist=[['2026-10-13', 0.37, 0.2, 50.0], ['2026-10-20', 0.27, 0.17, 48.0]])])
    scan = dict(asOf='2026-10-27', plan=dict(auto=dict(stress=S, crowding=G)))
    page = rs.stress_page(scan)
    assert 'Market stress' in page and 'Oil' in page and '2 of 3 on' in page and 'Speculator crowding' in page and 'cc-data' in page
    assert 'href="stress.html"' in rs.render(dict(asOf='2026-10-27', holdings=[], table=[], trades=[], curves={}, years={}, stats={}))
    assert rs.stress_html(dict(plan=dict(auto={}))) == ''


def test_page_tickers_skip_the_scans_own_series():
    t = stress.page_tickers()
    assert 'HG=F' in t and 'IWM' in t and 'ZN=F' in t
    assert not {'SPY', 'TLT', 'IEF', 'GLD', 'QQQ'} & set(t)
    assert t == sorted(set(t))

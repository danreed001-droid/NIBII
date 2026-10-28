"""Speculator crowding gauge: CFTC net long share of open interest, placed in its own 3-year range."""
import importlib.util
import io
import os
import zipfile

from mtl.crowding import CROWDED, WINDOW, gauge, merge, parse, reading

HDR = ['Market and Exchange Names', 'As of Date in Form YYMMDD', 'As of Date in Form YYYY-MM-DD', 'CFTC Contract Market Code',
       'Open Interest (All)', 'Noncommercial Positions-Long (All)', 'Noncommercial Positions-Short (All)']


def cot_zip(rows):
    """A CFTC-style yearly zip: rows of (date, code, open interest, spec long, spec short)."""
    lines = [','.join(f'"{h}"' for h in HDR)]
    for d, code, oi, lo, sh in rows:
        lines.append(f'"X",{d[2:].replace("-", "")},{d},{code},{oi},{lo},{sh}')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('annual.txt', '\n'.join(lines))
    return buf.getvalue()


def weeks(n, start=2020):
    from datetime import date, timedelta
    d0 = date(start, 1, 7)
    return [(d0 + timedelta(weeks=i)).isoformat() for i in range(n)]


def test_parse_keeps_known_markets_and_net_share():
    z = cot_zip([('2026-10-20', '088691', 1000, 600, 100), ('2026-10-20', '999999', 50, 1, 1), ('2026-10-20', '084691', 0, 1, 1)])
    p = parse(z)
    assert list(p) == ['Gold']                      # unknown codes and zero open interest are skipped
    assert p['Gold']['2026-10-20'] == (0.5, 1000.0)


def test_merge_combines_years():
    a = parse(cot_zip([('2025-12-30', '088691', 100, 60, 10)]))
    b = parse(cot_zip([('2026-01-06', '088691', 100, 70, 10)]))
    assert sorted(merge([a, b])['Gold']) == ['2025-12-30', '2026-01-06']


def test_reading_places_the_week_in_its_3_year_range():
    ds = weeks(WINDOW + 2)
    s = {d: (0.0, 1.0) for d in ds}
    s[ds[5]] = (-0.2, 1.0)                           # the low of the window
    s[ds[10]] = (0.4, 1.0)                           # the high
    s[ds[-1]] = (0.4, 1.0)                           # this week ties the high: crowded long
    r = reading(s)
    assert r['date'] == ds[-1] and r['net'] == 0.4 and r['pct'] == 1.0 and r['flag'] == 'long'
    assert r['prev'] == round(0.2 / 0.6, 3)          # last week at 0.0 sat a third of the way up
    s[ds[-1]] = (-0.2, 1.0)
    assert reading(s)['flag'] == 'short'
    s[ds[-1]] = (0.1, 1.0)
    assert reading(s)['flag'] is None
    assert reading({d: (0.0, 1.0) for d in weeks(WINDOW)}) is None   # not a full window yet


def test_gauge_keeps_market_order_and_skips_short_histories():
    ds = weeks(WINDOW + 1)
    m = {'Silver': {d: (0.1, 1.0) for d in ds}, 'Gold': {d: (0.2, 1.0) for d in ds}, 'Copper': {ds[0]: (0.1, 1.0)}}
    g = gauge(m)
    assert [r['name'] for r in g['rows']] == ['Gold', 'Silver'] and g['asOf'] == ds[-1] and g['crowded'] == CROWDED
    assert gauge({}) is None


def test_page_section():
    spec = importlib.util.spec_from_file_location(
        'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    G = dict(asOf='2026-10-20', window=WINDOW, crowded=CROWDED, rows=[
        dict(name='Gold', date='2026-10-20', net=0.5, pct=0.7, prev=0.84, lo=0.3, hi=0.6, flag=None, hist=[['a', 0.5], ['b', 0.7]]),
        dict(name='Nasdaq-100 (e-mini)', date='2026-10-20', net=0.19, pct=0.95, prev=0.91, lo=0, hi=0.2, flag='long', hist=[])])
    html = rs.crowding_html(dict(plan=dict(auto=dict(crowding=G))))
    assert 'Speculator crowding' in html and 'Crowded long' in html and '+50%' in html and '95%' in html and '<polyline' in html
    assert rs.crowding_html(dict(plan=dict(auto=dict(crowding=None)))) == ''


def test_plain_words_summary():
    spec = importlib.util.spec_from_file_location(
        'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    row = lambda name, pct, flag=None: dict(name=name, pct=pct, flag=flag)
    assert 'not making any unusually one-sided bets' in rs.crowding_plain([row('Gold', 0.5), row('Silver', 0.4)])
    t = rs.crowding_plain([row('Nasdaq-100 futures', 0.94, 'long'), row('Gold', 0.5)])
    assert 'betting heavily on the Nasdaq-100 going up' in t and 'not a reliable warning' in t and 'other 1 markets' in t
    t = rs.crowding_plain([row('S&P 500 futures', 0.05, 'short')])
    assert 'going down' in t and 'higher 3 months later 79%' in t and 'does not act' in t

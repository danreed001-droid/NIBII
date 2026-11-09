"""World index trends (mtl/world.py) and the scanner's world markets section."""
import json
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from mtl import world  # noqa: E402


def _days(n, f, start=date(2020, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d.isoformat(), f(len(out))))
        d += timedelta(days=1)
    return out


def test_trend_up_down_mixed():
    up = world.trend(_days(400, lambda i: 100 + i * 0.1))
    assert up['trend'] == 'up' and up['vsMa'] > 0 and up['maUp'] and abs(up['offHigh']) < 1e-9
    assert abs(up['m12'] - ((100 + 399 * 0.1) / (100 + 147 * 0.1) - 1)) < 1e-9
    down = world.trend(_days(400, lambda i: 200 - i * 0.2))
    assert down['trend'] == 'down' and down['vsMa'] < 0
    # a fresh drop under a still-rising average
    mixed = world.trend(_days(400, lambda i: 100 + i * 0.1 if i < 395 else 100))
    assert mixed['trend'] == 'mixed'
    assert world.trend(_days(100, lambda i: 100)) is None


def test_weekly_keeps_last_close_of_each_week():
    w = world.weekly(_days(10, lambda i: float(i)))   # Mon 6 Jan 2020 .. Fri 17 Jan
    assert w == [('2020-01-10', 4.0), ('2020-01-17', 9.0)]


def test_build_shares_one_weekly_calendar():
    a = _days(300, lambda i: 100 + i)
    b = _days(300, lambda i: 50 + i, start=date(2020, 3, 2))   # starts later: None before it
    doc = world.build({'^GSPC': a, '^GDAXI': b})
    assert [m['t'] for m in doc['markets']] == ['^GSPC', '^GDAXI']
    us, de = doc['markets']
    assert len(us['v']) == len(de['v']) == len(doc['d'])
    assert de['v'][0] is None and de['v'][-1] is not None and us['on'] and de['on']
    assert us['trend']['trend'] == 'up'


def test_world_section_renders(tmp_path, monkeypatch):
    import render_scanner as R
    W = world.build({'^GSPC': _days(300, lambda i: 100 + i), '^FTSE': _days(300, lambda i: 100 - i * 0.1)})
    F = dict(win=7, gate=0.25, good=2.0, markets=[
        dict(k='US', country='US', index='S&P 500', reviews=[dict(year=2025, good=7.5, giveBack=0.13, spike=0.5, choice='plan'), dict(year=2026, good=8.2, giveBack=0.13, spike=0.5, choice='plan')]),
        dict(k='SE', country='Sweden', index='OMX 30', stocks=30, reviews=[dict(year=2026, good=0.4, giveBack=0.28, spike=0.51, choice='index')])])
    (tmp_path / 'w.json').write_text(json.dumps(W)); (tmp_path / 'f.json').write_text(json.dumps(F))
    monkeypatch.setattr(R, 'WORLD_PATH', str(tmp_path / 'w.json')); monkeypatch.setattr(R, 'FITWORLD_PATH', str(tmp_path / 'f.json'))
    h = R.world_html()
    assert 'id="world"' in h and 'FTSE 100' in h and 'Runner quality by market' in h
    assert '<b class="neg">28%</b>' in h and 'the index' in h and '1.3' in h   # Sweden: 0.4 good doublers on 30 stocks = 1.3 per 100
    assert '__WM' not in h
    monkeypatch.setattr(R, 'WORLD_PATH', str(tmp_path / 'none.json'))
    assert 'Runner quality by market' in R.world_html() and 'wm-data' not in R.world_html()
    monkeypatch.setattr(R, 'FITWORLD_PATH', str(tmp_path / 'none.json'))
    assert R.world_html() == ''

"""What followed speculator crowding (mtl/crowding_history.py) and its table under the gauge."""
import importlib.util
import json
import os
from datetime import date, timedelta

from mtl import crowding_history as CH


def weeks(n, start='1998-01-06'):
    d = date.fromisoformat(start)
    return [(d + timedelta(weeks=i)).isoformat() for i in range(n)]


def test_spells_and_exits_count_each_episode_once():
    ws = weeks(600)
    # crowded long for 10 weeks (one week dipping out in the middle), then out; crowded short later for 3 weeks
    p = [0.5] * 600
    for i in range(300, 310): p[i] = 0.95
    p[304] = 0.8
    for i in range(400, 403): p[i] = 0.05
    rows = list(zip(ws, p))
    sp = CH.spells(rows, 'long')
    assert len(sp) == 1 and sp[0][0] == ws[300]
    assert CH.exits(rows, 'long') == [ws[311]]          # second straight week out, known then
    assert CH.exits(rows, 'short') == []                # 3 weeks is not a long spell
    assert CH.sign_p(10, 11) < 0.05 and CH.sign_p(6, 12) == 1.0


def test_build_reads_each_market_against_its_normal_move():
    ws = weeks(700)
    pos = {'Gold': {w: ((0.3 if (i // 40) % 2 else -0.1) + 0.001 * i, 1000.0) for i, w in enumerate(ws)}}
    cal, d = [], date(1998, 1, 1)
    while len(cal) < 3600:
        if d.weekday() < 5: cal.append(d.isoformat())
        d += timedelta(days=1)
    px = {'Gold': {c: 100.0 * (1.0002 ** i) for i, c in enumerate(cal)}}
    D = CH.build(pos, px, asof=ws[-1])
    g = D['markets']['Gold']
    assert set(g) >= {'normal', 'long', 'short', 'exitLong', 'exitShort'} and g['normal']['3'] > 0
    for k in ('long', 'short'):
        r = g[k]['3']
        assert r is None or (0 <= r['beat'] <= r['n'] and 0 <= r['p'] <= 1)
    assert CH.build({}, {})['markets'] == {}


def test_table_under_the_gauge(tmp_path):
    spec = importlib.util.spec_from_file_location('render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    c = lambda b, n, p: dict(n=n, beat=b, typ=0.05, p=p)
    m = dict(normal={'1': 0.01, '3': 0.03, '6': 0.06}, long={'n': 16, '1': c(6, 16, 0.45), '3': c(6, 15, 0.6), '6': c(7, 15, 1.0)},
             short={'n': 11, '1': c(9, 11, 0.07), '3': c(10, 11, 0.012), '6': None}, exitLong={'n': 0}, exitShort={'n': 0})
    p = tmp_path / 'h.json'
    p.write_text(json.dumps(dict(since='2000-01-01', span=8, markets={'Nasdaq-100 futures': m})))
    out = rs.crowding_history_html(dict(rows=[dict(name='Nasdaq-100 futures', flag='long')]), path=str(p))
    assert 'What followed, since 2000' in out and '<span class="sig pos">10/11✓</span>' in out
    assert '<td class="now"><span class="trip">6/16' in out and 'Passing: Nasdaq-100 futures while crowded short (3 mo).' in out
    assert 'momentum' not in out.lower() and rs.crowding_history_html(path=str(tmp_path / 'none.json')) == ''

"""Analyst-revisions forward test (mtl/revisions_forward.py): each logged Friday scored once, 20 sessions on, and its
section on docs/forward.html."""
import importlib.util
import json
import os
from datetime import date, timedelta

from mtl import revisions_forward as RF


def sessions(n, start='2026-10-09'):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_halves_by_estimate_rise_and_the_cut_group_against_the_sp500():
    cal = sessions(30)
    log = {cal[0]: {f'S{i}': dict(eps90=0.1 - i * 0.01, up30=5, down30=1 if i < 9 else 9, rank=i + 1) for i in range(10)}}
    closes = {f'S{i}': {d: 100 * (1 + (0.002 if i < 5 else -0.001) * k) for k, d in enumerate(cal)} for i in range(10)}
    closes['SPY'] = {d: 100.0 for d in cal}
    D = RF.build(log, closes)
    c = D['weeks'][0]['calls']
    assert c['top25']['hit'] and c['top10']['hit'] and c['top10']['n_a'] == 5 and c['top10']['n_b'] == 5
    assert c['cut']['names'] == ['S9'] and c['cut']['hit']                  # S9: more cuts than raises, fell
    rows = {r['id']: r for r in D['summary']['rows']}
    assert rows['top25']['n'] == 1 and rows['top25']['verdict'] == 'too few' and round(D['summary']['bar'], 4) == 0.0167


def test_not_scored_before_the_horizon_and_no_cut_call_without_cuts():
    cal = sessions(10)
    log = {cal[0]: {f'S{i}': dict(eps90=0.05, up30=3, down30=1, rank=i + 1) for i in range(4)}}
    closes = {t: {d: 100.0 for d in cal} for t in list(log[cal[0]]) + ['SPY']}
    c = RF.build(log, closes)['weeks'][0]['calls']
    assert c['top25'] == dict(waiting=True, n_a=2, n_b=2) and c['cut'] is None
    assert RF.build({}, {})['weeks'] == []


def test_section_on_the_forward_page(tmp_path):
    spec = importlib.util.spec_from_file_location('render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    cal = sessions(30)
    log = {cal[0]: {f'S{i}': dict(eps90=0.1 - i * 0.01, up30=5, down30=1, rank=i + 1) for i in range(10)},
           cal[5]: {f'S{i}': dict(eps90=0.1 - i * 0.01, up30=5, down30=1, rank=i + 1) for i in range(10)}}
    closes = {f'S{i}': {d: 100 * (1 + (0.002 if i < 5 else -0.001) * k) for k, d in enumerate(cal)} for i in range(10)}
    closes['SPY'] = {d: 100.0 for d in cal}
    p = tmp_path / 'rf.json'
    p.write_text(json.dumps(RF.build(log, closes)))
    out = rs.revisions_forward_html(path=str(p))
    assert 'Analyst estimate revisions' in out and '<span class="pos">✓</span>' in out and 'waiting' in out
    page = rs.forward_page(path=str(tmp_path / 'none.json'), rev_path=str(p))
    assert '<h1>Forward tests</h1>' in page and 'id="revisions"' in page
    for word in ('momentum', 'SPY'):
        assert word not in out
    assert rs.revisions_forward_html(path=str(tmp_path / 'none.json')) == ''

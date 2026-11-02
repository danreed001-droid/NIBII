import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import paper, volweight, volweight_check  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402


def _cal(n):
    d, out = date(2020, 1, 1), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _stock(cal, up_vol, dn_vol, drift=0.001):
    """Alternating up / down closes: up days trade up_vol shares, down days dn_vol."""
    px, vol, p = {}, {}, 100.0
    for i, d in enumerate(cal):
        up = i % 2 == 0
        p *= (1 + drift + 0.01) if up else (1 + drift - 0.01)
        px[d], vol[d] = p, up_vol if up else dn_vol
    return px, vol


def test_ratio_counts_up_and_other_days():
    cal = _cal(300)
    px, vol = _stock(cal, 300, 100)
    r = volweight.ratio(px, vol, cal, 299)
    ups = sum(1 for j in range(299 - 62, 300) if j % 2 == 0)     # 63 sessions: up days trade 300, the others 100
    assert abs(r - ups * 300 / ((63 - ups) * 100)) < 1e-9
    assert volweight.ratio(px, vol, cal, 100) is None          # less than a year of prices
    px2 = dict(px)
    px2.pop(cal[290])
    assert volweight.ratio(px2, vol, cal, 299) is None          # a gap in the window


def test_quantile_matches_numpy_linear():
    xs = [5, 1, 4, 2, 3, 9, 7]
    assert abs(volweight._quantile(xs, 2 / 3) - 5.0) < 1e-9
    assert abs(volweight._quantile(xs, 0.5) - 4.0) < 1e-9


def _universe(n=45):
    cal = _cal(300)
    prices, volumes = {}, {}
    for i in range(n):
        prices[f'S{i}'], volumes[f'S{i}'] = _stock(cal, 100 + 10 * i, 100)    # ratio 1.0 .. 5.4
    prices['SPY'], volumes['SPY'] = _stock(cal, 100, 100)
    return cal, prices, volumes


def test_weights_double_the_buying_stocks():
    cal, prices, volumes = _universe()
    vw = volweight.VolWeight(prices, volumes, lambda t, d: True, top_n=5)
    rows, th = vw.cut(cal, 299)
    assert len(rows) == 45 and 'SPY' not in rows
    top = sorted(rows.values())[-15]                          # the top third starts near the 30th value
    assert th <= top + 1e-9
    w = vw.weights(['S0', 'S1', 'S44', 'S43', 'S2'], cal, 299)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert abs(w['S44'] - 2 / 7) < 1e-9 and abs(w['S0'] - 1 / 7) < 1e-9
    w4 = vw.weights(['S0', 'S44', 'S43', 'S2'], cal, 299)    # an empty slot stays a fifth
    assert abs(sum(w4.values()) - 0.8) < 1e-9
    weq = vw.weights(['S0', 'S1', 'S2'], cal, 299)           # nobody buying: equal fifths
    assert all(abs(x - 0.2) < 1e-9 for x in weq.values())
    card = vw.card(['S44', 'S0'], cal, 299)
    assert card['stocks'][0]['buying'] and not card['stocks'][1]['buying'] and card['n'] == 45


def test_run_momentum_takes_a_weighting():
    cal, prices, volumes = _universe()
    vw = volweight.VolWeight(prices, volumes, lambda t, d: True, top_n=5)
    r = run_momentum(prices, cal, cal[260], top_n=5, weighting=vw.fn(cal), exec_next='close')
    assert r['weights']
    w = r['weights'][-1][1]
    assert abs(sum(w.values()) - len(w) / 5) < 1e-9


def test_paper_weights_follow_the_shares():
    w = paper.weights('boost', None, ['A', 'B', 'C', 'D'], sw={'A': 0.4, 'B': 0.2, 'C': 0.1, 'D': 0.1})
    assert abs(w['A'] - 0.4) < 1e-9 and abs(w[paper.CASH] - 0.2) < 1e-9
    w2 = paper.weights('boost', None, ['A', 'B'], sw={'A': 0.4})      # incomplete: equal fifths
    assert abs(w2['A'] - 0.2) < 1e-9 and abs(w2[paper.CASH] - 0.6) < 1e-9
    d = paper.decision('2026-11-06', 'boost', None, ['A', 'B', 'C', 'D', 'E'], sw={'A': 2 / 7, 'B': 2 / 7, 'C': 1 / 7, 'D': 1 / 7, 'E': 1 / 7})
    assert abs(sum(d['w'].values()) - 1) < 1e-5 and abs(d['w']['A'] - 0.285714) < 1e-6


def test_scorecard_scores_each_trade():
    cal = _cal(600)
    prices = {'A': {d: 100 * (1.001 ** i) for i, d in enumerate(cal)}, 'B': {d: 100.0 for d in cal}}
    log = [[cal[i], {'A': 2 / 3 * 2 / 5 * 2.5, 'B': 1 / 3 * 2 / 5 * 2.5}] for i in range(0, 600, 5)]
    c = volweight_check.scorecard(log, prices, cal, since=cal[500])
    assert c['trades'] == 20 and c['won'] >= 19 and c['edge'] > 0
    assert c['verdict'] == 'too early'
    assert c['past']['years'] > 0 and c['past']['aheadYears'] == c['past']['years']
    c2 = volweight_check.scorecard(log, prices, cal, since=cal[200])
    assert c2['verdict'] == 'keep'


def test_page_and_alert_show_the_weights():
    import importlib.util
    spec = importlib.util.spec_from_file_location('weekly_alert', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'weekly_alert.py'))
    wa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wa)
    bx = dict(vw=dict(stocks=[dict(t='A', w=2 / 7, buying=True), dict(t='B', w=1 / 7, buying=False)]))
    s = wa.vw_split(bx)
    assert 'A 28.6% (2x buying volume)' in s and 'B 14.3%' in s
    assert wa.vw_split(dict(vw=dict(stocks=[dict(t='A', w=0.2), dict(t='B', w=0.2)]))) == ''
    src = open(os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py')).read()
    assert 'function vwNote(RT)' in src and '12. Buying-volume weighting' in src and 'function amt(t)' in src

"""Rates model forward test (mtl/rates_forward.py): a month-end pick from earlier months only, logged once and scored
at the next month-end, against the plan-style rule; and its section on docs/forward.html."""
import importlib.util
import json
import math
import os
from datetime import date, timedelta

from mtl import rates_forward as RF


def sessions(start='2010-01-04', n=1900):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def market(cal):
    """Yields swing; gold rises in months that start with a high yield, the S&P falls then."""
    tnx = {d: 3 + 2 * math.sin(i / 120) for i, d in enumerate(cal)}
    irx = {d: 1.0 for d in cal}
    spy, gld, tlt, s, g = {}, {}, {}, 100.0, 100.0
    for i, d in enumerate(cal):
        hi = tnx[cal[max(0, i - 25)]] > 3
        s *= 1 + (-0.001 if hi else 0.001)
        g *= 1 + (0.002 if hi else -0.0005)
        spy[d], gld[d], tlt[d] = s, g, 100.0
    return dict(SPY=spy, GLD=gld, TLT=tlt, TNX=tnx, IRX=irx)


def test_month_ends_never_count_the_calendar_s_last_day():
    cal = ['2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03']
    assert RF.month_ends(cal) == ['2026-10-30'] and RF.month_ends(cal[:2]) == []


def test_picks_from_earlier_months_only_logs_once_and_scores_next_month():
    cal = sessions()
    px = RF.Px(market(cal))
    me = RF.month_ends(cal)
    assert RF.pick(px, cal, me[10])[0] is None                      # too few months to fit
    hi = next(m for m in me[60:] if px.at('TNX', m) > 4.5)
    p, pred, cash = RF.pick(px, cal, hi)
    assert p == 'GLD' and pred['GLD'] > pred['SPY'] and round(cash, 5) == round(1 / 100 / 12, 5)
    doc = RF.new_doc()
    row = RF.write(doc, hi, px, cal[:cal.index(hi) + 1], 'x')
    assert row['pick'] == 'GLD' and RF.write(doc, hi, px, cal, 'y') is None
    assert RF.score(doc, px, cal[:cal.index(hi) + 3]) == 0          # next month not over yet
    assert RF.score(doc, px, cal) == 1
    m = doc['months'][0]
    assert m['to'] == me[me.index(hi) + 1] and m['model'] > 0 and m['rule'] in ('SPY', 'GLD', 'TLT')
    s = RF.summary(doc)
    assert s['n'] == 1 and s['verdict'] == 'too few'


def test_section_on_the_forward_page(tmp_path):
    spec = importlib.util.spec_from_file_location('render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    doc = RF.new_doc()
    doc['months'] = [dict(d='2026-09-30', pick='GLD', rule='SPY', cash=0.003, model=0.02, ruleRet=-0.01, spy=-0.01, to='2026-10-30'),
                     dict(d='2026-10-30', pick='GLD', rule='SPY', cash=0.003)]
    doc['summary'] = RF.summary(doc)
    p = tmp_path / 'r.json'
    p.write_text(json.dumps(doc))
    out = rs.rates_forward_html(path=str(p))
    assert 'Rates model' in out and 'November 2026' in out and 'October 2026' in out and '<span class="pos">✓</span>' in out
    assert 'came out ahead 1 times' in out and 'waiting' in out and 'momentum' not in out.lower()
    page = rs.forward_page(path=str(tmp_path / 'n.json'), rev_path=str(tmp_path / 'n.json'), rates_path=str(p))
    assert 'id="rates"' in page and rs.rates_forward_html(path=str(tmp_path / 'none.json')) == ''

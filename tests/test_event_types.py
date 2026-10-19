"""Event types and what usually followed each (mtl/event_types.py, scripts/event_patterns.py, the events page)."""
from datetime import date, timedelta

import numpy as np

from mtl import event_types as et
from mtl import events as ev


def test_new_events_are_typed_by_rule_and_headline():
    c = lambda src, what: et.classify(dict(src=src, what=what))
    assert c('auto: Fed', 'Fed raises rates to 4–4.25% (FOMC statement)') == 'Fed hike / hawkish'
    assert c('auto: Fed', 'Fed cuts rates to 3.5–3.75% (FOMC statement)') == 'Fed cut'
    assert c('auto: VIX', 'Fear spike: the VIX closes at 33') == 'Fear spike'
    assert c('auto: market phase', 'S&P 500 enters a bear market (20%+ below its high)') == 'Bear market starts'
    assert c('auto: big move', 'S&P 500 −3.1% in a day: Iran strikes Gulf oil tankers (news log)') == 'War / terror'
    assert c('auto: big move', 'S&P 500 −3.1% in a day: Regional bank fails (news log)') == 'Bank / credit failure'
    assert c('auto: big move', 'S&P 500 −2.6% in a day') == 'Big down day'
    assert c('auto: big move', 'S&P 500 +2.9% in a day') == 'Big up day'
    assert c('added by you', 'Powell signals cuts are coming') == 'Fed cut'
    assert c('added by you', 'Something odd happened') == 'Other'
    assert all(et.CURATED[d] in et.TYPES for d in et.CURATED)


def test_your_items_keep_the_type_you_picked():
    evs = []
    ev.sync_mine(evs, [dict(d='2026-10-16', what='Tariffs on chips', type='War / terror'), dict(d='2026-10-17', what='Tariffs on chips')])
    assert [e['type'] for e in evs] == ['War / terror', 'Trade war / China']


def test_patterns_count_rule_days_from_history_and_mark_what_held():
    from scripts import event_patterns as ep
    days = [date(2011, 1, 3) + timedelta(days=i) for i in range(1100)]
    days = [d.isoformat() for d in days if d.weekday() < 5]
    rng = np.random.default_rng(1)
    spy = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))
    shocks = [days[i] for i in (200, 280, 360, 560, 640, 720)]   # three in each half (2011-12, 2013)
    for d in shocks:
        i = days.index(d); spy[i:] *= 0.96                       # a 4% drop on each event day
    px = {t: {d: float(x) for d, x in zip(days, spy * (1 + 0.1 * j))} for j, t in enumerate(['SPY', 'VUSTX', 'GLD', 'CL=F', 'DX-Y.NYB'])}
    px['VUSTX'] = {d: 100.0 + i * 0.01 for i, d in enumerate(days)}
    px['^VIX'] = {d: 20.0 for d in days}
    doc = dict(events=[dict(d=d, what='War breaks out', src='curated', type='War / terror') for d in shocks])
    out = ep.compute(doc, px)
    w = out['types']['War / terror']
    assert w['n'] == 6 and w['group'] == 'Outside shock'
    assert w['assets']['S&P 500']['day']['up'] == 0 and w['assets']['S&P 500']['day']['held']
    assert w['assets']['Bonds']['day']['up'] == 1
    assert out['types']['Big down day']['n'] >= 6          # the same drops (and any random ones), found by the nightly rule
    assert 'Outside shock' in out['groups'] and 'below200' in out['groups']['Outside shock']


def test_page_shows_what_usually_followed_recent_events():
    from scripts.major_events import render
    s = lambda up, avg, held=False: dict(n=10, up=up, avg=avg, held=held)
    asset = lambda: dict(day=s(0.7, 0.01, True), month=s(0.6, 0.0), quarter=s(0.8, 0.05, True))
    pats = dict(updated='2026-10-18T00:00:00+00:00', baseline={a: {str(h): dict(up=0.6, avg=0.01, n=100) for h in (0, 21, 63)}
                for a in ('S&P 500', 'Bonds', 'Gold', 'Oil', 'Dollar')},
                types={'War / terror': dict(n=9, clusters=8, first='2001-09-17', last='2025-06-23', group='Outside shock',
                                            assets={a: asset() for a in ('S&P 500', 'Bonds', 'Gold', 'Oil', 'Dollar')},
                                            sectors=[dict(name='Tech', avg=0.02, beat=0.7, n=9, held=True)])},
                groups={'Outside shock': dict(n=40, assets={'S&P 500': asset()}, above200=dict(quarter=s(0.75, 0.03)),
                                              below200=dict(quarter=s(0.91, 0.11)))})
    doc = dict(updated='2026-10-18', events=[
        dict(d='2026-10-10', what='Strikes on Iran', src='curated', type='War / terror', trend='below', day=-0.02, month=None),
        dict(d='2003-03-20', what='Iraq war begins', src='curated', type='War / terror', day=0.02, month=0.03)])
    page = render(doc, pats)
    assert page.count('class="pat"') == 1                                  # only the recent one
    assert 'S&amp;P higher 3 months later in 80%' in page and 'with the S&amp;P below its 200-day average, all outside shocks: 91% higher' in page
    assert page.count('href="#t-war-terror"') >= 3 and 'id="t-war-terror"' in page and 'Tech (70%' in page


def test_scorecard_saves_odds_once_and_scores_after_three_months(tmp_path):
    from scripts import event_patterns as ep
    q = lambda up: dict(n=12, up=up, avg=0.01, held=False)
    pats = dict(baseline={'S&P 500': {'63': dict(up=0.69, avg=0.02, n=100)}},
                types={'War / terror': dict(group='Outside shock', assets={'S&P 500': dict(quarter=q(0.8))})},
                groups={'Tightening': dict(assets={'S&P 500': dict(quarter=q(0.4))})})
    cal = [f'2026-{m:02d}-{d:02d}' for m in range(10, 13) for d in range(1, 29)] + [f'2027-{m:02d}-{d:02d}' for m in range(1, 6) for d in range(1, 29)]
    spy = [100 + i * 0.1 for i in range(len(cal))]
    doc = dict(events=[dict(d='2026-10-20', what='Strike on a port', src='auto: big move', type='War / terror'),
                       dict(d='2026-10-21', what='Hot CPI', src='curated', type='Inflation / yields'),    # falls back to its group
                       dict(d='2026-10-22', what='Top', src='curated', type='Turning point'),             # no odds
                       dict(d='2026-09-01', what='Before the scorecard', src='curated', type='War / terror')])
    path = str(tmp_path / 'f.json')
    log = ep.update_forecasts(doc, pats, cal[:40], spy[:40], '2026-10-22', path)
    assert [(x['d'], x['basis'], x['up'], x['spy_q']) for x in log['entries']] == \
        [('2026-10-20', 'War / terror', 0.8, None), ('2026-10-21', 'Tightening', 0.4, None)]
    pats['types']['War / terror']['assets']['S&P 500']['quarter'] = q(0.1)      # later weeks don't rewrite saved odds
    log = ep.update_forecasts(doc, pats, cal, spy, '2027-02-01', path)
    assert [x['up'] for x in log['entries']] == [0.8, 0.4] and all(x['spy_q'] > 0 for x in log['entries'])
    r = ep.record(log)
    assert (r['n'], r['calls'], r['right'], r['normal_right']) == (2, 2, 1, 2)
    from scripts.major_events import record_card
    card = record_card(log, pats)
    assert 'came true in <b>1 of 2</b>' in card and 'Strike on a port' in card

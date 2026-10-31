"""News forward test (mtl/news_forward.py, scripts/news_forward.py): calls written once before the next open, from
the entries the market could react to that day, and scored only afterwards; and its card on the scanner page."""
import importlib.util
import json
import os
from datetime import datetime, timezone

from mtl import news_forward as NF

CAL = ['2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03']


def item(d, direction='Bearish', impact='High', tm='Market hours', category='Market'):
    return dict(date=d, direction=direction, impact=impact, time=tm, category=category)


def test_entries_land_on_the_first_session_that_can_react():
    news = [item('2026-10-29', tm='After-hours'), item('2026-10-30'), item('2026-10-30', tm='After close'),
            item('2026-10-31', tm='Weekend'), item('2026-10-30', tm='Pre-market')]
    got = NF.entries_for(news, CAL, '2026-10-30')
    assert got == [news[0], news[1], news[4]]
    assert NF.entries_for(news, CAL, '2026-11-02') == [news[2], news[3]]


def test_calls_are_written_once_and_scored_only_when_the_horizon_has_passed():
    doc = NF.new_doc()
    news = [item('2026-10-30'), item('2026-10-30'), item('2026-10-30', direction='Bearish', category='Fed / rates', impact='Medium')]
    moves = dict(SPY=-0.02, QQQ=-0.03, GLD=-0.01, TLT=0.004)
    calls = NF.write(doc, '2026-10-30', news, moves, typical=0.005, at='x')
    ids = {c['id']: c['call'] for c in calls}
    assert ids['tone_tlt'] == 1 and ids['tone_spy'] == -1 and ids['pile_qqq'] == -1 and ids['fed_bear'] == -1
    assert ids['bounce'] == 1 and 'shrug' not in ids and 'busy' not in ids
    assert NF.write(doc, '2026-10-30', news * 5, moves, typical=0.005) == []          # never rewritten
    closes = {t: {'2026-10-30': 100.0, '2026-11-02': 101.0} for t in NF.ASSETS}
    assert NF.score(doc, closes) == 6                                                  # the 1-day calls
    by = {c['id']: c for c in doc['calls']}
    assert by['tone_tlt']['hit'] and not by['tone_spy']['hit'] and by['bounce']['hit'] and 'hit' not in by['pile_tlt']
    S = NF.summary(doc)
    row = next(r for r in S['rows'] if r['id'] == 'tone_tlt')
    assert row['n'] == 1 and row['hits'] == 1 and row['verdict'] == 'too few' and round(S['bar'], 3) == 0.005


def test_busy_days_are_scored_against_the_typical_move_and_a_long_record_gets_a_verdict():
    doc = NF.new_doc()
    days = [f'2026-{m:02d}-{d:02d}' for m in (1, 2, 3) for d in range(1, 29) if True][:41]
    closes = {t: {} for t in NF.ASSETS}
    for i, d in enumerate(days):
        for t in NF.ASSETS:
            closes[t][d] = 100.0 * (1.01 if i % 2 else 1.0)                            # 1% swing every day
    for d in days[:-1]:
        NF.write(doc, d, [item(d, direction='Mixed', impact='Low')] * 6, dict(SPY=0, QQQ=0, GLD=0, TLT=0), typical=0.005)
    NF.score(doc, closes)
    busy = next(r for r in NF.summary(doc)['rows'] if r['id'] == 'busy')
    assert busy['n'] == 40 and busy['hits'] == 40 and busy['verdict'] == 'holding up'
    assert NF.sign_p(5, 10) == 1.0 and NF.sign_p(0, 0) == 1.0


def test_the_script_writes_only_before_the_next_open():
    from scripts.news_forward import before_next_open, NY
    fri_evening = datetime(2026, 10, 30, 21, 0, tzinfo=NY)
    assert before_next_open('2026-10-30', fri_evening)
    assert before_next_open('2026-10-30', datetime(2026, 11, 2, 9, 29, tzinfo=NY))
    assert not before_next_open('2026-10-30', datetime(2026, 11, 2, 9, 31, tzinfo=NY))
    assert not before_next_open('2026-10-30', datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc).astimezone(NY))


def test_card_on_the_scanner_page(tmp_path):
    spec = importlib.util.spec_from_file_location('render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    doc = NF.new_doc()
    NF.write(doc, '2026-10-30', [item('2026-10-30')] * 2, dict(SPY=-0.02, QQQ=-0.03, GLD=-0.01, TLT=0.004), typical=0.005)
    doc['summary'] = NF.summary(doc)
    p = tmp_path / 'nf.json'
    p.write_text(json.dumps(doc))
    out = rs.news_forward_html(path=str(p))
    assert 'News forward test' in out and 'Latest calls</b> (Fri Oct 30, from 2 news items)' in out
    assert 'long Treasuries up over the next week; Nasdaq-100 down next day' in out and 'S&amp;P 500 down next day;' in out and 'S&amp;P 500 up next day.' in out and out.count('<tr>') == 1 + len(NF.GUESSES)
    assert 'momentum' not in out.lower() and rs.news_forward_html(path=str(tmp_path / 'none.json')) == ''

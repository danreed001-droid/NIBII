"""Tests for the script-built "Today's market" card (mtl/story.py, scripts/story_build.py, render_scanner.story_html)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from mtl import story  # noqa: E402
import render_scanner as rs  # noqa: E402

DATES = ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20', '2026-11-23', '2026-11-24']


def _bar(c):
    return [c, c, c, c, 1000]


def _ohlc():
    spy = [740, 735, 730, 728, 715, 690, 722]          # four losses, then a gain... see the asserts
    return dict(dates=DATES, n=dict(AAA='Alpha Co', BBB='Beta Co', CCC='Gamma Co'),
                t=dict(SPY=[_bar(x) for x in spy], QQQ=[_bar(x) for x in (500, 495, 490, 489, 480, 455, 480)],
                       RSP=[_bar(x) for x in (180, 179, 179, 178, 176, 172, 176)],
                       AAA=[_bar(x) for x in (10, 10, 10, 10, 10, 10, 11)], BBB=[_bar(x) for x in (20, 20, 20, 20, 20, 20, 19)],
                       CCC=[_bar(x) for x in (5, 5, 5, 5, 5, 5, None)][:6] + [None]))


def _heads(day):
    return [dict(d=day, src='AP News', t='Wall Street rallies as tech rebounds', link='https://ex.com/1'),
            dict(d=day, src='AP News', t='Another AP stock market story', link='https://ex.com/2'),
            dict(d=day, src='Bloomberg.com', t='Asian Stocks to Slide: Markets Wrap', link='https://ex.com/3'),
            dict(d=day, src='The Motley Fool', t='3 stocks to buy now', link='https://ex.com/4'),
            dict(d=day, src='Kiplinger', t='Dow Adds 500 Points: Stock Market Today', link='https://ex.com/5'),
            dict(d=day, src='Reuters', t='Canadian dollar falls as stock market selloff deepens', link='https://ex.com/6'),
            dict(d=day, src='Some Blog', t='Stocks rise on Monday', link='https://ex.com/7'),
            dict(d='2026-11-20', src='Reuters', t='Wall Street sinks', link='https://ex.com/8')]


def test_pick_headlines_by_rule():
    got = story.pick_headlines(_heads('2026-11-24'), '2026-11-24')
    assert [x['src'] for x in got] == ['AP News', 'Kiplinger']        # one per source; Asia, buy lists, currencies and weak sources out
    assert got[0]['t'] == 'Wall Street rallies as tech rebounds' and got[0]['link'] == 'https://ex.com/1'
    assert story.pick_headlines(_heads('2026-11-24'), '2026-11-25') == []


def test_build_item_numbers_from_prices():
    it = story.build_item('2026-11-24', _ohlc(), _heads('2026-11-24'), members=['AAA', 'BBB', 'CCC'], fomc=['2026-12-09'])
    assert it['headline'] == 'Stocks surge 4.6%; first gain after 5 losses'
    assert it['tape'][0] == dict(t='SPY', n='S&P 500', pct=0.0464, close=722)
    assert [x['t'] for x in it['tape']] == ['SPY', 'QQQ', 'RSP']
    assert it['facts'][0].startswith('SPY is 2.4% under its 1-year high (Mon Nov 16')
    assert it['facts'][1] == '1 of 2 S&P 500 stocks rose.'             # CCC has no price that day
    assert it['up'] == [dict(t='AAA', n='Alpha Co', pct=0.1)] and it['down'] == [dict(t='BBB', n='Beta Co', pct=-0.05)]
    assert it['coming'] == ['Thu Nov 26: market closed (Thanksgiving)', 'Fri Nov 27: half day (closes 1pm ET)']
    assert it['by'] == 'script' and len(it['headlines']) == 2


def test_build_item_losing_streak_and_missing_day():
    it = story.build_item('2026-11-23', _ohlc(), [], members=['AAA'])
    assert it['headline'] == 'Stocks sink 3.5%; 5th loss in a row'
    assert story.build_item('2026-11-25', _ohlc(), []) is None
    assert story.build_item('2026-11-16', _ohlc(), []) is None           # no day before it


def test_calendar_helpers():
    assert story.coming_up('2026-12-03', ['2026-12-09']) == ['Wed Dec 9: Fed rate decision (2pm ET)']
    assert story.early_close('2026-11-27') and story.early_close('2026-12-24') and not story.early_close('2026-11-25')
    assert story.coming_up('2026-12-29') == ['Fri Jan 1: market closed (New Year\'s Day)']


def test_upsert_replaces_the_day_and_keeps_order():
    log = dict(about='x', items=[dict(date='2026-11-23', headline='a'), dict(date='2026-11-24', headline='b')])
    out = story.upsert(log, dict(date='2026-11-24', headline='c'))
    assert [x['headline'] for x in out['items']] == ['a', 'c'] and out['about'] == 'x'
    assert len(story.upsert(dict(items=[dict(date='2026-01-%02d' % d, headline='h') for d in range(1, 31)]), dict(date='2026-02-01', headline='z'), keep=10)['items']) == 10


def test_limit_and_back_in_guards():
    assert story._limit([], '2026-11-13') == ('2026-11-27', '2026-11-30')
    assert story.back_in([], [], 0, dict(active=False)) is None
    assert story.back_in([], ['2026-11-24'], 0, dict(active=True, log=[dict(date='2026-11-13', test='2026-11-13', back='2026-11-20')])) is None


def _scan():
    bi = dict(fromDate='2026-10-06', top=781.62, slope=-0.653, test='2026-11-13', fired='2026-11-13', to='CASH',
              line=[['2026-11-23', 761.71], ['2026-11-24', 761.05]], ahead=[['2026-11-25', 760.4], ['2026-11-27', 759.74]],
              next=['2026-11-25', 760.4], lastDecision='2026-11-27', lastTrade='2026-11-30', brk=0.003)
    spy = [['2026-11-%02d' % d, 700.0 + d] for d in range(2, 25) if d not in (7, 8, 14, 15, 21, 22)]
    return dict(asOf='2026-11-24', story=dict(spy=spy, backIn=bi),
                plan=dict(auto=dict(rotation=dict(mode='CASH', trade=None, log=[['2026-11-13', 'boost', 'CASH', 'resist']]))))


def test_plan_lines_from_the_scan():
    lines = story.plan_lines(_scan())
    assert lines[0] == ('Holds cash since Fri Nov 13.', 'state') and lines[-1] == ('Tonight: no change.', 'note')
    assert 'above 760.40 on Wed Nov 25' in lines[1][0] and 'Mon Nov 30 close' in lines[1][0]
    assert story.plan_short(_scan())[0] == 'In cash.'


def test_card_and_whatsapp(tmp_path):
    a = story.build_item('2026-11-23', _ohlc(), [], members=['AAA', 'BBB'])
    b = story.build_item('2026-11-24', _ohlc(), _heads('2026-11-24') + [dict(d='2026-11-24', src='AP News', t='<script>x', link='javascript:1')],
                         members=['AAA', 'BBB'])
    p = tmp_path / 's.json'
    p.write_text(json.dumps(dict(items=[a, b])))
    h = rs.story_html(_scan(), str(p))
    assert h.startswith('<!--story-->') and h.endswith('<!--/story-->') and '<script>x' not in h
    assert 'Stocks surge 4.6%' in h and 'href="https://ex.com/1"' in h and 'Earlier days (1)' in h
    assert '<b>760.40</b>' in h and '<svg' in h and 'Thanksgiving' in h and 'Alpha Co' in h
    wa = rs.story_whatsapp(b, story.plan_short(_scan()))
    assert wa.startswith('*Market – Tue Nov 24*\nStocks surge 4.6%; first gain after 5 losses\nSPY 722.00 +4.6%')
    assert '*Headlines*\n• AP News: Wall Street rallies as tech rebounds' in wa and '*Plan*\n• In cash.' in wa and 'http' not in wa
    assert 'Nothing yet' in rs.story_html(_scan(), str(tmp_path / 'none.json'))


def test_the_log_in_the_repo_is_script_built():
    items = story.load(os.path.join(ROOT, 'data', 'story_log.json'))
    assert items and all(x.get('by') == 'script' and x.get('tape') for x in items)

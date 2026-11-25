"""Tests for the "Today's story" card (mtl/story.py, render_scanner.story_html, scripts/story_refresh.py)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from mtl import story  # noqa: E402
import render_scanner as rs  # noqa: E402
import story_refresh  # noqa: E402


def _item(d, head='A day', **kw):
    return dict(dict(date=d, headline=head, happened='Stocks moved.', points=['one', 'two'], matters='It matters.',
                     watch=['Jobs report'], short=head + '.', sources=[dict(name='Src', url='https://example.com/a')]), **kw)


def _scan(mode='CASH', back=True, trade=None):
    bi = dict(fromDate='2026-10-06', top=781.62, slope=-0.653, test='2026-11-13', fired='2026-11-13', to='CASH',
              line=[['2026-11-23', 761.71], ['2026-11-24', 761.05]], ahead=[['2026-11-25', 760.4], ['2026-11-27', 759.74]],
              next=['2026-11-25', 760.4], lastDecision='2026-11-27', lastTrade='2026-11-30', brk=0.003) if back else None
    spy = [['2026-11-%02d' % d, 700.0 + d] for d in range(2, 25) if d not in (7, 8, 14, 15, 21, 22)]
    return dict(asOf='2026-11-24', story=dict(spy=spy, backIn=bi),
                plan=dict(auto=dict(rotation=dict(mode=mode, trade=trade, log=[['2026-11-13', 'boost', mode, 'resist']]))))


def test_load_sorts_newest_first_and_skips_broken(tmp_path):
    p = tmp_path / 's.json'
    p.write_text(json.dumps(dict(items=[_item('2026-11-20'), {'date': '2026-11-21'}, _item('2026-11-24'), 'x'])))
    assert [x['date'] for x in story.load(str(p))] == ['2026-11-24', '2026-11-20']
    assert story.load(str(tmp_path / 'missing.json')) == []


def test_limit_is_the_second_week_end_after_the_exit():
    # out on Fri Nov 13, 2026: two week-ends later is Fri Nov 27 (Thanksgiving week), back in at the Mon Nov 30 close
    assert story._limit([], '2026-11-13') == ('2026-11-27', '2026-11-30')


def test_back_in_needs_the_rule_to_be_holding():
    assert story.back_in([], [], 0, dict(active=False)) is None
    assert story.back_in([], [], 0, None) is None
    assert story.back_in([], ['2026-11-24'], 0, dict(active=True, log=[dict(date='2026-11-13', test='2026-11-13', back='2026-11-20')])) is None


def test_scan_part_keeps_the_last_closes():
    bars = [['2026-10-%02d' % d, 1, 2, 0.5, 100.0 + d] for d in range(1, 29)]
    cal = [b[0] for b in bars]
    out = story.scan_part(bars, cal, len(cal) - 1, {})
    assert out['backIn'] is None and out['spy'][-1] == ['2026-10-28', 128.0] and len(out['spy']) == 28


def test_plan_lines_and_short_from_the_scan():
    lines = story.plan_lines(_scan())
    assert lines[0] == ('Holds cash since Fri Nov 13.', 'state')
    assert 'above 760.40 on Wed Nov 25' in lines[1][0] and 'Mon Nov 30 close' in lines[1][0] and lines[1][1] == 'back'
    assert lines[-1] == ('Tonight: no change.', 'note')
    assert story.plan_short(_scan()) == ['In cash.', 'Back into stocks on a close above 760.4 (Wed Nov 25), or at the latest at the Mon Nov 30 close.']
    stocks = story.plan_lines(_scan(mode='boost', back=False, trade='2026-11-25'))
    assert stocks[0][0].startswith('Holds stocks') and stocks[-1] == ('Trade at the Wed Nov 25 close.', 'note')
    assert story.plan_lines({}) == []


def test_card_renders_newest_story_with_markers_and_escaping(tmp_path):
    p = tmp_path / 's.json'
    p.write_text(json.dumps(dict(items=[_item('2026-11-23', 'Earlier day'), _item('2026-11-24', 'Big <b>day</b>', movers=[dict(t='NVDA', pct=-0.059)])])))
    h = rs.story_html(_scan(), str(p))
    assert h.startswith('<!--story-->') and h.endswith('<!--/story-->')
    assert 'Big &lt;b&gt;day&lt;/b&gt;' in h and '<b>day</b>' not in h
    assert 'SPY 724.00' in h and 'NVDA' in h and '−5.9%' in h          # SPY from the scan's closes (724 vs 723 the day before)
    assert '<b>760.40</b>' in h and 'Earlier days (1)' in h and 'Earlier day.' in h
    assert '<svg' in h and 'back-in line' in h and 'id="st-wa"' in h


def test_card_without_stories(tmp_path):
    h = rs.story_html(_scan(), str(tmp_path / 'none.json'))
    assert 'No story yet' in h and '<!--/story-->' in h


def test_whatsapp_version():
    wa = rs.story_whatsapp(_item('2026-11-24', 'Head'), _scan()['story'], story.plan_short(_scan()))
    assert wa.startswith('*Market story – Tue Nov 24*\nSPY 724.00 (+0.1%)')
    assert '*What happened*\n• one\n• two' in wa and '*Watch*\n• Jobs report' in wa and '*Plan*\n• In cash.' in wa
    assert '|' not in wa


def test_refresh_swaps_or_inserts_the_card(monkeypatch):
    monkeypatch.setattr(rs, 'story_html', lambda scan, path=None: '<!--story-->NEW ' + scan['asOf'] + '<!--/story-->')
    data = '<script type="application/json" id="scan-data">' + json.dumps(dict(asOf='2026-11-24')) + '</script>'
    old = '<div class="banner" id="banner"></div>\n<!--story-->OLD<!--/story-->' + data
    assert story_refresh.refresh(old) == '<div class="banner" id="banner"></div>\n<!--story-->NEW 2026-11-24<!--/story-->' + data
    bare = '<div class="banner" id="banner"></div>' + data
    assert '<div class="banner" id="banner"></div>\n<!--story-->NEW' in story_refresh.refresh(bare)
    assert story_refresh.refresh('<html>no data</html>') is None


def test_the_log_in_the_repo_is_valid():
    items = story.load(os.path.join(ROOT, 'data', 'story_log.json'))
    assert items, 'data/story_log.json has no stories'
    for x in items:
        assert x['date'][:4] == '2026' and x.get('short') and all(s['url'].startswith('https://') for s in x.get('sources') or [])

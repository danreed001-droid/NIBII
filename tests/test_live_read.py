"""The latest read: recomputed trend numbers shown next to a frozen board."""
import json
import os

from mtl.live_read import latest_note, latest_read
from scripts.render_html import latest_read_html, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = json.load(open(os.path.join(ROOT, 'golden/2026-09-24.published.json')))


def _bars(n, start=100.0, step=1.0, ts_fmt='2026-{m:02d}-{d:02d}'):
    """n rising daily OHLC bars with a small zigzag so swings form."""
    out = []
    for i in range(n):
        c = start + i * step + (3 if i % 4 == 0 else 0)
        d = i % 28 + 1
        m = 1 + (i // 28) % 12
        out.append((ts_fmt.format(m=m, d=d), c - 1, c + 1, c - 2, c))
    return out


def test_latest_read_none_without_history():
    assert latest_read('ES=F', [], []) is None
    assert latest_note(None) is None


def test_latest_read_computes_mas_rsi_and_both_structures():
    daily = _bars(260)
    read = latest_read('ES=F', _bars(80), daily)
    assert read['ticker'] == 'ES=F' and read['price'] == daily[-1][4]
    assert read['ma50'] is not None and read['ma200'] is not None and read['rsi14'] is not None
    assert read['hourly']['state'] is not None
    # compacted: only the last `lookback` labeled swings are carried
    assert len(read['hourly']['swings']) <= read['hourly']['lookback']
    json.dumps(read)  # must be storable in live.json


def test_latest_note_reads_like_the_trend_note():
    note = latest_note(latest_read('ES=F', _bars(80), _bars(260)))
    assert note.startswith('ES=F at ')
    assert '50-day average' in note and '200-day' in note and 'RSI(14)' in note
    assert '1H structure' in note and 'Weekly structure' in note


def test_page_unchanged_without_reads():
    a = PUB['assets'][0]
    assert latest_read_html(a, None) == ''
    assert latest_read_html(a, {'prices': {}}) == ''  # older live.json, no reads
    html = render(PUB, generated_at='2026-09-28T14:00:00Z',
                  live={'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {}})
    assert 'Latest read' not in html and 'now 1H' not in html


def test_page_shows_latest_read_and_now_badges():
    read = latest_read('ES=F', _bars(80), _bars(260))
    live = {'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {},
            'reads': {a['key']: read for a in PUB['assets']}}
    html = render(PUB, generated_at='2026-09-28T14:00:00Z', live=live)
    assert html.count('Latest read') == len(PUB['assets'])
    assert 'computed Mon Sep 28, 10:00 AM ET' in html
    assert 'now 1H' in html and 'now Weekly' in html
    # the board's own frozen badge is still there alongside: two per cell
    cells = sum(len(a['horizons']) for a in PUB['assets'])
    assert html.count('class="struct-badge') == 2 * cells

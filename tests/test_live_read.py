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


def test_since_board_news_only_after_the_board_and_matched_per_asset():
    from scripts.render_html import news_after
    log = [
        {'id': 'a', 'data': {'date': PUB['date'], 'event': 'same day', 'tickers': 'SPY', 'order': 1}},
        {'id': 'b', 'data': {'date': '2026-09-26', 'event': 'weekend trade deal', 'tickers': 'SPY', 'order': 1}},
        {'id': 'c', 'data': {'date': '2026-09-27', 'event': 'gold spikes', 'tickers': 'GLD', 'order': 1}},
    ]
    later = news_after(log, PUB['date'])
    assert [c['event'] for c in later] == ['gold spikes', 'weekend trade deal']  # newest first
    html = render(PUB, generated_at='2026-09-28T14:00:00Z', news_log=log)
    assert html.count('since the board (1)') == 2  # equities (SPY) and gold (GLD)
    assert 'not in these calls' in html


def test_no_since_board_panel_without_later_news():
    html = render(PUB, generated_at='2026-09-28T14:00:00Z', news_log=[])
    assert 'since the board' not in html


def test_usd_inside_a_crypto_pair_is_not_the_dollar():
    from scripts.render_html import matches_asset
    assert not matches_asset('dollar', {'tickers': 'USO, BTC-USD, SPY'})
    assert matches_asset('dollar', {'tickers': 'SPY, USD'})
    assert matches_asset('bonds', {'event': 'Treasury yields jump'})  # word endings still match


def test_hourly_chart_renders_candles_and_the_flat_zone():
    bars = [[f'2026-09-2{5 + i // 40}T{9 + i % 8:02d}:00:00-04:00', 100 + i, 101 + i, 99 + i, 100.5 + i]
            for i in range(100)]
    read = dict(latest_read('ES=F', _bars(80), _bars(260)), bars=bars)
    live = {'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {},
            'reads': {a['key']: read for a in PUB['assets']}}
    html = render(PUB, generated_at='2026-09-28T14:00:00Z', live=live)
    # one compact chart per price-strip tile, none down in the asset cards
    assert html.count('class="hchart compact"') == len(PUB['assets'])
    assert 'class="hchart"' not in html
    assert 'hc-zone' in html and 'shaded: 1D flat zone' in html
    assert '100 candles' in html
    strip = html.split('<div class="tape">')[1].split('<div class="stats"')[0]
    assert strip.count('hchart compact') == len(PUB['assets'])


def test_no_chart_without_bars():
    html = render(PUB, generated_at='2026-09-28T14:00:00Z',
                  live={'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {}, 'reads': {}})
    assert 'class="hchart' not in html


def test_price_strip_chart_has_no_price_tag_over_the_candles():
    bars = [[f'2026-09-28T{9 + i % 8:02d}:00:00-04:00', 100, 101, 99, 100.5] for i in range(50)]
    read = dict(latest_read('ES=F', _bars(80), _bars(260)), bars=bars)
    live = {'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {}, 'reads': {PUB['assets'][0]['key']: read}}
    from scripts.render_html import hourly_chart_html
    html = hourly_chart_html(PUB['assets'][0], live, compact=True)
    assert 'hc-last-tag' not in html and 'last 100.50 (dotted)' in html


def test_session_days_roll_at_9am_eastern():
    from scripts.render_html import session_days
    bars = [[ts, 1, 1, 1, 1] for ts in (
        '2026-09-24T08:00:00-04:00',   # still Wed's day (started Wed 9am)
        '2026-09-24T09:00:00-04:00',   # Thu's day starts
        '2026-09-25T08:00:00-04:00',   # ...and runs to Fri 8am
        '2026-09-25T09:00:00-04:00',   # Fri
        '2026-09-27T18:00:00-04:00',   # Sunday-evening reopen: still Friday's day
        '2026-09-28T08:00:00-04:00',   # ...up to Monday 8am
        '2026-09-28T09:00:00-04:00')]  # Monday's day starts at 9am, like every other
    assert session_days(bars) == [(0, 0, 'Wed 23'), (1, 2, 'Thu 24'), (3, 5, 'Fri 25'),
                                  (6, 6, 'Mon 28')]


def test_price_strip_chart_draws_alternating_day_bands_with_initials():
    from scripts.render_html import hourly_chart_html
    bars = [[f'2026-09-{21 + i // 24:02d}T{i % 24:02d}:00:00-04:00', 100, 101, 99, 100.5] for i in range(96)]
    read = dict(latest_read('ES=F', _bars(80), _bars(260)), bars=bars)
    live = {'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {}, 'reads': {PUB['assets'][0]['key']: read}}
    html = hourly_chart_html(PUB['assets'][0], live, compact=True)
    # Sep 21 00:00-24 23:00: the chart starts at Mon 21 9am (the partial Friday-day
    # morning is trimmed) -> Mon, Tue, Wed, Thu
    assert html.count('class="hc-day"') == 2          # every other one shaded
    assert html.count('class="hc-day-label"') == 4
    assert 'title="Mon 21"' in html and 'title="Fri 18"' not in html and 'title="Sun' not in html


def test_a_holiday_overnight_joins_the_previous_band():
    from scripts.render_html import session_days
    bars = [[ts, 1, 1, 1, 1] for ts in (
        '2026-09-04T09:00:00-04:00',   # Fri
        '2026-09-04T16:00:00-04:00',
        '2026-09-08T00:00:00-04:00',   # Labor Day Mon had no daytime candles; Tue overnight
        '2026-09-08T08:00:00-04:00',
        '2026-09-08T09:00:00-04:00')]  # Tue 9am: next band
    assert session_days(bars) == [(0, 3, 'Fri 4'), (4, 4, 'Tue 8')]


def test_chart_starts_at_a_9am_candle():
    from scripts.render_html import start_at_session_open
    bars = [[ts, 1, 1, 1, 1] for ts in (
        '2026-09-04T05:00:00-04:00',   # partial morning: dropped
        '2026-09-04T08:00:00-04:00',
        '2026-09-04T09:00:00-04:00',   # chart starts here
        '2026-09-04T10:00:00-04:00')]
    assert [b[0][11:16] for b in start_at_session_open(bars)] == ['09:00', '10:00']
    # already starting at 9am: unchanged
    assert start_at_session_open(bars[2:]) == bars[2:]


def test_every_day_start_after_the_first_gets_a_9am_line():
    from scripts.render_html import hourly_chart_html
    bars = [[f'2026-09-{21 + i // 24:02d}T{i % 24:02d}:00:00-04:00', 100, 101, 99, 100.5] for i in range(96)]
    read = dict(latest_read('ES=F', _bars(80), _bars(260)), bars=bars)
    live = {'fetchedAt': '2026-09-28T14:00:00Z', 'prices': {}, 'reads': {PUB['assets'][0]['key']: read}}
    html = hourly_chart_html(PUB['assets'][0], live, compact=True)
    assert html.count('class="hc-day-start"') == 3   # Mon | Tue | Wed | Thu

"""The News event issue form -> news_log.json entry."""
import pytest

from scripts.add_news_from_issue import build_entry, parse_issue_form

BODY = """### Date

2026-09-28

### Time

Market hours

### Event

Fed's Waller says a
November cut is on the table

### Tickers

SPY, TLT

### Direction

Bullish

### Impact

High

### Category

Fed

### Region

_No response_

### Numbers

_No response_

### Vs. expectations

_No response_

### Market reaction

Yields dip 5bp

### Source URL

https://example.com/waller
"""

LOG = [{'id': '2026-09-28-4-x', 'data': {'date': '2026-09-28', 'order': 4}}]


def test_parses_the_rendered_issue_form():
    f = parse_issue_form(BODY)
    assert f['date'] == '2026-09-28' and f['tickers'] == 'SPY, TLT'
    assert f['region'] == '' and f['source'] == 'https://example.com/waller'


def test_builds_an_entry_in_the_news_log_shape():
    e = build_entry(parse_issue_form(BODY), LOG, 7, '2026-09-28')
    d = e['data']
    assert e["id"] == "2026-09-28-5-fed-s-waller-says-a-november-cut-is-on-t"
    assert d['order'] == 5 and d['day'] == 'Mon' and d['region'] == 'US'
    assert d['event'] == "Fed's Waller says a November cut is on the table"
    assert d['numbers'] == 'n/a' and d['origin'] == 'manual (issue #7)'


def test_rejects_a_bad_date_or_missing_field():
    with pytest.raises(ValueError, match='YYYY-MM-DD'):
        build_entry(parse_issue_form(BODY.replace('2026-09-28', 'Sept 28')), [], 1, '2026-09-28')
    with pytest.raises(ValueError, match='tickers'):
        build_entry(parse_issue_form(BODY.replace('SPY, TLT', '_No response_')), [], 1, '2026-09-28')


def test_page_links_to_the_form():
    import json, os
    from scripts.render_html import render
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pub = json.load(open(os.path.join(root, 'golden/2026-09-24.published.json')))
    assert 'issues/new?template=news-event.yml' in render(pub, generated_at='2026-09-28T14:00:00Z')

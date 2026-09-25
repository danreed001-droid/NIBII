"""render_html: track record section, pure logic (no browser needed)."""
import copy
import json
import os

from scripts.render_html import pct_tone, render, track_record_section
from scripts.settle import settle_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = json.load(open(os.path.join(ROOT, 'golden/2026-09-24.published.json')))


def fake_close_fn(key, date):
    closes = {
        ('equities', '2026-09-25'): 7690.0, ('equities', '2026-10-01'): 7750.0,
        ('equities', '2026-10-08'): 7600.0,
        ('bonds', '2026-09-25'): 79.10, ('bonds', '2026-10-01'): 78.50,
        ('bonds', '2026-10-08'): 79.00,
        ('gold', '2026-09-25'): 4300.0, ('gold', '2026-10-01'): 4250.0,
        ('gold', '2026-10-08'): 4400.0,
        ('dollar', '2026-09-25'): 101.20, ('dollar', '2026-10-01'): 101.50,
        ('dollar', '2026-10-08'): 100.90,
        ('iwm', '2026-09-25'): 280.0, ('iwm', '2026-10-01'): 275.0,
        ('iwm', '2026-10-08'): 285.0,
        ('qqq', '2026-09-25'): 600.0, ('qqq', '2026-10-01'): 610.0,
        ('qqq', '2026-10-08'): 590.0,
    }
    return closes.get((key, date))


def test_pct_tone_boundaries():
    assert pct_tone(None) == 'flat'
    assert pct_tone(60) == 'good'
    assert pct_tone(40) == 'critical'
    assert pct_tone(50) == 'flat'


def test_track_record_empty_when_nothing_settled():
    html = track_record_section({PUB['date']: PUB})
    assert 'No calls have matured' in html


def test_track_record_reports_real_numbers_once_settled():
    doc = copy.deepcopy(PUB)
    settle_document(doc, close_fn=fake_close_fn)
    html = track_record_section({doc['date']: doc})
    assert 'record-pct' in html
    assert 'No calls have matured' not in html
    assert '18/18' in html or '/18' in html  # all 18 cells settled


def test_render_end_to_end_does_not_crash_with_settled_docs():
    doc = copy.deepcopy(PUB)
    settle_document(doc, close_fn=fake_close_fn)
    out = render(doc, {doc['date']: doc})
    assert '<title>Market Tape Ledger</title>' in out
    assert 'theme-toggle' in out

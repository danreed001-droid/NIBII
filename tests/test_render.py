"""render_html: track record section, pure logic (no browser needed)."""
import copy
import json
import os

from mtl.score import real_result
from scripts.render_html import call_log_section, pct_tone, render, track_record_section
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


def test_call_log_has_one_row_per_horizon_per_asset_before_settlement():
    html = call_log_section({PUB['date']: PUB})
    assert html.count('<tr>') == 19  # 1 header row + 6 assets x 3 horizons, none settled
    # 3 pending badges per unsettled row - actual_badge, result_badge and
    # real_result_badge each emit one
    assert html.count('log-pending') == 54
    assert 'log-correct' not in html and 'log-wrong' not in html and 'log-nocall' not in html


def test_call_log_shows_results_once_settled():
    doc = copy.deepcopy(PUB)
    settle_document(doc, close_fn=fake_close_fn)
    html = call_log_section({doc['date']: doc})
    assert 'log-pending' not in html
    assert ('log-correct' in html) or ('log-wrong' in html)
    # every row still names its own maturity date, independent of the others
    assert '2026-09-25' in html and '2026-10-01' in html and '2026-10-08' in html


def test_real_result_directional_call_ending_flat_is_no_call_not_wrong():
    # the market never actually tested the call - a push, not a miss
    assert real_result('bullish', 'flat') == 'no-call'
    assert real_result('bearish', 'flat') == 'no-call'


def test_real_result_flat_call_against_a_real_move_is_incorrect():
    assert real_result('flat', 'bullish') == 'incorrect'
    assert real_result('flat', 'bearish') == 'incorrect'


def test_real_result_opposite_direction_is_incorrect():
    assert real_result('bearish', 'bullish') == 'incorrect'
    assert real_result('bullish', 'bearish') == 'incorrect'


def test_real_result_matching_call_is_correct():
    assert real_result('bullish', 'bullish') == 'correct'
    assert real_result('bearish', 'bearish') == 'correct'
    assert real_result('flat', 'flat') == 'correct'


def test_real_result_no_call_to_grade_is_none():
    assert real_result(None, 'flat') is None
    assert real_result('no-call', 'bullish') is None


def test_call_log_caps_to_most_recent_sessions():
    many_docs = {}
    for i in range(20):
        d = copy.deepcopy(PUB)
        d['date'] = f"2026-08-{i + 1:02d}"
        many_docs[d['date']] = d
    html = call_log_section(many_docs)
    assert '14 most recent session' in html
    assert 'of 20 published total' in html

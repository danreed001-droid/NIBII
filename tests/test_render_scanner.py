"""docs/scanner.html - the Top 5 Strongest dashboard - embeds its data as JSON."""
import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location(
    'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
render_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_scanner)

SCAN = dict(generatedAt='2026-10-03T03:22:15+00:00', asOf='2026-10-02',
            holdings=[dict(t='EVIL', n='</script><script>alert(1)</script>', sec='X', rank=1)],
            table=[], trades=[], curves={}, years={}, stats={})


def test_data_is_embedded_and_cannot_close_the_script_block():
    page = render_scanner.render(SCAN)
    start = page.index('id="scan-data">') + len('id="scan-data">')
    blob = page[start:page.index('</script>', start)]
    assert json.loads(blob)['holdings'][0]['n'] == SCAN['holdings'][0]['n']
    assert '__DATA__' not in page


def test_page_links_to_the_ledger_and_the_backtests():
    page = render_scanner.render(SCAN)
    assert 'href="index.html"' in page and 'href="backtest.html"' in page


def test_page_has_the_plan_section_and_tolerates_old_data_without_it():
    page = render_scanner.render(SCAN)
    assert 'id="alloc"' in page and 'id="mix-seg"' in page and 'id="assets"' in page
    assert "if (!P || !SL)" in page          # scans without plan data still render


def test_holding_cards_open_a_swing_chart_panel():
    page = render_scanner.render(SCAN)
    assert 'id="swpanel"' in page and 'function drawSwing' in page
    assert "h.chart ?" in page            # cards without chart data stay plain


def test_page_has_the_human_calls_model():
    page = render_scanner.render(SCAN)
    for needle in ('id="choices"', 'id="call-save"', 'id="rec"', "nibii-calls-v1", 'id="call-import"'):
        assert needle in page
    assert "if (!P || !SL)" in page and "!HU || !HU.days.length" in page   # old data without the series still renders


def test_calls_sync_to_the_repo_and_ranges_filter_the_record():
    page = render_scanner.render(SCAN)
    assert "docs/my_calls.json" in page and "api.github.com/repos/" in page and "my_calls.json?t=" in page
    assert 'id="r-from"' in page and 'id="rr-from"' in page
    assert "m: 'del'" in page          # removals sync as tombstones, not silent deletes


def test_calls_can_swap_or_drop_stocks():
    page = render_scanner.render(SCAN)
    assert 'id="picks"' in page and 'Drop → cash' in page and 'function sigOf' in page and 'function slotsFor' in page


def test_on_deck_cards_open_their_own_swing_chart():
    page = render_scanner.render(SCAN)
    assert 'id="swpanel2"' in page and "openSwing(c.getAttribute('data-t'), 'swpanel2')" in page


def test_calls_are_submitted_as_a_github_issue():
    page = render_scanner.render(SCAN)
    assert 'id="call-submit"' in page and '/issues/new?title=' in page and 'Calls intake workflow' in page


def test_page_offers_the_bear_guard_mix():
    page = render_scanner.render(SCAN)
    assert "m === 'guard' ? 'Guard'" in page and 'bear guard' in page and 'A.guard.weights' in page

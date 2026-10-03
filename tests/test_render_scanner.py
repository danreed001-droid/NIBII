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

"""docs/scanner.html rendering - the scan data is embedded as JSON."""
import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location(
    'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
render_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_scanner)

SCAN = dict(generatedAt='2026-10-03T03:22:15+00:00', timeframes=['weekly', 'daily', '1h', '15m'],
            modes={'strict': 4, 'loose': 2},
            setups={'daily': dict(context=['weekly', 'daily'], trigger='1h', recentBars=7)},
            tickers=[dict(t='EVIL', n='</script><script>alert(1)</script>', sec='X', etf=False)])


def test_data_is_embedded_and_cannot_close_the_script_block():
    page = render_scanner.render(SCAN)
    start = page.index('id="scan-data">') + len('id="scan-data">')
    blob = page[start:page.index('</script>', start)]
    assert json.loads(blob)['tickers'][0]['n'] == SCAN['tickers'][0]['n']
    assert '__DATA__' not in page


def test_page_links_back_to_the_ledger():
    assert 'href="index.html"' in render_scanner.render(SCAN)

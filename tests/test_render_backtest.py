"""docs/backtest.html rendering."""
import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location(
    'render_backtest', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_backtest.py'))
render_backtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_backtest)


def test_data_is_embedded_safely_and_page_links_back():
    data = dict(generatedAt='2026-10-03T00:00:00+00:00', stake=100, tickers=1, note='</script>', results={})
    page = render_backtest.render(data)
    start = page.index('id="bt-data">') + len('id="bt-data">')
    assert json.loads(page[start:page.index('</script>', start)])['note'] == '</script>'
    assert 'href="scanner.html"' in page and '__DATA__' not in page

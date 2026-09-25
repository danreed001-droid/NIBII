"""patterns.analyze: pure logic, synthetic settled horizons + synthetic news log."""
from scripts.patterns import analyze, catalysts_in_window, MIN_SAMPLES

NEWS = [
    {"data": {"date": "2026-09-01", "category": "Fed", "direction": "Bearish",
              "tickers": "TLT, SHY", "event": "hawkish Fed speaker"}},
    {"data": {"date": "2026-09-02", "category": "Fed", "direction": "Bearish",
              "tickers": "SPY, QQQ", "event": "hawkish tone weighs on stocks"}},
    {"data": {"date": "2026-09-03", "category": "Earnings", "direction": "Bullish",
              "tickers": "QQQ, SMH", "event": "chip earnings beat"}},
]


def make_settled(asset_key, doc_date, maturity, outcome):
    return (asset_key, doc_date, maturity, outcome)


def test_catalysts_in_window_matches_by_ticker_and_date():
    hits = catalysts_in_window(NEWS, 'bonds', '2026-09-01', '2026-09-01')
    assert len(hits) == 1
    assert hits[0]['category'] == 'Fed'


def test_catalysts_in_window_excludes_out_of_range_dates():
    hits = catalysts_in_window(NEWS, 'bonds', '2026-09-03', '2026-09-05')
    assert hits == []


def test_analyze_gates_cells_below_min_samples():
    settled = [make_settled('bonds', '2026-09-01', '2026-09-01', 'bearish')]
    table = analyze(NEWS, settled)
    cell = table['bonds']['Fed']
    assert cell['n'] == 1
    assert cell['reliable'] is False
    assert cell['rate'] is None  # never reports a rate below MIN_SAMPLES


def test_analyze_reports_a_rate_once_min_samples_reached():
    settled = [make_settled('bonds', '2026-09-01', '2026-09-01', 'bearish')] * MIN_SAMPLES
    table = analyze(NEWS, settled)
    cell = table['bonds']['Fed']
    assert cell['n'] == MIN_SAMPLES
    assert cell['reliable'] is True
    assert cell['rate'] == 1.0


def test_analyze_ignores_mixed_and_neutral_catalysts():
    mixed_news = [{"data": {"date": "2026-09-01", "category": "Policy", "direction": "Mixed",
                            "tickers": "SPY", "event": "n/a"}}]
    settled = [make_settled('equities', '2026-09-01', '2026-09-01', 'bullish')]
    table = analyze(mixed_news, settled)
    assert table == {}

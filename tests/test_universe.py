"""The scanner's default universe: fixed ETFs + the S&P 500 csv."""
from mtl.universe import ETFS, default_universe, load_sp500


def test_sp500_csv_is_complete_and_in_yahoo_form():
    sp = load_sp500()
    assert 490 <= len(sp) <= 510
    assert 'AAPL' in sp and 'BRK-B' in sp
    assert not any('.' in s for s in sp)


def test_default_universe_puts_the_etfs_first():
    u = default_universe()
    assert list(u)[:len(ETFS)] == ['XLF', 'XLU', 'XLY', 'EEM', 'GLD', 'SLV']
    assert len(u) == len(ETFS) + len(load_sp500())

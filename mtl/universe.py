"""The multi-timeframe scanner's default universe: a fixed ETF list plus
the S&P 500 constituents in data/sp500.csv (refresh with
scripts/update_sp500.py)."""
import csv
import os

SP500_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'data', 'sp500.csv')

ETFS = {
    'XLF': ('Financial Select Sector SPDR', 'ETF'),
    'XLU': ('Utilities Select Sector SPDR', 'ETF'),
    'XLY': ('Consumer Discretionary Select Sector SPDR', 'ETF'),
    'EEM': ('iShares MSCI Emerging Markets', 'ETF'),
    'GLD': ('SPDR Gold Shares', 'ETF'),
    'SLV': ('iShares Silver Trust', 'ETF'),
}


def load_sp500(path=SP500_PATH):
    """{symbol: (name, sector)} in Yahoo symbol form."""
    with open(path, newline='') as f:
        return {r['symbol']: (r['name'], r['sector']) for r in csv.DictReader(f)}


def default_universe():
    """{symbol: (name, sector)}: the ETFs first, then the S&P 500."""
    return {**ETFS, **load_sp500()}

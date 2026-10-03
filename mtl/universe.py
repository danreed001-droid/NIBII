"""The multi-timeframe scanner's default universe: a fixed ETF list plus
the S&P 500 constituents in data/sp500.csv.

The S&P list keeps itself current: default_universe() re-downloads it from
Wikipedia when the saved copy is more than MAX_AGE_DAYS old (the date of
the last refresh lives in data/sp500.asof - file mtimes reset on every
git clone, so they can't be trusted). If the download fails, the saved
list is used as-is - a few days stale beats no scan.
"""
import csv
import io
import os
import sys
import urllib.request
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
SP500_PATH = os.path.join(DATA_DIR, 'sp500.csv')
ASOF_PATH = os.path.join(DATA_DIR, 'sp500.asof')
URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
MAX_AGE_DAYS = 7
MIN_CONSTITUENTS = 490  # fewer parsed = the page layout changed; don't overwrite

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


def fetch_sp500():
    """Downloads the constituents table -> {symbol: (name, sector, date
    added to the index)}, with symbols in Yahoo's form (BRK.B -> BRK-B)."""
    import pandas as pd
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=60).read().decode()
    t = pd.read_html(io.StringIO(html), attrs={'id': 'constituents'})[0]
    added = pd.to_datetime(t['Date added'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
    return {s.replace('.', '-'): (n, sec, a)
            for s, n, sec, a in zip(t['Symbol'], t['Security'], t['GICS Sector'], added)}


def last_refreshed(asof_path=ASOF_PATH):
    try:
        with open(asof_path) as f:
            return date.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return None


def refresh_sp500(path=SP500_PATH, asof_path=ASOF_PATH, today=None, fetch=fetch_sp500):
    """Re-downloads the list and saves it. Returns (added, removed) symbol
    lists versus the previous copy. Raises if the download fails or parses
    implausibly short - the saved copy is never replaced by a broken one."""
    new = fetch()
    if len(new) < MIN_CONSTITUENTS:
        raise ValueError(f"only {len(new)} constituents parsed - page layout changed?")
    old = load_sp500(path) if os.path.exists(path) else {}
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['symbol', 'name', 'sector', 'added'])
        w.writerows((s, *v, '')[:4] for s, v in sorted(new.items()))
    with open(asof_path, 'w') as f:
        f.write((today or date.today()).isoformat() + '\n')
    return sorted(set(new) - set(old)), sorted(set(old) - set(new))


def ensure_fresh(path=SP500_PATH, asof_path=ASOF_PATH, today=None, max_age_days=MAX_AGE_DAYS,
                 fetch=fetch_sp500, log=lambda msg: print(msg, file=sys.stderr)):
    """Refreshes the saved list if it's older than max_age_days (or has no
    refresh date). Never raises: on failure it logs and keeps the old list."""
    today = today or date.today()
    asof = last_refreshed(asof_path)
    if asof is not None and (today - asof).days <= max_age_days and os.path.exists(path):
        return False
    try:
        added, removed = refresh_sp500(path, asof_path, today, fetch)
    except Exception as e:
        log(f"S&P 500 list refresh failed ({e}); using saved list from {asof or 'unknown date'}")
        return False
    change = ', '.join(filter(None, [f"added {' '.join(added)}" if added else '',
                                     f"removed {' '.join(removed)}" if removed else '']))
    log(f"S&P 500 list refreshed: {change or 'no changes'}")
    return True


def load_added(path=SP500_PATH):
    """{symbol: 'YYYY-MM-DD' it joined the S&P 500} where known - lets a
    backtest skip a stock before it was actually in the index (otherwise
    today's list smuggles in hindsight: stocks get added AFTER big runs)."""
    with open(path, newline='') as f:
        return {r['symbol']: r['added'] for r in csv.DictReader(f) if r.get('added')}


def default_universe(refresh=True):
    """{symbol: (name, sector)}: the ETFs first, then the S&P 500."""
    if refresh:
        ensure_fresh()
    return {**ETFS, **load_sp500()}


# --- Nasdaq-100 (QQQ) - the momentum dashboard ranks S&P 500 + Nasdaq-100 ---

NDX_PATH = os.path.join(DATA_DIR, 'ndx100.csv')
NDX_ASOF_PATH = os.path.join(DATA_DIR, 'ndx100.asof')
NDX_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
NDX_MIN = 95


def fetch_ndx():
    """Downloads the Nasdaq-100 table -> {symbol: (name, industry)}."""
    import pandas as pd
    req = urllib.request.Request(NDX_URL, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=60).read().decode()
    t = next(x for x in pd.read_html(io.StringIO(html)) if 'Ticker' in x.columns and len(x) >= NDX_MIN)
    ind = next((c for c in t.columns if str(c).startswith('ICB Industry')), None)
    return {str(s).replace('.', '-'): (n, t[ind][i] if ind is not None else '')
            for i, (s, n) in enumerate(zip(t['Ticker'], t['Company']))}


def load_ndx(path=NDX_PATH):
    """{symbol: (name, industry)} - industry is '' for an older saved copy."""
    with open(path, newline='') as f:
        return {r['symbol']: (r['name'], r.get('industry', '')) for r in csv.DictReader(f)}


def refresh_ndx(path=NDX_PATH, asof_path=NDX_ASOF_PATH, today=None, fetch=fetch_ndx):
    """Same contract as refresh_sp500, for the Nasdaq-100 list."""
    new = fetch()
    if len(new) < NDX_MIN:
        raise ValueError(f"only {len(new)} Nasdaq-100 members parsed - page layout changed?")
    old = load_ndx(path) if os.path.exists(path) else {}
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['symbol', 'name', 'industry'])
        w.writerows((s, *v) for s, v in sorted(new.items()))
    with open(asof_path, 'w') as f:
        f.write((today or date.today()).isoformat() + '\n')
    return sorted(set(new) - set(old)), sorted(set(old) - set(new))


def ensure_fresh_ndx(path=NDX_PATH, asof_path=NDX_ASOF_PATH, today=None, max_age_days=MAX_AGE_DAYS,
                     fetch=fetch_ndx, log=lambda msg: print(msg, file=sys.stderr)):
    """ensure_fresh for the Nasdaq-100 list: refresh when stale, never raise."""
    today = today or date.today()
    asof = last_refreshed(asof_path)
    if asof is not None and (today - asof).days <= max_age_days and os.path.exists(path):
        return False
    try:
        added, removed = refresh_ndx(path, asof_path, today, fetch)
    except Exception as e:
        log(f"Nasdaq-100 list refresh failed ({e}); using saved list from {asof or 'unknown date'}")
        return False
    change = ', '.join(filter(None, [f"added {' '.join(added)}" if added else '',
                                     f"removed {' '.join(removed)}" if removed else '']))
    log(f"Nasdaq-100 list refreshed: {change or 'no changes'}")
    return True


def momentum_universe(refresh=True):
    """{symbol: (name, sector)} for the momentum dashboard: every S&P 500
    stock plus the Nasdaq-100 members that aren't in it (sector = their ICB
    industry). No ETFs - an ETF never ranks among the strongest stocks."""
    if refresh:
        ensure_fresh()
        ensure_fresh_ndx()
    out = load_sp500()
    for s, (n, ind) in load_ndx().items():
        out.setdefault(s, (n, ind))
    return out

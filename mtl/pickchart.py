"""The scanner's "any stock" chart: the last N sessions of daily bars for every stock the scan fetched, written to
docs/ohlc.json so the page loads it only when a ticker is picked (owner's ask, Nov 21, 2026).

Pure apart from write(): bars {ticker: [(date, open, high, low, close)]}, names {ticker: name}."""
import json
import os

N = 260   # about a year of sessions (the 1Y view), plus a week


def _r(x):
    return None if x is None or x != x else (round(x, 2) if abs(x) >= 1 else round(x, 4))


def build(bars, names=None, n=N, volumes=None):
    """{'dates': [...], 't': {ticker: [[o, h, l, c, volume] or None per date]}, 'n': {ticker: name}} on the last n dates
    any ticker has; a ticker without a bar on a date gets None there; volume is None where unknown."""
    days = sorted({b[0][:10] for bs in bars.values() for b in (bs or [])[-n - 10:]})[-n:]
    ix = {d: i for i, d in enumerate(days)}
    out = {}
    for t, bs in sorted(bars.items()):
        row = [None] * len(days)
        for b in bs or []:
            i = ix.get(b[0][:10])
            if i is not None:
                v = ((volumes or {}).get(t) or {}).get(b[0][:10])
                row[i] = [_r(b[1]), _r(b[2]), _r(b[3]), _r(b[4]), int(v) if v else None]
        if any(row):
            out[t] = row
    nm = {t: (names or {}).get(t) for t in out if (names or {}).get(t)}
    return {'dates': days, 't': out, 'n': nm}


FUNDS = {'SPY': 'S&P 500 fund', 'QQQ': 'Nasdaq-100 fund', 'RSP': 'Equal-weight S&P 500', 'GLD': 'Gold',
         'TLT': 'Long Treasuries (20y+)', 'IEF': 'Treasuries (7-10y)', 'UUP': 'US dollar', 'DBC': 'Commodities',
         'BIL': 'T-bills (1-3 month)', 'DBMF': 'Managed futures'}


def load_names(root):
    """{ticker: name} from data/sp500.csv and data/ndx100.csv, plus the funds (FUNDS)."""
    import csv
    out = dict(FUNDS)
    for f in ('sp500.csv', 'ndx100.csv'):
        p = os.path.join(root, 'data', f)
        if os.path.exists(p):
            with open(p) as fh:
                for r in csv.DictReader(fh):
                    if r.get('symbol') and r.get('name'):
                        out.setdefault(r['symbol'], r['name'])
    return out


def write(path, bars, names=None, n=N, volumes=None):
    data = build(bars, names, n, volumes)
    with open(path, 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    return len(data['t'])

"""Refresh data/flow_box.json: weekly closes, 14-day RSI and what the plan held, for stocks, long bonds, gold, managed
futures and cash since 2000 (mtl/flowbox.py), for the money flow animation on the scanner page. Information only; run
nightly by the scanner workflow, where a failure never blocks the page (it keeps the last file)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import flowbox  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'flow_box.json')


def closes(ticker, start):
    """Daily dividend-adjusted closes as [(isodate, close)] since `start` (yfinance), so a fund's payouts (DBMF pays
    most of a year's in one go in December) do not show as falls."""
    import yfinance as yf
    df = yf.Ticker(ticker).history(start=start, auto_adjust=True)
    if df is None or df.empty:
        return []
    return [(i.date().isoformat(), float(c)) for i, c in zip(df.index, df['Close']) if c == c]


SIZES = os.path.join(ROOT, 'data', 'market_sizes.json')
FRED = {'stocks': 'BOGZ1FL893064105Q', 'bonds': 'FYGFDPUN', 'cash': 'MMMFFAQ027S'}


def refresh_sizes():
    """data/market_sizes.json, with its three FRED quarterly series refreshed when FRED answers (best effort: on any
    failure the file's last values stand)."""
    with open(SIZES) as fh:
        M = json.load(fh)
    try:
        import csv
        import io
        import urllib.request
        from datetime import date, timedelta
        for key, sid in FRED.items():
            url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'
            with urllib.request.urlopen(url, timeout=20) as r:
                rows = list(csv.reader(io.StringIO(r.read().decode())))[1:]
            pts = []
            for d, v in rows:
                if d < '1999-01-01' or v in ('', '.'):
                    continue
                y, m = int(d[:4]), int(d[5:7]) + 3
                end = date(y + (m - 1) // 12, (m - 1) % 12 + 1, 1) - timedelta(days=1)   # FRED dates a quarter by its start
                pts.append([end.isoformat(), round(float(v) / 1000, 1)])
            if len(pts) > 50:
                M[key] = pts
        with open(SIZES, 'w') as fh:
            json.dump(M, fh, separators=(',', ':'))
            fh.write('\n')
    except Exception as e:   # information only: keep the last values
        print(f'  market sizes: FRED refresh skipped ({e})')
    return M


def main():
    with open(os.path.join(ROOT, 'data', 'plan_history.json')) as fh:
        ph = json.load(fh)
    try:
        with open(os.path.join(ROOT, 'data', 'paper_ledger.json')) as fh:
            entries = json.load(fh).get('entries') or []
    except (OSError, ValueError):
        entries = []
    start = ph['prices']['dates'][-1][:4] + '-01-01'
    fresh = {}
    for t in ('SPY', 'TLT', 'GLD'):
        fresh[t] = closes(t, start)
        if not fresh[t]:
            sys.exit(f'flow box: no closes for {t}; keeping the last file')
    fresh['DBMF'] = closes('DBMF', '2019-05-01')
    if not fresh['DBMF']:
        sys.exit('flow box: no closes for DBMF; keeping the last file')
    sizes = refresh_sizes()
    doc = flowbox.build(ph, fresh, entries, sizes)
    doc['asOf'] = doc['d'][-1]
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
        fh.write('\n')
    print(f"flow box: {len(doc['d'])} weeks, {doc['d'][0]} to {doc['d'][-1]}; last held {doc['h'][-1]}; "
          f"RSI SPY {doc['rs'][-1]} TLT {doc['rb'][-1]} GLD {doc['rg'][-1]} DBMF {doc['rf'][-1]}")


if __name__ == '__main__':
    main()

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
    doc = flowbox.build(ph, fresh, entries)
    doc['asOf'] = doc['d'][-1]
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
        fh.write('\n')
    print(f"flow box: {len(doc['d'])} weeks, {doc['d'][0]} to {doc['d'][-1]}; last held {doc['h'][-1]}; "
          f"RSI SPY {doc['rs'][-1]} TLT {doc['rb'][-1]} GLD {doc['rg'][-1]} DBMF {doc['rf'][-1]}")


if __name__ == '__main__':
    main()

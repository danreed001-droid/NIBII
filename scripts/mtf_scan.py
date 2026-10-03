#!/usr/bin/env python3
"""Multi-timeframe buy scanner - see mtl/mtf.py for the rules.

Usage:
    python scripts/mtf_scan.py                 # the Ledger's six markets
    python scripts/mtf_scan.py NQ=F AAPL BTC-USD
    python scripts/mtf_scan.py SPY --json
    python scripts/mtf_scan.py SPY --include-forming   # also use unfinished bars
    python scripts/mtf_scan.py SPY --lookback 2        # looser trend read: latest high+low only
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.fetch import TICKERS
from mtl.mtf import SETUPS, TIMEFRAMES, scan

ARROW = {'uptrend': '▲ up', 'downtrend': '▼ down', 'choppy': '◆ choppy', None: '· n/a'}


def render(r):
    lines = [f"\n=== {r['ticker']} ==="]
    for tf in TIMEFRAMES:
        t = r['timeframes'][tf]
        b = t['lastBreak']
        brk = f"last break: {b['direction']} {b['kind']} {t['barsAgo']} bars ago" if b else "no break yet"
        lines.append(f"  {tf:>6}  {ARROW[t['state']]:<10} {'/'.join(t['labels']) or '-':<14} {brk}")
    for name in SETUPS:
        s = r['setups'][name]
        line = f"  {name.upper():>6} trade: {s['verdict']:<5}  {s['reason']}"
        if s['verdict'] == 'BUY':
            stop = f"{s['stop']:.4g}" if s['stop'] is not None else 'n/a'
            line += f"\n{'':>21}entry ~{s['entry']:.4g}  stop below {stop}"
        lines.append(line)
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tickers', nargs='*', default=list(TICKERS.values()))
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--include-forming', action='store_true')
    ap.add_argument('--lookback', type=int, default=4,
                    help='recent labeled swings that must all agree for a trend (default 4)')
    args = ap.parse_args()
    results = []
    for tk in args.tickers:
        try:
            results.append(scan(tk, include_forming=args.include_forming, lookback=args.lookback))
        except Exception as e:  # one bad ticker shouldn't kill the scan
            results.append(dict(ticker=tk, error=str(e)))
    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return
    for r in results:
        print(f"\n=== {r['ticker']} ===\n  error: {r['error']}" if 'error' in r else render(r))


if __name__ == '__main__':
    main()

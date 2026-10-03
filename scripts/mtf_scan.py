#!/usr/bin/env python3
"""Multi-timeframe buy/sell scanner - see mtl/mtf.py for the rules.

With no tickers it scans the default universe (mtl/universe.py): the
XLF/XLU/XLY/EEM/GLD/SLV ETFs plus every S&P 500 stock in data/sp500.csv,
and prints a summary of the BUY/SELL signals. A short list of tickers
(10 or fewer) gets the full per-timeframe detail instead.

Usage:
    python scripts/mtf_scan.py                    # ETFs + S&P 500, summary
    python scripts/mtf_scan.py --watch            # ...also list WATCH names
    python scripts/mtf_scan.py --csv scan.csv     # ...and save every row
    python scripts/mtf_scan.py AAPL XLF           # detail for a few tickers
    python scripts/mtf_scan.py SPY --json
    python scripts/mtf_scan.py --include-forming  # also use unfinished bars
    python scripts/mtf_scan.py --lookback 2       # looser trend read: latest high+low only
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.mtf import SETUPS, TIMEFRAMES, fetch_series_many, scan_bars
from mtl.universe import ETFS, default_universe

ARROW = {'uptrend': '▲ up', 'downtrend': '▼ down', 'choppy': '◆ choppy', None: '· n/a'}
DETAIL_MAX = 10


def fmt(x):
    return f"{x:.4g}" if x is not None else '-'


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
        if s['verdict'] in ('BUY', 'SELL'):
            where = 'below' if s['verdict'] == 'BUY' else 'above'
            line += f"\n{'':>21}entry ~{fmt(s['entry'])}  stop {where} {fmt(s['stop'])}"
        lines.append(line)
    return '\n'.join(lines)


def rows(results, names):
    """One flat row per ticker x setup."""
    for r in results:
        name, sector = names.get(r['ticker'], ('', ''))
        if 'error' in r:
            yield dict(ticker=r['ticker'], name=name, sector=sector, setup='', verdict='ERROR',
                       entry=None, stop=None, reason=r['error'])
            continue
        for setup, s in r['setups'].items():
            yield dict(ticker=r['ticker'], name=name, sector=sector, setup=setup,
                       verdict=s['verdict'], entry=s['entry'], stop=s['stop'], reason=s['reason'],
                       **{tf: r['timeframes'][tf]['state'] for tf in TIMEFRAMES})


def summary(results, names, show_watch):
    flat = list(rows(results, names))
    errors = [r for r in flat if r['verdict'] == 'ERROR']
    ok = len(results) - len(errors)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    out = [f"Scanned {len(results)} tickers at {stamp}: {ok} ok, {len(errors)} without data"]
    sections = ['BUY', 'SELL'] + (['WATCH'] if show_watch else [])
    for verdict in sections:
        hits = sorted((r for r in flat if r['verdict'] == verdict),
                      key=lambda r: (r['setup'], r['ticker']))
        out.append(f"\n{verdict} ({len(hits)})")
        if not hits:
            out.append("  none")
            continue
        out.append(f"  {'TICKER':<7}{'SETUP':<8}{'ENTRY':>10}{'STOP':>10}  {'SECTOR':<24}WHY")
        for r in hits:
            out.append(f"  {r['ticker']:<7}{r['setup']:<8}{fmt(r['entry']):>10}{fmt(r['stop']):>10}  "
                       f"{r['sector'][:23]:<24}{r['reason']}")
    counts = {v: sum(r['verdict'] == v for r in flat) for v in ('WATCH', 'NO')}
    out.append(f"\nOther setups: {counts['WATCH']} WATCH"
               f"{'' if show_watch else ' (--watch to list)'}, {counts['NO']} NO")
    if errors:
        out.append("No data: " + ', '.join(r['ticker'] for r in errors))
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tickers', nargs='*', help='default: ETFs + S&P 500')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--csv', metavar='FILE', help='write one row per ticker x setup')
    ap.add_argument('--watch', action='store_true', help='list WATCH setups in the summary')
    ap.add_argument('--details', action='store_true', help='full per-timeframe detail for every ticker')
    ap.add_argument('--include-forming', action='store_true')
    ap.add_argument('--lookback', type=int, default=4,
                    help='recent labeled swings that must all agree for a trend (default 4)')
    args = ap.parse_args()

    names = default_universe()
    tickers = [t.upper() for t in args.tickers] or list(names)
    print(f"Fetching weekly/daily/1h/15m bars for {len(tickers)} tickers...", file=sys.stderr)
    series = fetch_series_many(tickers, include_forming=args.include_forming)
    results = []
    for tk in tickers:
        s = series[tk]
        if not s.get('daily'):
            results.append(dict(ticker=tk, error='no data from Yahoo'))
            continue
        try:
            results.append(dict(ticker=tk, **scan_bars(s, args.lookback)))
        except Exception as e:  # one bad ticker shouldn't kill the scan
            results.append(dict(ticker=tk, error=str(e)))

    if args.csv:
        fields = ['ticker', 'name', 'sector', 'setup', 'verdict', 'entry', 'stop', *TIMEFRAMES, 'reason']
        with open(args.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, restval='')
            w.writeheader()
            w.writerows(rows(results, names))
        print(f"wrote {args.csv}", file=sys.stderr)
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    elif args.details or len(tickers) <= DETAIL_MAX:
        for r in results:
            print(f"\n=== {r['ticker']} ===\n  error: {r['error']}" if 'error' in r else render(r))
    else:
        print(summary(results, names, args.watch))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Tests risk-management and filter variants of the daily trade against the
original rule, over the same universe and window as scripts/backtest.py.

Exits: the original 1h flip, 1h flip + structure stop, stop + take profit
at 1/2/3R, stop + exit on the daily chart's flip, and a 3-candle
confirmation of the 1h reversal on entry (and optionally exit). Filter: SPY above its
200-day average for buys, below it for sells. Each variant is reported for
buys, sells and both, and split into an in-sample period (entries before
--split) and an out-of-sample period (from --split on) - choose on the
first, check on the second, so a variant that merely fit the past shows up.

Price history is cached in data/.bt_cache.pkl for a day (gitignored).

Usage:
    python scripts/backtest_variants.py
    python scripts/backtest_variants.py --split 2026-01-01
"""
import argparse
import json
import os
import pickle
import sys
import time
from bisect import bisect_left
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402  (scripts/backtest.py)
from mtl.backtest import (ET, SETUPS, consistent, curve_stats, portfolio_index,  # noqa: E402
                          simulate_variant, summarize)
from mtl.universe import default_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.bt_cache.pkl')

EXITS = {
    'flip':       dict(exit='flip', use_stop=False, label='1h flip (original)'),
    'flip+stop':  dict(exit='flip', use_stop=True, label='1h flip + swing stop'),
    'rr1':        dict(exit='rr', rr=1.0, use_stop=True, label='stop + target 1R'),
    'rr2':        dict(exit='rr', rr=2.0, use_stop=True, label='stop + target 2R'),
    'rr3':        dict(exit='rr', rr=3.0, use_stop=True, label='stop + target 3R'),
    'daily+stop': dict(exit='daily', use_stop=True, label='stop + daily-chart flip'),
    'conf3':      dict(exit='flip', use_stop=False, confirm=3, label='enter 3 candles after a held 1h reversal'),
    'conf3x':     dict(exit='flip', use_stop=False, confirm=3, confirm_exit=True,
                       label='enter and exit 3 candles after a held 1h reversal'),
    'conf3x+stop': dict(exit='flip', use_stop=True, confirm=3, confirm_exit=True,
                        label='3-candle confirmed entry/exit + swing stop'),
}


def load_data(tickers):
    if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 86400:
        with open(CACHE, 'rb') as f:
            c = pickle.load(f)
        if c['tickers'] == tickers:
            print("using cached price history", file=sys.stderr)
            return c['raw'], c['bench']
    raw, bench = bt.fetch_all(tickers), bt.fetch_benchmarks()
    with open(CACHE, 'wb') as f:
        pickle.dump(dict(tickers=tickers, raw=raw, bench=bench), f)
    return raw, bench


def regime_filter(spy):
    """allow(side, when): buys only when SPY's previous close was above its
    200-day average, sells only when below. Uses the session BEFORE the
    entry's date so nothing from the entry day leaks in."""
    dates = [d for d, _ in spy]
    closes = [c for _, c in spy]
    above = {}
    for k in range(199, len(closes)):
        above[dates[k]] = closes[k] > sum(closes[k - 199:k + 1]) / 200

    def allow(side, when):
        k = bisect_left(dates, when.date().isoformat()) - 1
        if k < 199:
            return False
        return above[dates[k]] if side == 'long' else not above[dates[k]]
    return allow


def stats_row(trades, closes, cal):
    s = summarize(trades)
    if not s.get('trades'):
        return dict(trades=0)
    idx = portfolio_index(trades, closes, cal)
    g = curve_stats([p[1] for p in idx])
    return dict(trades=s['trades'], winRate=s['winRate'], avgRet=s['avgRet'], pf=s['profitFactor'],
                pnl=s['totalPnl'], acct=g['total'], maxDD=g['maxDD'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--start', default='2020-01-01')
    ap.add_argument('--split', default='2026-01-01')
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'variants.json'))
    args = ap.parse_args()

    names = default_universe()
    tickers = list(names)
    raw, bench = load_data(tickers)
    start = datetime.fromisoformat(args.start).replace(tzinfo=ET)
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    ranges = {tk: {b[0][:10]: (b[3], b[2]) for b in raw[tk].get('daily', [])} for tk in tickers}
    series = {tk: bt.build_series(raw[tk]) for tk in tickers if raw[tk].get('daily')}
    sessions = [d for d, _ in bench['SPY']]
    allow_regime = regime_filter(bench['SPY'])
    setup = SETUPS['daily']

    results = []
    for mode, lookback in bt.MODES.items():
        for ex_key, ex in EXITS.items():
            for filt in ('none', 'spy200'):
                trades = []
                for tk, ser in series.items():
                    for t in simulate_variant(ser, setup, lookback, start, ticker=tk, exit=ex['exit'],
                                              rr=ex.get('rr', 2.0), use_stop=ex['use_stop'],
                                              confirm=ex.get('confirm', 0), confirm_exit=ex.get('confirm_exit', False),
                                              allow=allow_regime if filt == 'spy200' else None):
                        if consistent(t, ranges):
                            trades.append(t)
                if not trades:
                    continue
                first = min(t['entryTime'] for t in trades)[:10]
                last = max(t['exitTime'] for t in trades)[:10]
                cal = [d for d in sessions if first <= d <= last]
                for side in ('long', 'short', 'all'):
                    st = trades if side == 'all' else [t for t in trades if t['side'] == side]
                    ins = [t for t in st if t['entryTime'][:10] < args.split]
                    oos = [t for t in st if t['entryTime'][:10] >= args.split]
                    row = dict(mode=mode, exit=ex_key, exitLabel=ex['label'], filter=filt, side=side,
                               full=stats_row(st, closes, cal),
                               inSample=stats_row(ins, closes, [d for d in cal if d < args.split]),
                               outSample=stats_row(oos, closes, [d for d in cal if d >= args.split]))
                    results.append(row)
                    f, i, o = row['full'], row['inSample'], row['outSample']
                    if f.get('trades'):
                        print(f"{mode:6} {ex_key:10} {filt:6} {side:5} n={f['trades']:5} win {f['winRate']:.0%} "
                              f"avg {f['avgRet']:+.2%} PF {f['pf'] or 0:.2f} acct {f['acct']:+.0%} DD {f['maxDD']:.0%} | "
                              f"IS avg {i.get('avgRet', 0):+.2%} PF {i.get('pf') or 0:.2f} | "
                              f"OOS n={o.get('trades', 0)} avg {o.get('avgRet', 0):+.2%} PF {o.get('pf') or 0:.2f} acct {o.get('acct') or 0:+.0%}",
                              flush=True)
    bstats = {b: curve_stats([c for d, c in pts if d >= '2023-11-08']) for b, pts in bench.items()}
    oos_b = {b: curve_stats([c for d, c in pts if d >= args.split]) for b, pts in bench.items()}
    print("benchmarks full:", {b: f"{s['total']:+.0%}" for b, s in bstats.items()})
    print(f"benchmarks from {args.split}:", {b: f"{s['total']:+.0%}" for b, s in oos_b.items()})
    with open(args.out, 'w') as f:
        json.dump(dict(split=args.split, results=results, benchFull=bstats, benchOOS=oos_b), f)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == '__main__':
    main()

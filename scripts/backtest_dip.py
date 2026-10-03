#!/usr/bin/env python3
"""Buy-the-dip backtest (mtl.backtest.simulate_dip): a stock closes 10%+
below its 20-day high, then the 1h chart prints its first higher high
(bullish CHoCH) -> buy; sell at +20%. Variants add a stop, a time stop, a
10% target and a weekly-uptrend filter. Buys only, S&P 500 + ETFs, a
stock only counted once it was in the index. 1h history limits this to
Nov 2023 on; 2026 is the out-of-sample check. Trades still open at the
end are marked at the last close and INCLUDED in every number.

Reuses the price cache from scripts/backtest_variants.py.

Usage:
    python scripts/backtest_dip.py
"""
import os
import statistics
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import ET, consistent, curve_stats, portfolio_index, simulate_dip  # noqa: E402
from mtl.universe import default_universe, load_added  # noqa: E402

SPLIT = '2026-01-01'
SESSION_BARS = 7  # 1h bars per regular session
VARIANTS = {
    'A. your rules: +20% target, no stop': dict(target=0.20),
    'B. +20% target, -10% stop': dict(target=0.20, stop=0.10),
    'C. +20% target, sell after 60 days': dict(target=0.20, max_bars=60 * SESSION_BARS),
    'D. +10% target, no stop': dict(target=0.10),
    'E. A + weekly chart in uptrend': dict(target=0.20, weekly_up=True),
}


def describe(trades, closes, sessions):
    if not trades:
        return None
    rets = [t['ret'] for t in trades]
    marked = [dict(t, open=False) for t in trades]
    first = min(t['entryTime'] for t in trades)[:10]
    cal = [d for d in sessions if d >= first]
    acct = curve_stats([p[1] for p in portfolio_index(marked, closes, cal)])
    by = lambda r: sum(t['exitReason'] == r for t in trades) / len(trades)
    opn = [t['ret'] for t in trades if t['open']]
    return dict(n=len(trades), target=by('target'), stop=by('stop'), time=by('time'), open=by('open'),
                avg=statistics.mean(rets), median=statistics.median(rets),
                days=statistics.mean(t['bars'] for t in trades) / SESSION_BARS,
                openAvg=statistics.mean(opn) if opn else None, acct=acct['total'], dd=acct['maxDD'])


def main():
    names = default_universe(refresh=False)
    tickers = list(names)
    raw, bench = load_data(tickers)
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    ranges = {tk: {b[0][:10]: (b[3], b[2]) for b in raw[tk].get('daily', [])} for tk in tickers}
    added = load_added()
    sessions = [d for d, _ in bench['SPY']]
    start = datetime(2020, 1, 1, tzinfo=ET)
    series = {tk: bt.build_series(raw[tk]) for tk in tickers if raw[tk].get('daily') and raw[tk].get('1h')}

    print(f"{'version':40} {'trades':>6} {'hit +tgt':>8} {'stopped':>7} {'timed':>6} {'open':>5} "
          f"{'avg':>7} {'median':>7} {'days':>5} {'open avg':>8} | {'account':>8} {'DD':>5} | "
          f"{'2026 avg':>8} {'2026 acct':>9}")
    for label, kw in VARIANTS.items():
        trades = []
        for tk, ser in series.items():
            allow = (lambda tk: (lambda side, when: added.get(tk, '0000') <= when.date().isoformat()))(tk)
            for t in simulate_dip(ser, 2, start, ticker=tk, allow=allow, **kw):
                if consistent(t, ranges):
                    trades.append(t)
        full = describe(trades, closes, sessions)
        oos = describe([t for t in trades if t['entryTime'][:10] >= SPLIT], closes, sessions)
        f = full
        print(f"{label:40} {f['n']:6} {f['target']:8.0%} {f['stop']:7.0%} {f['time']:6.0%} {f['open']:5.0%} "
              f"{f['avg']:+7.2%} {f['median']:+7.2%} {f['days']:5.0f} "
              f"{(f['openAvg'] if f['openAvg'] is not None else 0):+8.1%} | {f['acct']:+8.0%} {f['dd']:5.0%} | "
              f"{oos['avg'] if oos else 0:+8.2%} {oos['acct'] if oos else 0:+9.0%}", flush=True)
    first = '2023-11-08'
    for b in ('SPY', 'QQQ'):
        full = curve_stats([c for d, c in bench[b] if d >= first])
        oos = curve_stats([c for d, c in bench[b] if d >= SPLIT])
        print(f"{'buy & hold ' + b:40} {'':>83} | {full['total']:+8.0%} {full['maxDD']:5.0%} | {'':>8} {oos['total']:+9.0%}")


if __name__ == '__main__':
    main()

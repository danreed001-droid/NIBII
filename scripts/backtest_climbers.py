#!/usr/bin/env python3
"""Rank-climbers backtest (mtl.momentum.run_rank_climbers): rank the S&P 500
weekly by trailing performance, and hold 10 stocks chosen from the top
100 by how much their rank IMPROVED since last week - vs the plain
"top 10 strongest" portfolio, SPY and QQQ. From 2020, a stock only once it
was in the index, 0.05% trading cost, 2025-26 as the check.

Reuses the price cache from scripts/backtest_variants.py.

Usage:
    python scripts/backtest_climbers.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_momentum import BROKEN, SPLIT, START, stats  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum, run_rank_climbers  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

SCORES = {'6-1m': (126, 21), '3m': (63, 0)}
VERSIONS = {
    'A. sell rank drops, refill with climbers': dict(mode='decliners'),
    'B. swap worst 5 for top 5 climbers': dict(mode='swap', swap=5),
    'C. A, max 5 new buys a week': dict(mode='decliners', max_new=5),
}


def row(label, r):
    full, ins, out = stats(r['curve'])
    print(f"{label:52} {full['total']:+7.0%} {full['annual'] or 0:+6.0%} {full['maxDD']:6.0%} | "
          f"{ins['total']:+7.0%} {ins['maxDD']:5.0%} | {out['total']:+7.0%} {out['maxDD']:5.0%} | {r['turnover']:5.1f}x",
          flush=True)


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    tickers = [t for t in names if t not in ETFS and t not in BROKEN]
    prices = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in tickers if raw[t].get('daily')}
    prices['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    added = load_added()

    def member(t, d):
        return added.get(t, '0000') <= d

    print(f"{'version (from 2020)':52} {'total':>7} {'CAGR':>6} {'maxDD':>6} | {'2020-24':>7} {'DD':>5} | "
          f"{'2025-26':>7} {'DD':>5} | turn/yr")
    for sname, (look, skip) in SCORES.items():
        print(f"-- ranked by {sname} performance --")
        for label, kw in VERSIONS.items():
            row(f"{label} ({sname})", run_rank_climbers(prices, calendar, START, look=look, skip=skip,
                                                         eligible=member, **kw))
        row(f"plain top 10 strongest ({sname})", run_momentum(prices, calendar, START, look=look, skip=skip,
                                                              top_n=10, eligible=member))
    for b in ('SPY', 'QQQ'):
        pts = [p for p in bench[b] if p[0] >= START]
        f = curve_stats([c for _, c in pts])
        i = curve_stats([c for d, c in pts if d < SPLIT])
        o = curve_stats([c for d, c in pts if d >= SPLIT])
        print(f"{'buy & hold ' + b:52} {f['total']:+7.0%} {f['annual']:+6.0%} {f['maxDD']:6.0%} | "
              f"{i['total']:+7.0%} {i['maxDD']:5.0%} | {o['total']:+7.0%} {o['maxDD']:5.0%}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Searches for a strength-window "sweet spot": the top-5 rule with every
lookback from 1 to 12 months, each with and without skipping the latest
month, on S&P 500 + Nasdaq-100 and on the fair S&P 500-only universe,
since 2020 (2020-24 vs 2025-26 shown separately so a lucky winner stands out).

Usage:
    python scripts/backtest_lookback_grid.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

START, SPLIT, MONTH = '2020-01-02', '2025-01-01', 21


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    base['SPY'] = dict(bench['SPY'])
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]

    def eligible(t, d):
        return t in extra or added.get(t, '0000') <= d

    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, since 2020 ==")
        print(f"{'window':24} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} | {'2025-26':>8}")
        for skip in (0, MONTH):
            for m in range(1, 13):
                if skip and m == 1:
                    continue
                r = run_momentum(prices, calendar, START, look=m * MONTH, skip=skip, top_n=5, eligible=eligible)
                c = r['curve']
                f = curve_stats([p[1] for p in c])
                i = curve_stats([p[1] for p in c if p[0] < SPLIT])
                o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
                label = f"{m:2} months" + (", skip latest" if skip else "")
                print(f"{label:24} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} | {o['total']:+8.0%}",
                      flush=True)
    for b in ('SPY', 'QQQ'):
        pts = [[d, c] for d, c in bench[b] if d >= START]
        f = curve_stats([c for _, c in pts])
        print(f"buy & hold {b}: {f['total']:+.0%} total, {f['annual']:+.0%} a year, worst drop {f['maxDD']:.0%}")


if __name__ == '__main__':
    main()

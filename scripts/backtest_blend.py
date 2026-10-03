#!/usr/bin/env python3
"""Blended strength score vs single windows for the top-5 rule, since 2020.

Blend = 6, 7, 8, 9 and 10-month returns, combined either by average rank
(each window counts equally) or average return. Compared with the
dashboard's current 6-months-skip-latest and the best single window (8
months), on S&P 500 + Nasdaq-100 and the fair S&P 500-only universe, with
years.

Usage:
    python scripts/backtest_blend.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

START, SPLIT, M = '2020-01-02', '2025-01-01', 21
BLEND = [(m * M, 0) for m in (6, 7, 8, 9, 10)]
VARIANTS = {
    '6 months, skip latest (current)': dict(look=126, skip=21),
    '8 months': dict(look=8 * M, skip=0),
    'BLEND 6-10 months, average rank': dict(windows=BLEND, blend='rank'),
    'blend 6-10 months, average return': dict(windows=BLEND, blend='mean'),
}


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

    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, since 2020 ==")
        print(f"{'score':36} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} | {'2025-26':>8} | turn/yr")
        for label, kw in VARIANTS.items():
            r = run_momentum(prices, calendar, START, top_n=5, eligible=eligible, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            curves[(uni, label)] = [p[:2] for p in c]
            print(f"{label:36} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} | "
                  f"{o['total']:+8.0%} | {r['turnover']:5.1f}x", flush=True)
    for b in ('SPY', 'QQQ'):
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
        f = curve_stats([c for d, c in bench[b] if d >= START])
        print(f"buy & hold {b}: {f['total']:+.0%}, {f['annual']:+.0%} a year, worst drop {f['maxDD']:.0%}")

    keys = [('S&P 500 + Nasdaq-100', k) for k in VARIANTS] + ['SPY', 'QQQ']
    heads = ['6m skip', '8m', 'blend rank', 'blend ret', 'SPY', 'QQQ']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>12}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+12.0%}" for k in keys))


if __name__ == '__main__':
    main()

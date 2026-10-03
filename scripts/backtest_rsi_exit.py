#!/usr/bin/env python3
"""RSI exit for the top-5 rule, since 2020: sell a holding the day its daily
RSI(14) closes below a level (35 / 40 / 45), replace it at once with the
best-ranked qualifying stock whose RSI is not below the level, and bar the
sold stock for 4 weeks (or 1 week, or no bar - it can come back as soon as
its RSI recovers and it still ranks).

Each vs the current rule on S&P 500 + Nasdaq-100 and the fair S&P-only
universe, with the Feb-Apr 2025 crash and the Jun-Jul 2026 theme crash.

Usage:
    python scripts/backtest_rsi_exit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import SPLIT, START, WINDOWS, window_return  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

VARIANTS = {
    'current (no RSI exit)': {},
    'RSI < 40, bar 4 weeks': dict(rsi_exit=40, cooldown=20),
    'RSI < 40, bar 1 week': dict(rsi_exit=40, cooldown=5),
    'RSI < 40, no bar': dict(rsi_exit=40, cooldown=0),
    'RSI < 35, bar 4 weeks': dict(rsi_exit=35, cooldown=20),
    'RSI < 45, bar 4 weeks': dict(rsi_exit=45, cooldown=20),
}


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]
    base['SPY'] = dict(bench['SPY'])
    comb['SPY'] = dict(bench['SPY'])

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, since 2020 ==")
        print(f"{'exit rule':28} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} {'2025-26':>8} | "
              + ' | '.join(f"{w:>15}" for w in WINDOWS) + " | exits/yr")
        for label, kw in VARIANTS.items():
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=member, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            curves[(uni, label)] = [p[:2] for p in c]
            ws = ' | '.join(f"{window_return(c, a, b):+15.1%}" for a, b in WINDOWS.values())
            print(f"{label:28} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} "
                  f"{o['total']:+8.0%} | {ws} | {r['stops'] / (len(c) / 252):8.0f}", flush=True)
    for b in ('SPY', 'QQQ'):
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
        f = curve_stats([c for d, c in bench[b] if d >= START])
        ws = ' | '.join(f"{window_return(curves[b], a, bb):+15.1%}" for a, bb in WINDOWS.values())
        print(f"{'buy & hold ' + b:28} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {'':>17} | {ws}")
    keys = [('S&P 500 + Nasdaq-100', k) for k in VARIANTS] + ['SPY', 'QQQ']
    heads = ['current', 'R40 4wk', 'R40 1wk', 'R40 none', 'R35 4wk', 'R45 4wk', 'SPY', 'QQQ']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>10}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+10.0%}" for k in keys))


if __name__ == '__main__':
    main()

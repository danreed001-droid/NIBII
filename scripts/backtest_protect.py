#!/usr/bin/env python3
"""Drawdown protection for the top-5 rule, since 2020:

  - breadth exit (90% of stocks down over 2 weeks) with a faster re-entry
    (below 85% with no wait, or a 2-day wait)
  - per-stock trailing stop (15/20/25% below the highest close since buying;
    the stopped stock is barred for 4 weeks, replaced at once)
  - industry cap (at most 2 of the 5 from one industry, data/industries.csv)
  - cap + 20% stop

Each vs the current rule on S&P 500 + Nasdaq-100 and the fair S&P-only
universe, with the Feb-Apr 2025 crash and the Jun-Jul 2026 theme crash.

Usage:
    python scripts/backtest_protect.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_breadth import breadth_series, risk_states  # noqa: E402
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START, SPLIT = '2020-01-02', '2025-01-01'
WINDOWS = {"Feb19-Apr9 '25": ('2025-02-19', '2025-04-09'), "Jun22-Jul29 '26": ('2026-06-22', '2026-07-29')}


def window_return(curve, a, b):
    pts = [p[1] for p in curve if a <= p[0] <= b]
    return pts[-1] / pts[0] - 1 if pts else None


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    with open(os.path.join(ROOT, 'data', 'industries.csv'), newline='') as f:
        industry = {r['symbol']: r['industry'] for r in csv.DictReader(f)}
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    print("computing breadth...", file=sys.stderr)
    breadth = breadth_series(comb, calendar, member)
    fast0 = risk_states(calendar, breadth, 0.90, 0.85, wait=0)
    fast2 = risk_states(calendar, breadth, 0.90, 0.85, wait=2)
    week = risk_states(calendar, breadth, 0.90, 0.85, wait=5)
    base['SPY'] = dict(bench['SPY'])
    comb['SPY'] = dict(bench['SPY'])

    def breadth_kw(st):
        return dict(risk_on=lambda d: st.get(d, True), risk_daily=True)

    variants = {
        'current (no protection)': {},
        'breadth 90/85, wait 1 week (last test)': breadth_kw(week),
        'breadth 90/85, no wait': breadth_kw(fast0),
        'breadth 90/85, wait 2 days': breadth_kw(fast2),
        'trailing stop 15%': dict(trail_stop=0.15),
        'trailing stop 20%': dict(trail_stop=0.20),
        'trailing stop 25%': dict(trail_stop=0.25),
        'industry cap 2': dict(group_of=industry, max_per_group=2),
        'industry cap 2 + stop 20%': dict(group_of=industry, max_per_group=2, trail_stop=0.20),
    }
    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, since 2020 ==")
        print(f"{'protection':40} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} {'2025-26':>8} | "
              + ' | '.join(f"{w:>15}" for w in WINDOWS) + " | stops")
        for label, kw in variants.items():
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=member, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            curves[(uni, label)] = [p[:2] for p in c]
            ws = ' | '.join(f"{window_return(c, a, b):+15.1%}" for a, b in WINDOWS.values())
            print(f"{label:40} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} "
                  f"{o['total']:+8.0%} | {ws} | {r['stops']:5}", flush=True)
    for b in ('SPY', 'QQQ'):
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
        f = curve_stats([c for d, c in bench[b] if d >= START])
        ws = ' | '.join(f"{window_return(curves[b], a, bb):+15.1%}" for a, bb in WINDOWS.values())
        print(f"{'buy & hold ' + b:40} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {'':>17} | {ws}")
    keys = [('S&P 500 + Nasdaq-100', k) for k in ('current (no protection)', 'breadth 90/85, no wait',
                                                   'trailing stop 20%', 'industry cap 2', 'industry cap 2 + stop 20%')]
    heads = ['current', 'breadth fast', 'stop 20%', 'cap 2', 'cap2+stop20']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>13}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+13.0%}" for k in keys))


if __name__ == '__main__':
    main()

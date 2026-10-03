#!/usr/bin/env python3
"""Close a holding when its daily chart turns into a lower-low downtrend and buy
the next-best ranked stock that isn't in one, since 2020, S&P 500 + Nasdaq-100.

Downtrend = the same read as the dashboard's D arrow (uptrend = last two swings HH/HL) and the auto mix: 3-bar
swings, the last two labeled swings both LH/LL, using only data up to that
close. Checked every session or only at the Friday signal; trades at the next
close (Monday for the weekly signal), like the live page. A sold stock can come
back as soon as its chart stops reading down (or after a 4-week bar).

Usage:
    python scripts/backtest_lolo_exit.py
"""
import os
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_drawdown import row  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START, WINDOWS  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    bars = {t: [(b[0][:10],) + tuple(b[1:5]) for b in raw[t]['daily']] for t in sp}
    bars.update({t: [(b[0][:10],) + tuple(b[1:5]) for b in bs] for t, bs in extra.items()})
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    prices['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    dates = {t: [b[0] for b in bs] for t, bs in bars.items()}
    cache = {}

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    def state(t, k):
        d = calendar[k]
        if (t, d) not in cache:
            j = bisect_right(dates[t], d)
            cache[(t, d)] = structure_signal(bars[t][max(0, j - 320):j], n=3, lookback=2)['state']
        return cache[(t, d)]

    def down(t, k):
        return state(t, k) == 'downtrend'

    def up(t, k):
        return state(t, k) == 'uptrend'

    def run(**kw):
        return run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close', **kw)

    variants = {
        'current (no lower-low exit)': {},
        'exit daily, can come straight back': dict(exit_when=down, exit_daily=True, cooldown=0),
        'exit daily, barred 4 weeks': dict(exit_when=down, exit_daily=True, cooldown=20),
        'exit at Friday check, straight back': dict(exit_when=down, exit_daily=False, cooldown=0),
        'exit at Friday check, barred 4 weeks': dict(exit_when=down, exit_daily=False, cooldown=20),
        'exit daily, replace with UPTREND only': dict(exit_when=down, exit_daily=True, cooldown=0, buy_when=up),
        'exit Friday, replace with UPTREND only': dict(exit_when=down, exit_daily=False, cooldown=0, buy_when=up),
        'no exit, buy only UPTREND stocks': dict(buy_when=up),
    }
    print(f"{'top 5, 100% stocks':38} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | "
          + ' | '.join(f"{w:>15}" for w in WINDOWS) + " | exits/yr")
    curves = {}
    for label, kw in variants.items():
        print(f"running: {label}", file=sys.stderr, flush=True)
        r = run(**kw)
        c = [p[:2] for p in r['curve']]
        curves[label] = c
        sys.stdout.write(f"{label[:38]:38} ")
        row('', c)
        print(f"{'':38} exits a year: {r['stops'] / (len(c) / 252):.0f}")
    keys = list(curves)
    years = {k: yearly(curves[k]) for k in keys}
    heads = ['current', 'daily/back', 'daily/4wk', 'Fri/back', 'Fri/4wk', 'daily/up', 'Fri/up', 'buy up']
    print(f"\nyear by year\n{'year':6}" + ''.join(f"{h:>12}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+12.0%}" for k in keys))


if __name__ == '__main__':
    main()

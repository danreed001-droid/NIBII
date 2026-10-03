#!/usr/bin/env python3
"""Auto mix with the defensive part in cash instead of the best-of sleeve,
since 2020: 100% invested in the top 5 normally; when holdings are in daily
lower-low downtrends at Friday's close, only part stays invested and the rest
sits in cash (T-bill ETF BIL, or 0% cash) until a Friday says otherwise.

  2+ down -> 60% invested
  2+ down -> 80% invested
  tiers   -> 1 down: 80%, 2+ down: 60%
  tiers   -> 1 down: 80%, 2 down: 60%, 3+ down: 40%

Each with cash vs with the sleeve, against the live page's auto mix.

Usage:
    python scripts/backtest_cash_mix.py
"""
import os
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_drawdown import row  # noqa: E402
from backtest_hedge import load_assets  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START, WINDOWS  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.sleeve import filled, plan_curve_dynamic, sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

EXTRA_WINDOWS = {"Jan15-Mar31 '20": ('2020-01-15', '2020-03-31'), "Feb18-Apr9 '25": ('2025-02-18', '2025-04-09')}


def window(c, a, b):
    pts = [v for d, v in c if a <= d <= b]
    return pts[-1] / pts[0] - 1


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    bars = {t: [(b[0][:10],) + tuple(b[1:5]) for b in raw[t]['daily']] for t in sp}
    bars.update({t: [(b[0][:10],) + tuple(b[1:5]) for b in bs] for t, bs in extra.items()})
    comb = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    comb['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    dates = {t: [b[0] for b in bs] for t, bs in bars.items()}
    assets = load_assets()
    sl, _ = sleeve_curve(assets, calendar, START)
    bil = filled({'BIL': assets['BIL']}, calendar)['BIL']
    tbills = [[d, bil[d]] for d in calendar if d >= START]
    zero = [[d, 1.0] for d in calendar if d >= START]

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    r = run_momentum(comb, calendar, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    top5 = [p[:2] for p in r['curve']]
    pdays = [p[0] for p in r['picks']]
    cache = {}

    def downs(d):
        if d not in cache:
            i = bisect_right(pdays, d)
            held = r['picks'][i - 1][1] if i else []
            n = 0
            for t in held:
                j = bisect_right(dates[t], d)
                n += structure_signal(bars[t][max(0, j - 320):j], n=3, lookback=2)['state'] == 'downtrend'
            cache[d] = n
        return cache[d]

    rules = {
        '2+ down -> 60% invested': lambda d: 0.6 if downs(d) >= 2 else 1.0,
        '2+ down -> 80% invested': lambda d: 0.8 if downs(d) >= 2 else 1.0,
        'tiers 1:80% 2+:60%': lambda d: 0.6 if downs(d) >= 2 else 0.8 if downs(d) == 1 else 1.0,
        'tiers 1:80% 2:60% 3+:40%': lambda d: (0.4 if downs(d) >= 3 else 0.6 if downs(d) == 2
                                               else 0.8 if downs(d) == 1 else 1.0),
    }
    rest = {'sleeve': sl, 'cash (T-bills)': tbills, 'cash (0%)': zero}
    allw = dict(WINDOWS)
    allw.update(EXTRA_WINDOWS)
    print(f"{'rule / where the rest goes':44} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | "
          + ' | '.join(f"{w:>15}" for w in allw))
    curves = {}

    def line(label, c):
        from mtl.backtest import curve_stats
        f = curve_stats([p[1] for p in c])
        ws = ' | '.join(f"{window(c, a, b):+15.1%}" for a, b in allw.values())
        print(f"{label:44} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} {f['annual'] / -f['maxDD']:6.2f} | {ws}",
              flush=True)

    line('always 100% top 5', top5)
    for rl, fn in rules.items():
        for where, other in rest.items():
            c = plan_curve_dynamic(top5, other, calendar, fn)
            curves[(rl, where)] = c
            line(f"{rl}, rest in {where}", c)
    for b in ('SPY', 'QQQ'):
        line('buy & hold ' + b, [[d, v] for d, v in bench[b] if d >= START])
    keys = [('2+ down -> 60% invested', 'sleeve'), ('2+ down -> 60% invested', 'cash (T-bills)'),
            ('tiers 1:80% 2+:60%', 'sleeve'), ('tiers 1:80% 2+:60%', 'cash (T-bills)')]
    heads = ['60 sleeve*', '60 cash', 'tier sleeve', 'tier cash']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nyear by year (* = live page)\n{'year':6}" + ''.join(f"{h:>13}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+13.0%}" for k in keys))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""More profit AND less drawdown: lever up the top-5 + best-of sleeve mix.

The 70/30 mix of the top-5 rule and the best-of sleeve (scripts/backtest_hedge.py)
earns more per point of drawdown than the top 5 alone, so a little leverage
can lift its return above the top 5's while its drawdown stays smaller.

Leverage L: L x (share in top 5, the rest in the sleeve), rebalanced weekly;
the borrowed (L - 1) pays `RATE` a year (a typical margin rate), charged daily.
Also the "overlay" form: 100% top 5 plus X% sleeve on top.

Usage:
    python scripts/backtest_leverage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_drawdown import row  # noqa: E402
from backtest_hedge import load_assets, sleeve  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START, WINDOWS  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

RATES = (0.06, 0.08)


def run(curve, other, w_main, w_other, calendar, rate):
    """Weekly-rebalanced w_main in curve + w_other in other {date: value}; anything
    above 100% of the account is borrowed at `rate` a year (holdings and debt in dollars)."""
    rebal = set(last_sessions_of_weeks(calendar))
    nav = 1.0
    a, b, debt = nav * w_main, nav * w_other, nav * max(0.0, w_main + w_other - 1)
    out, prev = [], None
    for d, v in curve:
        if prev:
            a *= v / prev[0]
            b *= other[d] / prev[1]
            debt *= 1 + rate / 252
            nav = a + b - debt
            if nav <= 0:
                out.append([d, 1e-9])
                break
        out.append([d, nav])
        prev = (v, other[d])
        if d in rebal:
            a, b, debt = nav * w_main, nav * w_other, nav * max(0.0, w_main + w_other - 1)
    return out


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    px = load_assets()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    comb = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    comb['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    def best_of(k, f):
        def r6(t):
            a, b = f[t][calendar[max(0, k - 126)]], f[t][calendar[k]]
            return b / a - 1 if a and b else -1
        return {max(['GLD', 'TLT', 'IEF', 'UUP', 'DBC', 'BIL'], key=r6): 1.0}

    sl = sleeve(px, calendar, best_of)
    top5 = [p[:2] for p in run_momentum(comb, calendar, START, look=126, skip=21, top_n=5,
                                        eligible=member)['curve']]
    curves = {}
    for rate in RATES:
        print(f"\n== borrowing at {rate:.0%} a year ==")
        print(f"{'mix':34} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | "
              + ' | '.join(f"{w:>15}" for w in WINDOWS))
        plans = [('top 5 alone (today)', 1.0, 0.0)]
        for lev in (1.0, 1.2, 1.3, 1.4, 1.5):
            plans.append((f'70/30 mix x{lev:.1f}', 0.7 * lev, 0.3 * lev))
        for lev in (1.3, 1.5, 1.7):
            plans.append((f'60/40 mix x{lev:.1f}', 0.6 * lev, 0.4 * lev))
        for extra_w in (0.3, 0.5):
            plans.append((f'overlay: 100% top 5 + {extra_w:.0%} sleeve', 1.0, extra_w))
        for label, wm, wo in plans:
            c = run(top5, sl, wm, wo, calendar, rate)
            curves[(rate, label)] = c
            row(label, c)
    row('buy & hold QQQ', [[d, v] for d, v in bench['QQQ'] if d >= START])
    keys = [(RATES[0], k) for k in ('top 5 alone (today)', '70/30 mix x1.0', '70/30 mix x1.3',
                                    '60/40 mix x1.5', 'overlay: 100% top 5 + 30% sleeve')]
    heads = ['top 5', '70/30', '70/30 x1.3', '60/40 x1.5', 'overlay 30%']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nyear by year (borrowing at {RATES[0]:.0%})\n{'year':6}" + ''.join(f"{h:>13}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+13.0%}" for k in keys))


if __name__ == '__main__':
    main()

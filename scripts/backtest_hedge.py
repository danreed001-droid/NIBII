#!/usr/bin/env python3
"""Top 5 Strongest paired with a gold / bonds sleeve, since 2020.

Sleeves (dividend-adjusted ETF prices, decided at each Friday close; cash
earns the T-bill ETF BIL):
  static     - 50% GLD / 50% TLT, always held
  trend      - GLD and TLT, each held only while above its 200-day average
               (otherwise that half sits in BIL)
  trend 5    - same idea across GLD, TLT, IEF, UUP (US dollar), DBC
               (commodities): each a fifth, held only above its 200-day average
  best of    - all in whichever of GLD / TLT / IEF / UUP / DBC / BIL has the
               best 6-month return (BIL when none beats cash)

Each sleeve mixed with the top-5 rule (S&P 500 + Nasdaq-100) at 70/30, 60/40
and 50/50, rebalanced weekly; plus each piece alone and QQQ/SPY.

Usage:
    python scripts/backtest_hedge.py
"""
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_drawdown import mix, row  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START, WINDOWS  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from momentum_scan import fetch  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.hedge.pkl')
ASSETS = ['GLD', 'TLT', 'IEF', 'UUP', 'DBC', 'BIL']


def load_assets():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    bars = fetch(ASSETS, start='2018-06-01', adjusted=True)
    out = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    with open(CACHE, 'wb') as f:
        pickle.dump(out, f)
    return out


def sleeve(px, calendar, choose):
    """Daily curve of a sleeve whose weights {asset: w} are set by choose(k) at
    each week-end close (weights sum to 1; the rest is put in BIL)."""
    rebal = set(last_sessions_of_weeks(calendar))
    filled = {}
    for t, s in px.items():   # carry prices over missing sessions
        last, f = None, {}
        for d in calendar:
            last = s.get(d) or last
            f[d] = last
        filled[t] = f
    w, val, out = None, 1.0, {}
    for k, d in enumerate(calendar):
        if d < START:
            if d in rebal:
                w = choose(k, filled)
            continue
        if w is None:
            w = choose(k, filled)
        elif k:
            p = calendar[k - 1]
            val *= 1 + sum(x * (filled[t][d] / filled[t][p] - 1) for t, x in w.items())
        out[d] = val
        if d in rebal:
            w = choose(k, filled)
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

    def above_ma(t, k, f, n=200):
        xs = [f[t][calendar[i]] for i in range(max(0, k - n + 1), k + 1) if f[t][calendar[i]]]
        return len(xs) >= n * 0.9 and xs[-1] > sum(xs) / len(xs)

    def trend(assets):
        def choose(k, f):
            w = {t: 1 / len(assets) for t in assets if above_ma(t, k, f)}
            w['BIL'] = 1 - sum(w.values())
            return w
        return choose

    def best_of(k, f):
        def r6(t):
            a, b = f[t][calendar[max(0, k - 126)]], f[t][calendar[k]]
            return b / a - 1 if a and b else -1
        best = max(['GLD', 'TLT', 'IEF', 'UUP', 'DBC', 'BIL'], key=r6)
        return {best: 1.0}

    sleeves = {
        'static GLD/TLT': sleeve(px, calendar, lambda k, f: {'GLD': 0.5, 'TLT': 0.5}),
        'trend GLD/TLT': sleeve(px, calendar, trend(['GLD', 'TLT'])),
        'trend 5 assets': sleeve(px, calendar, trend(['GLD', 'TLT', 'IEF', 'UUP', 'DBC'])),
        'best-of 6m': sleeve(px, calendar, best_of),
    }
    r = run_momentum(comb, calendar, START, look=126, skip=21, top_n=5, eligible=member)
    top5 = [p[:2] for p in r['curve']]
    weekly = [d for d in last_sessions_of_weeks(calendar) if d >= START]
    t5 = dict(top5)

    def wret(s):
        return [s[b] / s[a] - 1 for a, b in zip(weekly, weekly[1:])]

    def corr(a, b):
        n = len(a)
        ma, mb = sum(a) / n, sum(b) / n
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        return cov / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5

    print(f"\n{'mix (weekly rebalanced)':30} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | "
          f"{'2020-24':>8} {'2025-26':>8} | " + ' | '.join(f"{w:>15}" for w in WINDOWS))
    row('top 5 alone', top5)
    curves = {'top 5 alone': top5}
    for name, s in sleeves.items():
        print(f"-- {name}: weekly correlation with top 5 {corr(wret(t5), wret(s)):+.2f}")
        row(f'  {name} alone', [[d, v] for d, v in s.items()])
        for share in (0.7, 0.6, 0.5):
            c = mix(top5, s, share, calendar)
            label = f"  {share:.0%} top 5 / {1 - share:.0%} {name.split()[0]}"
            curves[(name, share)] = c
            row(label, c)
    for b in ('SPY', 'QQQ'):
        row('buy & hold ' + b, [[d, v] for d, v in bench[b] if d >= START])
    keys = ['top 5 alone'] + [(n, 0.6) for n in sleeves]
    heads = ['top 5', '60/40 stat', '60/40 trnd', '60/40 tr5', '60/40 best']
    years = {k: yearly(curves[k]) for k in keys}
    sl = {n: yearly([[d, v] for d, v in s.items()]) for n, s in sleeves.items()}
    print(f"\nyear by year\n{'year':6}" + ''.join(f"{h:>12}" for h in heads)
          + ''.join(f"{'(' + n.split()[0] + ')':>12}" for n in sleeves))
    for y in sorted(years['top 5 alone']):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+12.0%}" for k in keys)
              + ''.join(f"{sl[n].get(y, 0):+12.0%}" for n in sleeves))


if __name__ == '__main__':
    main()

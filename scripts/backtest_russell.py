#!/usr/bin/env python3
"""Top-5 strongest, weekly, from S&P 500 + Nasdaq-100 + Russell 2000.

Russell 2000 members come from data/russell2000_snapshot.csv (a public
GitHub snapshot from roughly 2023-24); Yahoo still has prices for about
1,255 of them that aren't already in the other two lists. Small caps get
safety filters, all checked with data up to the rank date only:
  - price >= $5 (no penny stocks)
  - 20-day average dollar volume >= $10M (tradable)
  - no one-day move above +200% or below -80% in the scoring window
    (reverse-split glitches and data errors)
Caveats: the snapshot is a later list applied back to 2020 (hindsight),
and companies acquired or delisted since are missing (survivorship).

Usage:
    python scripts/backtest_russell.py
"""
import collections
import os
import pickle
import sys
from bisect import bisect_left

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2K_CACHE = os.path.join(ROOT, 'data', '.r2k.pkl')
MIN_PRICE, MIN_DOLLAR_VOL, LOOK, SKIP = 5.0, 10e6, 126, 21


def tradable_map(bars):
    """{date: True} where the small-cap filters pass using data through that date."""
    out, closes = {}, [c for _, c, _ in bars]
    dv = [c * v for _, c, v in bars]
    jump = [False] + [closes[i - 1] > 0 and not (-0.8 <= closes[i] / closes[i - 1] - 1 <= 2.0)
                      for i in range(1, len(closes))]
    last_jump = -10 ** 9
    for i, (d, c, _) in enumerate(bars):
        if jump[i]:
            last_jump = i
        avg_dv = sum(dv[max(0, i - 19):i + 1]) / min(20, i + 1)
        out[d] = c >= MIN_PRICE and avg_dv >= MIN_DOLLAR_VOL and i - last_jump > LOOK
    return out


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    with open(R2K_CACHE, 'rb') as f:
        r2k = pickle.load(f)
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    base.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    base['SPY'] = dict(bench['SPY'])
    small = {t: {d: c for d, c, _ in bars} for t, bars in r2k.items()}
    ok = {t: tradable_map(bars) for t, bars in r2k.items()}
    calendar = [d for d, _ in bench['SPY']]

    def eligible(t, d):
        if t in ok:
            return ok[t].get(d, False)
        return t in extra or added.get(t, '0000') <= d

    runs = {}
    print(f"{'top 5, 6-month strength, from 2020':40} {'total':>7} {'CAGR':>5} {'maxDD':>6}")
    for label, prices in (('S&P 500 + Nasdaq-100', base), ('+ Russell 2000', {**base, **small})):
        r = run_momentum(prices, calendar, '2020-01-02', look=LOOK, skip=SKIP, top_n=5, eligible=eligible)
        runs[label] = (r, prices)
        s = curve_stats([p[1] for p in r['curve']])
        print(f"{label:40} {s['total']:+7.0%} {s['annual']:+5.0%} {s['maxDD']:6.0%}")
    for b in ('SPY', 'QQQ'):
        s = curve_stats([c for d, c in bench[b] if d >= '2020-01-02'])
        print(f"{'buy & hold ' + b:40} {s['total']:+7.0%} {s['annual']:+5.0%} {s['maxDD']:6.0%}")

    cols = [(k, [p[:2] for p in r['curve']]) for k, (r, _) in runs.items()]
    cols += [(b, [[d, c] for d, c in bench[b] if d >= '2019-12-31']) for b in ('SPY', 'QQQ')]
    years = {n: yearly(p) for n, p in cols}
    print(f"\n{'year':6}" + ''.join(f"{n:>22}" for n, _ in cols))
    for y in sorted(years[cols[0][0]]):
        print(f"{y:6}" + ''.join(f"{years[n].get(y, 0):+22.0%}" for n, _ in cols))

    r, prices = runs['+ Russell 2000']
    val = {p[0]: p[1] for p in r['curve']}
    contrib, weeks = collections.Counter(), collections.Counter()
    for (d, h), (d2, _) in zip(r['picks'], r['picks'][1:]):
        for t in h:
            a, b = prices[t].get(d), prices[t].get(d2) or prices[t].get(d)
            contrib[t] += (b / a - 1) * val[d] / 5
            weeks[t] += 1
    tot = sum(contrib.values())
    sm = sum(v for t, v in contrib.items() if t in small)
    share = sum(weeks[t] for t in weeks if t in small) / max(1, sum(weeks.values()))
    print(f"\n+ Russell: total gain ${tot:,.0f}; from Russell 2000 stocks ${sm:,.0f} ({sm / tot:.0%}); "
          f"{share:.0%} of holding-weeks were Russell stocks")
    print("biggest contributors:")
    for t, v in contrib.most_common(12):
        tag = 'R2K' if t in small else ''
        print(f"  {t:6} {tag:4} ${v:8,.0f}  held {weeks[t]} weeks")
    print(f"holds as of {r['picks'][-1][0]}: {', '.join(r['picks'][-1][1])}")


if __name__ == '__main__':
    main()

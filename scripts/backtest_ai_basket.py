#!/usr/bin/env python3
"""The dashboard's rule, but only allowed to pick from a fixed list of 13 AI-theme stocks.

  big tech  MSFT GOOGL AMZN META
  chips     NVDA AMD AVGO
  power     CEG VST NEE
  miners    CIFR CORZ MARA     (bitcoin miners turned AI data-center hosts)

Same rule as the page: 6-month return skipping the last month, must beat SPY,
top 5 in equal weight (unfilled slots sit in cash), decided Friday, traded at
Monday's close, kept while ranked in the top 10 (with 13 names that is almost
always - so 'strict' keeps only the top 5). 'Boost' adds the page's news-gap
rule (a 12%+ gap on news in the last 4 weeks forces the stock in). A stock is
only eligible from its first trading day (CEG 2022, CORZ relisted 2024, ...).
Dividend-adjusted prices; 0.05% cost per trade; no tax.

Compared with SPY, QQQ, the 13 in equal weight (rebalanced monthly, each from
its first day) and the dashboard's current Auto / Boost (pre-tax, 2000-2026
audit curves, when available).

Part 2 - all stocks, but only these 13 get bought: the page rule runs on the
whole universe (S&P 500 with join dates + Nasdaq-100, plus the three miners);
each week's holdings that are on the list are held at 1/5 each, and a slot
taken by any other stock sits in cash. A list stock is kept while the page
rule keeps it (top 10).

Usage:
    python scripts/backtest_ai_basket.py [curves_dump.json]
"""
import json
import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_scan import LOOK, SKIP, fetch  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.news import booster, news_gap_days  # noqa: E402

BASKET = ['MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'AMD', 'AVGO', 'CEG', 'VST', 'NEE', 'CIFR', 'CORZ', 'MARA']
WINDOWS = [('2015-01-02', 'since 2015'), ('2020-01-02', 'since 2020'), ('2023-01-03', 'since 2023'), (None, 'last 12 months')]


def stats(curve, lo):
    """curve: [(date, value)] -> (per year, worst drop, Sharpe, $100k grows to) from `lo` on."""
    c = [(d, v) for d, v in curve if d >= lo]
    if len(c) < 10:
        return None
    v = [x[1] for x in c]
    yrs = (date.fromisoformat(c[-1][0]) - date.fromisoformat(c[0][0])).days / 365.25
    per = (len(v) - 1) / yrs
    r = [v[i] / v[i - 1] - 1 for i in range(1, len(v))]
    m = sum(r) / len(r)
    sd = (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5
    peak, dd = v[0], 0.0
    for x in v:
        peak = max(peak, x)
        dd = min(dd, x / peak - 1)
    return (v[-1] / v[0]) ** (1 / yrs) - 1, dd, m / sd * math.sqrt(per) if sd else 0, 100000 * v[-1] / v[0]


def main():
    bars = fetch(BASKET + ['SPY', 'QQQ'], start='2013-06-01', adjusted=True)
    cal = [b[0] for b in bars['SPY']]
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    first = {t: bs[0][0] for t, bs in bars.items() if bs}
    print("first trading day in the data: " + ', '.join(f"{t} {first.get(t, 'none')}" for t in BASKET))

    def eligible(t, d):
        return t in BASKET and t in first and first[t] <= d
    start = '2015-01-02'
    kw = dict(look=LOOK, skip=SKIP, top_n=5, eligible=eligible, exec_next='close')
    gaps = {t: news_gap_days(bars[t]) for t in BASKET if t in bars}
    runs = {
        'Basket top 5 (page rule)': run_momentum(prices, cal, start, **kw),
        'Basket top 5, strict (sell when out of top 5)': run_momentum(prices, cal, start, keep_rank=5, **kw),
        'Basket top 5 + Boost': run_momentum(prices, cal, start, prefer=booster(gaps, cal), prefer_mode='force',
                                             prefer_rank=None, prefer_pool='all', **kw),
    }
    curves = {k: [(p[0], p[1]) for p in r['curve']] for k, r in runs.items()}
    # the 13 in equal weight, rebalanced each month-end among those already trading
    v, held, ew = 1.0, {}, []
    for i, d in enumerate(cal):
        if d < start:
            continue
        if held:
            v = sum(n * prices[t].get(d, 0) or n * last[t] for t, n in held.items())
        ew.append((d, v))
        last = {t: prices[t].get(d) for t in BASKET if prices.get(t, {}).get(d)}
        if i + 1 == len(cal) or cal[i + 1][:7] != d[:7] or not held:
            live = [t for t in BASKET if t in last]
            held = {t: v / len(live) / last[t] for t in live}
    curves['The 13, equal weight'] = ew
    for b in ('SPY', 'QQQ'):
        curves[b] = [(d, prices[b][d]) for d in cal if d >= start and d in prices[b]]
    dump = sys.argv[1] if len(sys.argv) > 1 else None
    if dump and os.path.exists(dump):
        s = json.load(open(dump))['series']
        for key, lab in (('oldld_auto', 'Dashboard Auto (all S&P 500)'), ('oldld_boost', 'Dashboard Boost (all S&P 500)')):
            curves[lab] = [(d, x) for d, x in s[key]['pre']]

    last12 = cal[-253]
    for lo, lab in WINDOWS:
        lo = lo or last12
        print(f"\n=== {lab} (from {lo}) ===")
        print(f"{'':48} {'per year':>9} {'worst drop':>11} {'Sharpe':>7} {'$100k ->':>12}")
        for k, c in curves.items():
            s_ = stats(c, lo)
            if s_ is None:
                continue
            month = 'monthly' if 'Dashboard' in k else ''
            print(f"{k:48} {s_[0]:9.1%} {s_[1]:11.1%} {s_[2]:7.2f} {s_[3]:12,.0f} {month}")
    for k, r in runs.items():
        held_n = [len(p[1]) for p in r['picks'] if p[0] >= start]
        print(f"\n{k}: average holdings {sum(held_n) / len(held_n):.1f} of 5, turnover {r['turnover']:.1f}x a year")
        print("  holdings now: " + ', '.join(r['picks'][-1][1]))
    # time held per stock (page rule)
    days = {}
    picks = runs['Basket top 5 (page rule)']['picks']
    for (d0, h), (d1, _) in zip(picks, picks[1:] + [[cal[-1], []]]):
        n = sum(1 for d in cal if d0 <= d < d1)
        for t in h:
            days[t] = days.get(t, 0) + n
    tot = sum(1 for d in cal if d >= picks[0][0])
    print("\nshare of time held (page rule): " + ', '.join(f"{t} {days.get(t, 0) / tot:.0%}" for t in sorted(BASKET, key=lambda t: -days.get(t, 0))))

    all_stocks_filter(bars)


def all_stocks_filter(basket_bars):
    from backtest_long_history import load
    from momentum_scan import blocked_dates
    from mtl.universe import load_added, load_sp500
    D = load()
    bars = dict(D['bars'])
    for t in BASKET:
        if t not in bars or not bars[t]:
            bars[t] = basket_bars[t]
    sp, added = load_sp500(), load_added()
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in D['bench']['SPY']}
    cal = [b[0] for b in D['bench']['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t in BASKET or t not in sp or added.get(t, '0000') <= d)
    start = '2015-01-02'
    gaps = {t: news_gap_days(bs) for t, bs in bars.items() if bs}
    kw = dict(look=LOOK, skip=SKIP, top_n=5, eligible=eligible, exec_next='close')
    runs = {'Auto': run_momentum(prices, cal, start, **kw),
            'Boost': run_momentum(prices, cal, start, prefer=booster(gaps, cal), prefer_mode='force',
                                  prefer_rank=None, prefer_pool='all', **kw)}
    print("\n\n##### Part 2: all stocks ranked, only the 13 bought when they make the top 5 #####")
    for name, r in runs.items():
        picks = r['picks']
        pdays = [p[0] for p in picks]
        full = [(p[0], p[1]) for p in r['curve']]
        v, cur, out, slots, prev = 1.0, [], [], [], None
        j = 0
        for d in cal:
            if d < pdays[0]:
                continue
            if prev is not None and cur:
                v *= 1 + sum(0.2 * (prices[t].get(d, prices[t].get(prev)) / prices[t][prev] - 1)
                             for t in cur if prices[t].get(prev))
            while j < len(pdays) and pdays[j] <= d:
                cur = [t for t in picks[j][1] if t in BASKET]
                j += 1
            out.append((d, v))
            slots.append(len(cur))
            prev = d
        for lo, lab in WINDOWS:
            lo = lo or cal[-253]
            a, b = stats(full, lo), stats(out, lo)
            print(f"  {name:6} {lab:15} page rule, all stocks {a[0]:6.1%} (drop {a[1]:6.1%}, ${a[3]:>10,.0f})"
                  f"  |  only the 13 {b[0]:6.1%} (drop {b[1]:6.1%}, ${b[3]:>10,.0f})")
        print(f"  {name}: on average {sum(slots) / len(slots):.1f} of 5 slots held a list stock "
              f"({sum(1 for x in slots if x == 0) / len(slots):.0%} of days fully in cash)")
        tally = {}
        for p in picks:
            for t in p[1]:
                if t in BASKET:
                    tally[t] = tally.get(t, 0) + 1
        print("  list stocks that made the page's holdings (weeks): " + ', '.join(f"{t} {n}" for t, n in sorted(tally.items(), key=lambda x: -x[1])))
        print("  holdings now: " + ', '.join(picks[-1][1]))


if __name__ == '__main__':
    main()

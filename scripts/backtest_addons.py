#!/usr/bin/env python3
"""Add-ons to the top-5 rule from scripts/study_edges.py, 2000-2026.

Same rule as the dashboard (S&P 500 + Nasdaq-100 by 6-1 month strength, beat
SPY, top 5, keep while top 10, signal Friday, trade Monday's close). An add-on
only changes WHICH stock fills a slot: among the qualifying stocks ranked in
the top 20 (or 10), a flagged one jumps the queue.
  fill   flagged stocks take open slots first (holdings are kept as usual)
  force  a flagged stock also replaces the lowest-ranked holding when no slot is open

Flags (from daily bars):
  news gap   a day that opened 10%+ above the prior close and closed 10%+ up,
             in the upper part of its range (likely earnings / big news) -
             within the last week, or the last month (the drift lasts ~3 months)
  gap 5%     same at 5%+, closing near the high
  dip        a day down 5%+ within the last week (a leader on sale)

Long-history data of backtest_long_history.py (today's index lists).

Usage:
    python scripts/backtest_addons.py
    python scripts/backtest_addons.py --wide   # news gap from the top 10 / 20 / 50 / any stock beating SPY /
                                               # any stock at all, and news gaps alone with no ranking
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import START, load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    cal = [b[0] for b in bench['SPY']]
    pos = {d: i for i, d in enumerate(cal)}
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t not in sp or added.get(t, '0000') <= d)

    flags = {'gap10': {}, 'gap5': {}, 'dip': {}}
    for t, bs in bars.items():
        for j in range(1, len(bs)):
            d, o, h, lo, c = bs[j]
            pc = bs[j - 1][4]
            k = pos.get(d)
            if k is None or not pc or h <= lo:
                continue
            g, r, where = o / pc - 1, c / pc - 1, (c - lo) / (h - lo)
            if g >= 0.10 and r >= 0.10 and where >= 0.6:
                flags['gap10'].setdefault(t, set()).add(k)
            if g >= 0.05 and r >= 0.05 and where >= 0.75:
                flags['gap5'].setdefault(t, set()).add(k)
            if r <= -0.05:
                flags['dip'].setdefault(t, set()).add(k)

    def flagged(kind, window):
        f = flags[kind]
        return lambda t, k: any((k - w) in f.get(t, ()) for w in range(window))

    def either(a, b):
        return lambda t, k: a(t, k) or b(t, k)

    base = dict(look=126, skip=21, top_n=5, eligible=eligible, exec_next='close')
    if '--wide' in sys.argv:
        g = flagged('gap10', 21)
        variants = [('top 5 as is', {})]
        for mode in ('fill', 'force'):
            for lab, kw in (('top 10', dict(prefer_rank=10)), ('top 20', dict(prefer_rank=20)),
                            ('top 50', dict(prefer_rank=50)), ('any stock beating SPY', dict(prefer_rank=None)),
                            ('ANY stock, even weak', dict(prefer_rank=None, prefer_pool='all'))):
                variants.append((f"news gap, {lab}, {mode}", dict(prefer=g, prefer_mode=mode, **kw)))
        return report(variants, prices, cal, eligible, gap_only(flags['gap10'], prices, cal, eligible, pos))
    variants = [
        ('top 5 as is', {}),
        ('news gap this week, fill', dict(prefer=flagged('gap10', 5))),
        ('news gap last month, fill', dict(prefer=flagged('gap10', 21))),
        ('news gap last month, force', dict(prefer=flagged('gap10', 21), prefer_mode='force')),
        ('news gap last month, top 10 only, fill', dict(prefer=flagged('gap10', 21), prefer_rank=10)),
        ('gap 5% this week, fill', dict(prefer=flagged('gap5', 5))),
        ('gap 5% last month, fill', dict(prefer=flagged('gap5', 21))),
        ('dip this week, fill', dict(prefer=flagged('dip', 5))),
        ('dip this week, force', dict(prefer=flagged('dip', 5), prefer_mode='force')),
        ('dip this week, top 10 only, fill', dict(prefer=flagged('dip', 5), prefer_rank=10)),
        ('news gap last month OR dip this week, fill', dict(prefer=either(flagged('gap10', 21), flagged('dip', 5)))),
    ]
    report(variants, prices, cal, eligible)


def gap_only(gaps, prices, cal, eligible, pos, slots=5, hold=60):
    """No strength ranking at all: buy each news-gap stock at the next close (open slots only,
    newest gaps first), hold it `hold` sessions, `slots` equal slots, the rest in cash."""
    by_day = {}
    for t, ks in gaps.items():
        for k in ks:
            by_day.setdefault(k, []).append(t)
    start = pos[next(d for d in cal if d >= START)]
    cash, held, curve, last = 100.0, {}, [], {}
    for k in range(start, len(cal)):
        d = cal[k]
        for t in list(held):
            px = prices[t].get(d) or last.get(t)
            last[t] = px
            if k >= held[t][1]:
                cash += held[t][0] * px
                del held[t]
        val = cash + sum(n * last[t] for t, (n, _) in held.items())
        for t in by_day.get(k - 1, []):
            if len(held) >= slots or t in held or not eligible(t, cal[k - 1]):
                continue
            px = prices[t].get(d)
            if not px:
                continue
            spend = min(cash, val / slots)
            held[t] = (spend * (1 - 0.0005) / px, k + hold)
            last[t] = px
            cash -= spend
        curve.append((d, cash + sum(n * last[t] for t, (n, _) in held.items())))
    return curve


def report(variants, prices, cal, eligible, extra=None):
    base = dict(look=126, skip=21, top_n=5, eligible=eligible, exec_next='close')
    spans = [('since 2000', '2000-01-01', '2100'), ('2000-09', '2000-01-01', '2009-12-31'),
             ('2010-19', '2010-01-01', '2019-12-31'), ('since 2020', '2020-01-01', '2100')]
    print(f"{'top-5 stock account':44} | " + ' | '.join(f"{lab:^22}" for lab, _, _ in spans) + " | trades/yr")
    print(f"{'':44} | " + ' | '.join(f"{'total':>9} {'/yr':>5} {'worst':>6}" for _ in spans) + " |")
    curves = {}
    for label, kw in variants:
        r = run_momentum(prices, cal, START, **kw, **base)
        c = [(p[0], p[1]) for p in r['curve']]
        curves[label] = c
        out = []
        for _, a, b in spans:
            st = curve_stats([v for d, v in c if a <= d <= b])
            out.append(f"{st['total']:+9.0%} {st['annual']:+5.0%} {st['maxDD']:6.0%}")
        buys = sum(len(set(h) - set(p)) for (_, p), (_, h) in zip(r['picks'], r['picks'][1:]))
        print(f"{label:44} | " + ' | '.join(out) + f" | {buys / (len(c) / 252):6.0f}", flush=True)
    if extra:
        curves['news gaps only, no ranking (5 slots, 60 days)'] = extra
        out = []
        for _, a, b in spans:
            st = curve_stats([v for d, v in extra if a <= d <= b])
            out.append(f"{st['total']:+9.0%} {st['annual']:+5.0%} {st['maxDD']:6.0%}")
        print(f"{'news gaps only, no ranking (5 slots, 60 days)':44} | " + ' | '.join(out), flush=True)
    years = sorted({d[:4] for d, _ in curves['top 5 as is']})
    print(f"\n{'by year':44} " + ' '.join(f"{y[2:]:>5}" for y in years))
    for label, c in curves.items():
        ye, prev, ys = {}, c[0][1], []
        for d, v in c:
            ye[d[:4]] = v
        for y in years:
            ys.append(f"{ye[y] / prev - 1:+5.0%}")
            prev = ye[y]
        print(f"{label:44} " + ' '.join(ys))
    print(f"\n{'vs top 5 as is, years better / worse':44}")
    basey = {}
    c = curves['top 5 as is']
    prev = c[0][1]
    for d, v in c:
        basey[d[:4]] = v
    for label, c in list(curves.items())[1:]:
        ye = {}
        for d, v in c:
            ye[d[:4]] = v
        better = worse = 0
        pb = pv = None
        for y in years:
            if pb is not None:
                diff = (ye[y] / pv) - (basey[y] / pb)
                better += diff > 0.005
                worse += diff < -0.005
            pb, pv = basey[y], ye[y]
        print(f"   {label:41} {better:2} better, {worse:2} worse")


if __name__ == '__main__':
    main()

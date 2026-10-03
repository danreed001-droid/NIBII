#!/usr/bin/env python3
"""The viewer's own timing on top of the models, since 2020: step out to cash
(T-bills, BIL) at the close of each 'no trade' date and buy back in at the
close of the re-entry date (whatever the model holds then). A date that is
not a trading day rolls to the next session.

--mix: instead of cash, hold 60% top 5 / 40% best-of sleeve during those
periods (set at the exit close, left to drift until re-entry).

Uses the dashboard's own daily curves (data/momentum_scan.json - run
scripts/momentum_scan.py first) for Top 5, Auto and Steps, and SPY / QQQ.

Usage:
    python scripts/backtest_my_timing.py
    python scripts/backtest_my_timing.py --mix
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_hedge import load_assets  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.sleeve import filled, sleeve_curve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PERIODS = [('2020-03-10', '2020-03-25'), ('2022-03-02', '2022-03-17'), ('2022-04-19', '2022-07-15'),
               ('2022-09-02', '2022-10-27'), ('2025-03-31', '2025-04-26'), ('2026-03-05', '2026-04-11')]
MODELS = [('strategy', 'Top 5 (100%)'), ('plan', 'Auto'), ('steps', 'Steps'), ('SPY', 'SPY'), ('QQQ', 'QQQ')]


def on_or_after(calendar, d):
    return next(x for x in calendar if x >= d)


def with_timing(curve, cash, periods, top=None, sleeve=None, share=0.6):
    """curve [[date, v]]: out at the close of each period's first date, back in at the close of its second.
    Out = cash (`cash` {date: price}), or with top/sleeve given, share in top + rest in sleeve."""
    out_days = set()
    cal = [d for d, _ in curve]
    spans = [(on_or_after(cal, a), on_or_after(cal, b)) for a, b in periods]
    for a, b in spans:
        out_days.update(d for d in cal if a < d <= b)   # returns from the day after the exit through re-entry day
    res, val, a, b = [[cal[0], 1.0]], 1.0, 0.0, 0.0
    for (d0, v0), (d1, v1) in zip(curve, curve[1:]):
        if d1 in out_days and top is not None:
            if d0 not in out_days:          # just stepped aside at d0's close
                a, b = val * share, val * (1 - share)
            a *= top[d1] / top[d0]
            b *= sleeve[d1] / sleeve[d0]
            val = a + b
        else:
            val *= cash[d1] / cash[d0] if d1 in out_days else v1 / v0
        res.append([d1, val])
    return res, spans


def main():
    scan = json.load(open(os.path.join(ROOT, 'data', 'momentum_scan.json')))
    cv = scan['curves']
    cal = [d for d, _ in cv['strategy']]
    assets = load_assets()
    bil = filled({'BIL': assets['BIL']}, cal)['BIL']
    mix = '--mix' in sys.argv
    top, sl = dict(cv['strategy']), dict(sleeve_curve(assets, cal, cal[0])[0])
    print('Out periods held as ' + ('60% top 5 / 40% sleeve' if mix else 'cash (T-bills)') + '\n')
    print(f"{'model':14} {'as is':>9} {'per yr':>7} {'worst':>6} | {'your timing':>11} {'per yr':>7} {'worst':>6} | {'difference':>10}")
    spans = None
    for key, name in MODELS:
        c = cv[key]
        mine, spans = with_timing(c, bil, OUT_PERIODS, top if mix else None, sl if mix else None)
        a = curve_stats([p[1] for p in c])
        b = curve_stats([p[1] for p in mine])
        print(f"{name:14} {a['total']:+9.0%} {a['annual']:+7.0%} {a['maxDD']:6.0%} | {b['total']:+11.0%} {b['annual']:+7.0%} "
              f"{b['maxDD']:6.0%} | {(b['annual'] - a['annual']) * 100:+8.1f} pts/yr")
    print("\nEach period: what the model did while you were in cash (negative = loss you avoided)")
    hdr = ''.join(f"{n:>14}" for _, n in MODELS)
    print(f"{'out':>10} -> {'back in':10} {'days':>4}{hdr}{'cash':>8}{'60/40':>8}")
    for a, b in spans:
        row = ''
        for key, _ in MODELS:
            d = dict(cv[key])
            row += f"{d[b] / d[a] - 1:+14.1%}"
        n = sum(1 for d in cal if a < d <= b)
        m6 = 0.6 * top[b] / top[a] + 0.4 * sl[b] / sl[a] - 1
        print(f"{a:>10} -> {b:10} {n:4}{row}{bil[b] / bil[a] - 1:+8.1%}{m6:+8.1%}")


if __name__ == '__main__':
    main()

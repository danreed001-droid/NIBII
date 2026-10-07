#!/usr/bin/env python3
"""Does the Bitcoin Oct 2015 - Oct 2016 pattern predict a big move in STOCKS?

Template: BTC's 12-month path from 2015-10-01 to 2016-10-01 (log price,
resampled to 253 points): a steady climb of +158%, above its 200-day average
97% of the time, worst pullback -29%, a big leg up in the last third then a
sideways pause.

Every month-end since 2001, every stock in the universe (S&P 500 with join
dates + Nasdaq-100, long-history data): its last 252 sessions are compared
with the template -
  shape      correlation of the two paths (1.0 = identical shape)
  look-alike shape 0.90+ AND a similar size of move: up 80-300% over the
             year, worst pullback between -15% and -45%, above its 200-day
             average 85%+ of the time
and the next 12 months are measured (total, best point, worst point, and vs
the average stock over the same 12 months). Split 2001-2012 / 2013-2026.

Today's look-alikes are listed at the end.

Usage:
    python scripts/study_btc_pattern_stocks.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402
from study_big_moves import roll_mean  # noqa: E402

W = 252
SPLIT = '2013-01-01'


def template():
    import yfinance as yf
    h = yf.Ticker('BTC-USD').history(start='2015-09-25', end='2016-10-03', auto_adjust=False)['Close']
    s = h[(h.index >= '2015-10-01') & (h.index <= '2016-10-01 23:59')]
    y = np.log(s.values / s.values[0])
    t = np.linspace(0, len(y) - 1, W + 1)
    y = np.interp(t, np.arange(len(y)), y)
    return (y - y.mean()) / y.std()


def main():
    tz = template()
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    month_end = [i for i in range(W + 200, n - 1) if cal[i][:7] != cal[i + 1][:7] and cal[i] >= '2001-01-01']
    tick = sorted(t for t, b in bars.items() if len(b) > W + 250)
    C = np.full((len(tick), n), np.nan)
    ok = np.zeros((len(tick), n), bool)
    for a, t in enumerate(tick):
        blocked = blocked_dates(bars[t])
        for d, o, h, lo, c in bars[t]:
            i = pos.get(d)
            if i is not None:
                C[a, i] = c
                ok[a, i] = d not in blocked and (t not in sp or added.get(t, '0000') <= d)
    for a in range(len(tick)):   # carry over gaps
        last = np.nan
        for i in range(n):
            if np.isfinite(C[a, i]):
                last = C[a, i]
            else:
                C[a, i] = last
    # equal-weight universe index for "vs the average stock"
    with np.errstate(divide='ignore', invalid='ignore'):
        r1 = C[:, 1:] / C[:, :-1] - 1
    r1 = np.where(ok[:, 1:] & np.isfinite(r1) & (np.abs(r1) < 1), r1, np.nan)
    ew = np.r_[1.0, np.cumprod(1 + np.nan_to_num(np.nanmean(r1, axis=0)))]

    rows = []
    for a, t in enumerate(tick):
        c = C[a]
        ma = roll_mean(c, 200)
        for i in month_end:
            if not ok[a, i] or not np.isfinite(c[i - W]) or not c[i - W] > 0:
                continue
            x = np.log(c[i - W:i + 1] / c[i - W])
            if not np.all(np.isfinite(x)) or x.std() == 0:
                continue
            shape = float(np.mean(tz * (x - x.mean()) / x.std()))
            seg = c[i - W:i + 1]
            chg = seg[-1] / seg[0] - 1
            dd = float(np.min(seg / np.maximum.accumulate(seg) - 1))
            above = float(np.mean(seg > ma[i - W:i + 1]))
            j = min(n - 1, i + 252)
            full = i + 252 < n
            f = c[i:j + 1] / c[i]
            rows.append(dict(t=t, d=cal[i], shape=shape, chg=chg, dd=dd, above=above, full=full,
                             n12=f[-1] - 1, mx=f.max() - 1, mn=f.min() - 1, ex=(f[-1] - 1) - (ew[j] / ew[i] - 1)))
    print(f"{len(rows):,} stock-months scanned", file=sys.stderr)

    def look(r):
        return r['shape'] >= 0.9 and 0.8 <= r['chg'] <= 3.0 and -0.45 <= r['dd'] <= -0.15 and r['above'] >= 0.85

    groups = [
        ('look-alike (shape + size + steadiness)', look),
        ('shape 0.90+ (any size)', lambda r: r['shape'] >= 0.9),
        ('up 80-300% in a year, any shape', lambda r: 0.8 <= r['chg'] <= 3.0),
        ('shape below 0.5', lambda r: r['shape'] < 0.5),
        ('ALL stock-months (base rate)', lambda r: True),
    ]
    print(f"\n{'next 12 months after the month-end':42} | {'2001-2012':^52} | {'2013-2026':^52}")
    hdr = f"{'n':>6} {'avg':>6} {'median':>7} {'vs avg':>7} {'2x+':>5} {'fell 50%':>8} {'+50% later':>10}"
    print(f"{'':42} | {hdr} | {hdr}")
    for lab, fn in groups:
        cells = []
        for per in (lambda r: r['d'] < SPLIT, lambda r: r['d'] >= SPLIT):
            sel = [r for r in rows if r['full'] and per(r) and fn(r)]
            if not sel:
                cells.append(f"{'0':>6}{'':>46}")
                continue
            n12 = np.array([r['n12'] for r in sel])
            cells.append(f"{len(sel):6} {n12.mean():+6.0%} {np.median(n12):+7.0%} {np.mean([r['ex'] for r in sel]):+7.0%} "
                         f"{np.mean([r['mx'] >= 1 for r in sel]):5.0%} {np.mean([r['mn'] <= -0.5 for r in sel]):8.0%} "
                         f"{np.mean([r['mx'] >= 0.5 for r in sel]):10.0%}")
        print(f"{lab:42} | {cells[0]} | {cells[1]}")
    print("  avg / median = next-12-month return; vs avg = minus the average stock's; 2x+ = doubled at some point;"
          " fell 50% = was down 50%+ at some point; +50% later = was up 50%+ at some point")

    la = [r for r in rows if look(r) and r['full']]
    by_year = {}
    for r in la:
        by_year[r['d'][:4]] = by_year.get(r['d'][:4], 0) + 1
    print("\nlook-alike stock-months by year: " + ', '.join(f"{y}:{c}" for y, c in sorted(by_year.items())))
    best = sorted(la, key=lambda r: -r['n12'])[:8]
    worst = sorted(la, key=lambda r: r['n12'])[:8]
    print("  biggest moves after a look-alike: " + '; '.join(f"{r['t']} {r['d'][:7]} {r['n12']:+.0%}" for r in best))
    print("  worst after a look-alike:         " + '; '.join(f"{r['t']} {r['d'][:7]} {r['n12']:+.0%}" for r in worst))

    last = max(r['d'] for r in rows)
    now = sorted([r for r in rows if r['d'] == last and look(r)], key=lambda r: -r['shape'])
    print(f"\nLook-alikes right now (month-end {last}): " + (', '.join(f"{r['t']} (shape {r['shape']:.2f}, {r['chg']:+.0%})" for r in now) or 'none'))
    top_shape = sorted([r for r in rows if r['d'] == last], key=lambda r: -r['shape'])[:10]
    print("  closest shapes now: " + ', '.join(f"{r['t']} {r['shape']:.2f} ({r['chg']:+.0%})" for r in top_shape))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Quiet rounding base -> accelerating (slightly exponential) rise, at any speed.

The BTC 2015-16 chart, as features rather than an exact path:
  1. QUIET BASE (Jan-Sep 2015 for BTC): price goes roughly nowhere (net move
     within half of one normal swing) with volatility at most 0.8x the
     year before it (BTC: ~50% vs 64% in the 2014 crash).
  2. ROUNDING: over base + rise the log price fits a U-shaped curve (positive
     curvature, the curve's low in the first 15-60% of the window, fit R2 0.75+).
  3. ACCELERATING RISE (Oct 2015 - Jun 2016 for BTC): the rise is at least 1.5
     normal swings, its second half climbs at least 1.3x faster than its
     first half (BTC: ~4x), and it ends at (95%+ of) the window high.
Normal swing = the base's daily volatility x sqrt(length).

Scales: base and rise each 21, 42, 84, 126 or 189 sessions (1, 2, 4, 6, 9
months). Checked every Friday since 2001 on every stock in the universe
(S&P 500 + Nasdaq-100, long-history data); BTC itself is checked too, with
the same rules on calendar days.

Next: the following rise-length and twice that - return, vs the average
stock, and how often it then moved 2+ normal swings up ("blew up") or down.
Split 2001-2012 / 2013-2026.

Usage:
    python scripts/study_base_breakout.py
"""
import math
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402

SCALES = (21, 42, 84, 126, 189)
SPLIT = '2013-01-01'
QUIET, ROUND_R2, ACCEL, RISE_Z = 0.8, 0.75, 1.3, 1.5


def detect(y, i, L, prior=252, per_year=252):
    """y: log prices; pattern ending at i with base [i-2L, i-L] and rise [i-L, i]. Returns (hit, info)."""
    s0 = i - 2 * L
    if s0 - prior < 1:
        return False, None
    r = np.diff(y[s0 - prior:i + 1])
    if not np.all(np.isfinite(r)):
        return False, None
    rp, rb, rr = r[:prior], r[prior:prior + L], r[prior + L:]
    vp, vb = rp.std(), rb.std()
    if vp <= 0 or vb <= 0:
        return False, None
    swing = vb * math.sqrt(L)
    base_move = y[i - L] - y[s0]
    if vb > QUIET * vp or abs(base_move) > 0.5 * swing:
        return False, None
    rise = y[i] - y[i - L]
    h = L // 2
    s1, s2 = (y[i - L + h] - y[i - L]), (y[i] - y[i - L + h])
    if rise < RISE_Z * swing or s1 <= 0 or s2 < ACCEL * s1:
        return False, None
    w = y[s0:i + 1]
    if y[i] < w.max() + math.log(0.95):
        return False, None
    t = np.linspace(0, 1, len(w))
    c2, c1, c0 = np.polyfit(t, w, 2)
    fit = c0 + c1 * t + c2 * t * t
    r2 = 1 - ((w - fit) ** 2).sum() / ((w - w.mean()) ** 2).sum()
    vtx = -c1 / (2 * c2) if c2 > 0 else -1
    if c2 <= 0 or not 0.15 <= vtx <= 0.6 or r2 < ROUND_R2:
        return False, None
    return True, dict(quiet=vb / vp, accel=s2 / s1, rise_z=rise / swing, r2=r2, swing=swing, vtx=vtx)


def btc_check():
    import yfinance as yf
    h = yf.Ticker('BTC-USD').history(start='2014-09-01', auto_adjust=False)['Close']
    d = [x.strftime('%Y-%m-%d') for x in h.index]
    y = np.log(h.values)
    print("BTC with the same rules (calendar days; base and rise each N days):")
    for L in (30, 60, 120, 180, 270):
        hits = [d[i] for i in range(len(y)) if detect(y, i, L, prior=365, per_year=365)[0]]
        eps = []
        for x in hits:
            if not eps or (date.fromisoformat(x) - date.fromisoformat(eps[-1][-1])).days > 60:
                eps.append([x])
            else:
                eps[-1].append(x)
        print(f"  {L:3}-day base + {L}-day rise: " + (', '.join(f"{e[0]}→{e[-1]}" if len(e) > 1 else e[0] for e in eps) or 'none'))


def main():
    try:
        btc_check()
    except Exception as e:  # noqa: BLE001
        print("BTC check skipped:", e)
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    wd = [date.fromisoformat(d).weekday() for d in cal]
    fri = [i for i in range(1, n - 1) if wd[i + 1] <= wd[i] and cal[i] >= '2001-01-01']
    tick = sorted(t for t, b in bars.items() if len(b) > 400)
    m = len(tick)
    C = np.full((m, n), np.nan)
    ok = np.zeros((m, n), bool)
    for a, t in enumerate(tick):
        blocked = blocked_dates(bars[t])
        for d, o, h, lo, c in bars[t]:
            i = pos.get(d)
            if i is not None:
                C[a, i] = c
                ok[a, i] = d not in blocked and (t not in sp or added.get(t, '0000') <= d)
    for a in range(m):
        last = np.nan
        for i in range(n):
            if np.isfinite(C[a, i]):
                last = C[a, i]
            else:
                C[a, i] = last
    Y = np.log(C)
    with np.errstate(invalid='ignore'):
        r1 = np.c_[np.full(m, np.nan), np.exp(np.diff(Y, axis=1)) - 1]
    r1 = np.where(ok & np.isfinite(r1) & (np.abs(r1) < 1), r1, np.nan)
    ew = np.cumprod(1 + np.nan_to_num(np.nanmean(r1, axis=0)))

    for L in SCALES:
        hits, base = [], []
        for a in range(m):
            y = Y[a]
            last_hit = -10 ** 9
            for i in fri:
                if i + 2 * L >= n or i < 2 * L + 253 or not ok[a, i]:
                    continue
                ok_hit, info = detect(y, i, L)
                fwd1 = y[i + L] - y[i]
                fwd2 = y[i + 2 * L] - y[i]
                if not (np.isfinite(fwd1) and np.isfinite(fwd2)):
                    continue
                ex1 = math.exp(fwd1) - 1 - (ew[i + L] / ew[i] - 1)
                ex2 = math.exp(fwd2) - 1 - (ew[i + 2 * L] / ew[i] - 1)
                rb = np.diff(y[i - L:i + 1])
                swing = np.nanstd(rb) * math.sqrt(L) if ok_hit is False else info['swing']
                row = (cal[i] < SPLIT, math.exp(fwd1) - 1, ex1, fwd1 / swing, math.exp(fwd2) - 1, ex2, fwd2 / (swing * math.sqrt(2)))
                if ok_hit and i - last_hit > L:       # one signal per episode
                    hits.append(row + (tick[a], cal[i]))
                    last_hit = i
                elif (i // 5) % 4 == 0:                # thin the base rate a little for speed
                    base.append(row)
        print(f"\n=== {L}-session quiet base + {L}-session accelerating rise (~{L / 21:.0f} + {L / 21:.0f} months) ===")
        print(f"{'':16} | {'next ' + str(L) + ' sessions':^40} | {'next ' + str(2 * L) + ' sessions':^40}")
        hdr = f"{'n':>6} {'avg':>6} {'vs avg':>7} {'blew up':>8} {'blew dn':>8}"
        print(f"{'':16} | {hdr:40} | {hdr:40}")
        for lab, rows, keep in (('pattern 01-12', hits, True), ('pattern 13-26', hits, False),
                                ('all 01-12', base, True), ('all 13-26', base, False)):
            sel = [r for r in rows if r[0] == keep]
            if len(sel) < 10:
                print(f"{lab:16} | {len(sel):6}")
                continue
            A = np.array([r[1:7] for r in sel])
            print(f"{lab:16} | {len(sel):6} {A[:, 0].mean():+6.1%} {A[:, 1].mean():+7.1%} {np.mean(A[:, 2] >= 2):8.1%} {np.mean(A[:, 2] <= -2):8.1%} | "
                  f"{len(sel):6} {A[:, 3].mean():+6.1%} {A[:, 4].mean():+7.1%} {np.mean(A[:, 5] >= 2):8.1%} {np.mean(A[:, 5] <= -2):8.1%}")
        recent = sorted(hits, key=lambda r: r[-1])[-6:]
        if recent:
            print("  latest signals: " + ', '.join(f"{r[-2]} {r[-1]} (next {L}: {r[1]:+.0%})" for r in recent))
        # signals right now (last Friday, forward not known yet)
        lastf = fri[-1]
        now = [tick[a] for a in range(m) if ok[a, lastf] and detect(Y[a], lastf, L)[0]]
        print(f"  signals at {cal[lastf]}: " + (', '.join(now) if now else 'none'))


if __name__ == '__main__':
    main()

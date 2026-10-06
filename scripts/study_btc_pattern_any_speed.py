#!/usr/bin/env python3
"""The BTC Oct 2015 - Oct 2016 shape at ANY speed in stocks.

The 12-month BTC path (log price) is squeezed to L sessions - 21 (~1 month),
42 (2 months), 63 (3 months), 126 (6 months), 252 (12 months). Every Friday
since 2001, every stock in the universe: its last L sessions are compared with
the squeezed template (correlation of the two shapes, size ignored).

  look-alike       shape 0.90+
  + strong rise    and the rise over the window is at least 1 standard
                   deviation of the stock's own normal L-session swing
                   (BTC's 2015-16 year was ~1.7)

Then the NEXT L sessions (same length as the pattern - after BTC's 12-month
pattern came its 12-month blow-off):
  avg / vs avg     return, and minus the average stock's over the same days
  big up / down    moved more than 2 of its own normal L-session swings up /
                   down at the end ("blew up" / "blew down")
Split 2001-2012 / 2013-2026; base rate = every stock-Friday.

Usage:
    python scripts/study_btc_pattern_any_speed.py
"""
import math
import os
import sys
from datetime import date

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402
from study_big_moves import roll_std  # noqa: E402

LENGTHS = (21, 42, 63, 126, 252)
SPLIT = '2013-01-01'


def btc_path():
    import yfinance as yf
    h = yf.Ticker('BTC-USD').history(start='2015-09-25', end='2016-10-03', auto_adjust=False)['Close']
    s = h[(h.index >= '2015-10-01') & (h.index <= '2016-10-01 23:59')]
    return np.log(s.values / s.values[0])


def main():
    path = btc_path()
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    wd = np.array([date.fromisoformat(d).weekday() for d in cal])
    fri = np.array([i for i in range(300, n - 1) if wd[i + 1] <= wd[i] and cal[i] >= '2001-01-01'])
    tick = sorted(t for t, b in bars.items() if len(b) > 300)
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
    with np.errstate(divide='ignore', invalid='ignore'):
        lr = np.log(C[:, 1:] / C[:, :-1])
    lr = np.c_[np.full(m, np.nan), lr]
    vol = np.array([roll_std(lr[a], 252) for a in range(m)])   # daily volatility, past year
    r1 = np.where(ok & np.isfinite(lr) & (np.abs(lr) < 0.7), np.exp(lr) - 1, np.nan)
    ew = np.cumprod(1 + np.nan_to_num(np.nanmean(r1, axis=0)))
    find = np.array([cal[i] < SPLIT for i in fri])

    for L in LENGTHS:
        tpl = np.interp(np.linspace(0, len(path) - 1, L + 1), np.arange(len(path)), path)
        tz = (tpl - tpl.mean()) / tpl.std()
        F = fri[(fri >= L) & (fri + L < n)]
        fmask = np.array([cal[i] < SPLIT for i in F])
        res = {k: [] for k in ('shape', 'z', 'nz', 'ex', 'ret', 'per', 'tk', 'd')}
        for a in range(m):
            c = np.log(C[a])
            win = sliding_window_view(c, L + 1)          # win[s] = c[s .. s+L]
            W = win[F - L]                                 # windows ending at each Friday
            good = ok[a, F] & np.all(np.isfinite(W), axis=1) & np.isfinite(vol[a, F])
            if not good.any():
                continue
            W, Fi, per = W[good], F[good], fmask[good]
            X = W - W[:, :1]
            sd = X.std(axis=1)
            sd[sd == 0] = np.nan
            shape = ((X - X.mean(axis=1, keepdims=True)) / sd[:, None] * tz).mean(axis=1)
            swing = vol[a, Fi] * math.sqrt(L)              # normal L-session move (log)
            rise = X[:, -1] / swing
            nxt = c[Fi + L] - c[Fi]
            res['shape'].append(shape)
            res['z'].append(rise)
            res['nz'].append(nxt / swing)
            res['ret'].append(np.exp(nxt) - 1)
            res['ex'].append(np.exp(nxt) - 1 - (ew[Fi + L] / ew[Fi] - 1))
            res['per'].append(per)
            res['tk'].append(np.full(len(Fi), a))
            res['d'].append(Fi)
        R = {k: np.concatenate(v) for k, v in res.items()}
        print(f"\n=== pattern squeezed to {L} sessions (~{L / 21:.0f} month{'s' if L > 21 else ''}); next {L} sessions ===")
        print(f"{'':30} | {'2001-2012':^44} | {'2013-2026':^44}")
        hdr = f"{'n':>7} {'avg':>6} {'vs avg':>7} {'big up':>7} {'big down':>9}"
        print(f"{'':30} | {hdr:^44} | {hdr:^44}")
        for lab, sel in (('look-alike (shape 0.90+)', R['shape'] >= 0.9),
                         ('look-alike + strong rise', (R['shape'] >= 0.9) & (R['z'] >= 1)),
                         ('very close (0.95+) + rise', (R['shape'] >= 0.95) & (R['z'] >= 1)),
                         ('strong rise, any shape', R['z'] >= 1),
                         ('ALL (base rate)', np.isfinite(R['shape']))):
            cells = []
            for p in (True, False):
                s = sel & (R['per'] == p) & np.isfinite(R['nz'])
                k = int(s.sum())
                if k < 30:
                    cells.append(f"{k:>7}{'':>37}")
                    continue
                cells.append(f"{k:7} {np.mean(R['ret'][s]):+6.1%} {np.mean(R['ex'][s]):+7.1%} "
                             f"{np.mean(R['nz'][s] >= 2):7.1%} {np.mean(R['nz'][s] <= -2):9.1%}")
            print(f"{lab:30} | {cells[0]:44} | {cells[1]:44}")
        # current look-alikes at the last Friday with a full window
        last = fri[-1]
        now = []
        for a in range(m):
            c = np.log(C[a, last - L:last + 1])
            if not ok[a, last] or not np.all(np.isfinite(c)):
                continue
            x = c - c[0]
            if x.std() == 0:
                continue
            sh = float(np.mean((x - x.mean()) / x.std() * tz))
            sw = vol[a, last] * math.sqrt(L)
            if sh >= 0.95 and x[-1] / sw >= 1:
                now.append((sh, tick[a], math.exp(x[-1]) - 1))
        now.sort(reverse=True)
        print(f"  look-alikes now ({cal[last]}, 0.95+ and a strong rise): " +
              (', '.join(f"{t} {s:.2f} ({r:+.0%})" for s, t, r in now[:12]) or 'none') + (f" … {len(now)} total" if len(now) > 12 else ''))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Hunting for single-stock edges: classic patterns, 2001-2026, two periods.

For each pattern the signal is read at a session's close and the trade is
entered at the NEXT session's close (you can't trade after the bell). Reported
per period (2001-2012 = find, 2013-2026 = check):
  n        number of signals (per year in brackets)
  ex5/ex20/ex60   average return vs the equal-weight average of all stocks in
           the universe over the next 5 / 20 / 60 sessions (the edge itself)
  beat     % of signals beating that average over 20 sessions
  opt3m    same with a 3-month option at expiry (60 sessions)
  opt      average 1-month at-the-money option at expiry (20 sessions), CALL
           for patterns that should go up, PUT for ones that should go down;
           priced from the higher of 20/63-day realized volatility + 10 points,
           4% rate, 3% paid in (so +0% = paid for itself)
A pattern is only interesting if it holds in BOTH periods.

Universe: S&P 500 (with join dates) + Nasdaq-100, long-history data of
backtest_long_history.py (today's lists: survivorship flatters 'buy the
loser' patterns in the early years); volume from data/.volume.pkl.

Usage:
    python scripts/study_edges.py
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
from study_big_moves import roll_mean, roll_std, volumes  # noqa: E402

RATE, COST, T = 0.04, 0.03, 28 / 365
SPLIT = '2013-01-01'


def ncdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def atm_cost(iv, T=T):
    """ATM call and put price per $1 of stock, plus the entry cost."""
    v = iv * math.sqrt(T)
    d1 = (RATE + 0.5 * iv * iv) * T / v
    call = ncdf(d1) - math.exp(-RATE * T) * ncdf(d1 - v)
    put = call - 1 + math.exp(-RATE * T)
    return call * (1 + COST), put * (1 + COST)


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    vols = volumes(sorted(bars))
    tick = sorted(t for t, bs in bars.items() if len(bs) > 300)
    m = len(tick)
    O, H, L, C, V = (np.full((m, n), np.nan) for _ in range(5))
    ok = np.zeros((m, n), bool)
    for a, t in enumerate(tick):
        blocked = blocked_dates(bars[t])
        vt = vols.get(t, {})
        for d, o, h, lo, c in bars[t]:
            i = pos.get(d)
            if i is None:
                continue
            O[a, i], H[a, i], L[a, i], C[a, i] = o, h, lo, c
            V[a, i] = vt.get(d, np.nan)
            ok[a, i] = d not in blocked and (t not in sp or added.get(t, '0000') <= d)
    print(f"{m} stocks x {n} sessions", file=sys.stderr, flush=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        P = np.roll(C, 1, axis=1)
        P[:, 0] = np.nan
        r1 = C / P - 1
        gap = O / P - 1
        pos_in_range = (C - L) / (H - L)
        lr = np.log(C / P)
    spy = np.array([b[4] for b in bench['SPY']])
    spy_r = np.r_[np.nan, spy[1:] / spy[:-1] - 1]
    spy200 = roll_mean(spy, 200)
    # equal-weight universe index (eligible stocks), daily
    ew_r = np.nanmean(np.where(ok & np.isfinite(r1) & (np.abs(r1) < 1), r1, np.nan), axis=0)
    ew_r[~np.isfinite(ew_r)] = 0
    ew = np.cumprod(1 + ew_r)
    iv = np.full((m, n), np.nan)
    v60 = np.full((m, n), np.nan)
    print("volatility / volume...", file=sys.stderr, flush=True)
    for a in range(m):
        iv[a] = np.fmax(roll_std(lr[a], 20), roll_std(lr[a], 63)) * math.sqrt(252) + 0.10
        v60[a] = np.r_[np.nan, roll_mean(V[a], 60)[:-1]]   # average volume BEFORE today
    iv = np.fmax(iv, 0.20)
    volx = V / v60
    hi252 = np.full((m, n), np.nan)
    for a in range(m):     # highest close of the 252 sessions BEFORE today
        c = C[a]
        w = sliding_window_view(np.where(np.isfinite(c), c, -np.inf), 252)
        hi252[a, 252:] = w[:-1].max(axis=1)
    hi63_before = np.full((m, n), np.nan)
    for a in range(m):
        c = C[a]
        w = sliding_window_view(np.where(np.isfinite(c), c, -np.inf), 63)
        hi63_before[a, 63:] = w[:-1].max(axis=1)
    mom = np.full((m, n), np.nan)
    mom[:, 126:] = C[:, 105:-21] / C[:, :-126]
    big1 = np.abs(r1) > 0.06

    def events(mask, side):
        """Rows (a, i) where mask; entry at i+1 close. Returns per-event arrays."""
        mask = mask & ok & np.isfinite(C)
        mask[:, :260] = False
        mask[:, n - 62:] = False
        a, i = np.nonzero(mask)
        e = i + 1
        c0 = C[a, e]
        good = np.isfinite(c0) & (c0 > 0)
        a, i, e, c0 = a[good], i[good], e[good], c0[good]
        out = dict(d=np.array(cal)[i], side=side)
        for k in (5, 20, 60):
            f = C[a, e + k] / c0 - 1
            out[f'ex{k}'] = f - (ew[e + k] / ew[e] - 1)
            out[f'f{k}'] = f
        call, put = atm_cost(iv[a, e])
        f = out['f20']
        out['opt'] = (np.maximum(f, 0) / call - 1) if side > 0 else (np.maximum(-f, 0) / put - 1)
        call, put = atm_cost(iv[a, e], 88 / 365)
        f = out['f60']
        out['opt60'] = (np.maximum(f, 0) / call - 1) if side > 0 else (np.maximum(-f, 0) / put - 1)
        return out

    def line(ev, sel):
        k = int(sel.sum())
        if k < 30:
            return f"{k:>6} {'(too few)':>44}"
        yrs = len({d[:4] for d in ev['d'][sel]})
        s = ev['side']
        g = lambda x: np.nanmean(x[sel]) * s  # noqa: E731  (sign so + = edge in the pattern's direction)
        beat = np.nanmean((ev['ex20'][sel] * s) > 0)
        return (f"{k:>6} {k / max(1, yrs):4.0f}/y {g(ev['ex5']):+5.1%} {g(ev['ex20']):+5.1%} {g(ev['ex60']):+5.1%} "
                f"{beat:4.0%} {np.nanmean(ev['opt'][sel]):+5.0%} {np.nanmean(ev['opt60'][sel]):+5.0%}")

    hdr = f"{'n':>6} {'':>6} {'ex5':>5} {'ex20':>5} {'ex60':>5} {'beat':>4} {'opt':>5} {'opt3m':>5}"
    print(f"\n{'pattern (+ = edge in its direction)':46} {'dir':>4} | {'2001-2012':^48} | {'2013-2026':^48}")
    print(f"{'':46} {'':>4} | {hdr} | {hdr}")
    results = {}

    def show(label, mask, side):
        ev = events(mask, side)
        A = ev['d'] < SPLIT
        results[label] = ev
        print(f"{label:46} {'up' if side > 0 else 'down':>4} | {line(ev, A)} | {line(ev, ~A)}", flush=True)

    with np.errstate(invalid='ignore'):
        print("-- earnings-style gaps")
        go_up = (gap >= 0.05) & (r1 >= 0.05) & (pos_in_range >= 0.75)
        go_dn = (gap <= -0.05) & (r1 <= -0.05) & (pos_in_range <= 0.25)
        show("gap up 5%+, closes near the high", go_up, 1)
        show("  ... with volume 2x+", go_up & (volx >= 2), 1)
        show("  ... with volume 2x+ and SPY above 200-day", go_up & (volx >= 2) & (spy > spy200)[None, :], 1)
        show("  ... gap up 10%+ (big news)", (gap >= 0.10) & (r1 >= 0.10) & (pos_in_range >= 0.6), 1)
        show("gap down 5%+, closes near the low", go_dn, -1)
        show("  ... with volume 2x+", go_dn & (volx >= 2), -1)
        show("gap up 5%+ but closes below the open (fade)", (gap >= 0.05) & (C < O), -1)
        show("gap down 5%+ but closes above the open (reclaim)", (gap <= -0.05) & (C > O), 1)

        print("-- breakouts / strength")
        brk = (C > hi252) & (hi63_before < hi252)        # first new 52-week high in 3+ months
        show("first new 52w high in 3+ months", brk, 1)
        show("  ... with volume 1.5x+", brk & (volx >= 1.5), 1)
        show("up on a day SPY falls 2%+ (stock +1%+)", (r1 >= 0.01) & (spy_r <= -0.02)[None, :], 1)
        show("down 5%+ on a day SPY is flat/up", (r1 <= -0.05) & (spy_r >= 0)[None, :], -1)

        # cross-sectional patterns, Fridays only
        wd = np.array([date.fromisoformat(d).weekday() for d in cal])
        fri = np.r_[wd[1:] <= wd[:-1], False]
        r5 = C / np.roll(C, 5, axis=1) - 1
        r5[:, :5] = np.nan

        def pct_rank(X):
            Y = np.where(ok & np.isfinite(X), X, np.nan)
            order = np.argsort(np.argsort(np.where(np.isfinite(Y), Y, np.inf), axis=0), axis=0).astype(float)
            cnt = np.isfinite(Y).sum(axis=0)
            with np.errstate(invalid='ignore', divide='ignore'):
                R = order / np.maximum(cnt - 1, 1)
            R[~np.isfinite(Y)] = np.nan
            return R

        R5, RM = pct_rank(r5), pct_rank(mom)
        print("-- weekly reversal (Friday ranks)")
        show("worst 5% of the week", fri[None, :] & (R5 <= 0.05), 1)
        show("  ... SPY above 200-day", fri[None, :] & (R5 <= 0.05) & (spy > spy200)[None, :], 1)
        show("best 5% of the week", fri[None, :] & (R5 >= 0.95), -1)
        print("-- dips in leaders")
        show("top 20% strength, down 5%+ in a day", (RM >= 0.8) & (r1 <= -0.05), 1)
        show("top 20% strength, worst 10% of the week", fri[None, :] & (RM >= 0.8) & (R5 <= 0.10), 1)
        show("top 20% strength, pulls back 10%+ from high", fri[None, :] & (RM >= 0.8) & (C / hi252 <= 0.9) & (C / hi252 > 0.8), 1)

        # earnings clock: the last 6%+ day was ~a quarter ago -> report likely within ~2 weeks
        since = np.full((m, n), 999)
        for a in range(m):
            last = -10 ** 6
            for i in range(n):
                if big1[a, i]:
                    last = i
                since[a, i] = i - last
        print("-- earnings run-up (proxy: last 6%+ day 52-58 sessions ago)")
        show("earnings likely in ~1-2 weeks", fri[None, :] & (since >= 52) & (since <= 58), 1)
        show("  ... top 20% strength", fri[None, :] & (since >= 52) & (since <= 58) & (RM >= 0.8), 1)

        # same-month seasonality: the stock's average return in this calendar month over the past 10 years
        print("-- the stock's own calendar month (past 10 years)")
        month = np.array([int(d[5:7]) for d in cal])
        year = np.array([int(d[:4]) for d in cal])
        month_end = np.r_[month[1:] != month[:-1], False]
        mret = {}   # (a, year, month) -> return
        ends = np.nonzero(month_end)[0]
        for a in range(m):
            for j in range(1, len(ends)):
                i0, i1 = ends[j - 1], ends[j]
                if C[a, i0] > 0 and C[a, i1] > 0:
                    mret[(a, year[i1], month[i1])] = C[a, i1] / C[a, i0] - 1
        S = np.full((m, n), np.nan)
        for i in ends:   # at a month end, score the NEXT month for each stock
            nm = month[i] % 12 + 1
            ny = year[i] + (1 if month[i] == 12 else 0)
            for a in range(m):
                past = [mret.get((a, ny - k, nm)) for k in range(1, 11)]
                past = [x for x in past if x is not None]
                if len(past) >= 6:
                    S[a, i] = np.mean(past)
        RS = pct_rank(S)
        show("best 10% history for next month", np.isfinite(RS) & (RS >= 0.9), 1)
        show("worst 10% history for next month", np.isfinite(RS) & (RS <= 0.1), -1)
        show("next month up in 9 or 10 of the past 10 years",
             np.isfinite(S) & month_end[None, :] & _upcount(mret, m, ends, month, year, C, need=9), 1)

    print("\nRead: ex20 = average edge over 20 sessions vs the average stock (e.g. +1.0% = beat it by 1%);"
          " opt = what a 1-month at-the-money option in that direction returned on average.")


def _upcount(mret, m, ends, month, year, C, need):
    n = C.shape[1]
    X = np.zeros((m, n), bool)
    for i in ends:
        nm = month[i] % 12 + 1
        ny = year[i] + (1 if month[i] == 12 else 0)
        for a in range(m):
            past = [mret.get((a, ny - k, nm)) for k in range(1, 11)]
            past = [x for x in past if x is not None]
            if len(past) == 10 and sum(1 for x in past if x > 0) >= need:
                X[a, i] = True
    return X


if __name__ == '__main__':
    main()

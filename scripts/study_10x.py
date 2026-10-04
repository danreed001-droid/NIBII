#!/usr/bin/env python3
"""The 10x hunt: what comes before a cheap call option returning 10 times its price?

Every Friday close since 2001, every stock in the universe (S&P 500 with join
dates + Nasdaq-100, long-history data): a call 10% out of the money is bought
at the next session's close, 1-month (30 days) or 3-month (90 days). Priced
with Black-Scholes from the higher of 20/63-day realized volatility + 10
points (floor 20%), 4% rate, paying 2% over / selling 2% under the price.
Real out-of-the-money calls on stocks often trade a bit CHEAPER than this
(volatility skew), so 10x counts here are on the conservative side; meme-style
spikes where real option prices explode are not captured.

For each trade:
  peak      the best value it reached at any close before expiry (x cost)
  10x / 5x  whether the peak reached 10x / 5x
  TP10      the result if you sell the moment it reaches 10x (else hold to expiry)
  TP5       same, selling at 5x
A trade style only pays if TP10 or TP5 averages above 0 (most trades lose
everything, the hits must pay for them all).

Every condition (bucket of one market / stock reading, and every pair of them)
is scored in 2001-2012 (find) and 2013-2026 (check). The list of the best
conditions is picked on the FIND period only, then shown with the CHECK
period next to it - a real edge holds in both.

Usage:
    python scripts/study_10x.py
"""
import math
import os
import sys
from datetime import date
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402
from study_big_moves import roll_mean, roll_std, volumes  # noqa: E402
from study_edges import bs  # noqa: E402

RATE, SPREAD, OTM = 0.04, 0.02, 1.10
SPLIT = '2013-01-01'


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    ords = np.array([date.fromisoformat(d).toordinal() for d in cal])
    vols = volumes(sorted(bars))
    tick = sorted(t for t, bs_ in bars.items() if len(bs_) > 300)
    m = len(tick)
    H, L, C, V = (np.full((m, n), np.nan) for _ in range(4))
    ok = np.zeros((m, n), bool)
    for a, t in enumerate(tick):
        blocked = blocked_dates(bars[t])
        vt = vols.get(t, {})
        for d, o, h, lo, c in bars[t]:
            i = pos.get(d)
            if i is None:
                continue
            H[a, i], L[a, i], C[a, i] = h, lo, c
            V[a, i] = vt.get(d, np.nan)
            ok[a, i] = d not in blocked and (t not in sp or added.get(t, '0000') <= d)
    # carry closes over gaps so a path never hits NaN mid-trade
    for a in range(m):
        last = np.nan
        for i in range(n):
            if np.isfinite(C[a, i]):
                last = C[a, i]
            elif np.isfinite(last):
                C[a, i] = last
    print(f"{m} stocks x {n} sessions", file=sys.stderr, flush=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        lr = np.log(C / np.roll(C, 1, axis=1))
        lr[:, 0] = np.nan
    iv = np.full((m, n), np.nan)
    rv20 = np.full((m, n), np.nan)
    sq = np.full((m, n), np.nan)
    v60 = np.full((m, n), np.nan)
    for a in range(m):
        r20, r63 = roll_std(lr[a], 20), roll_std(lr[a], 63)
        iv[a] = np.fmax(np.fmax(r20, r63) * math.sqrt(252) + 0.10, 0.20)
        rv20[a] = r20
        v60[a] = np.r_[np.nan, roll_mean(V[a], 60)[:-1]]
    iv_ok = np.isfinite(iv)
    iv = np.where(iv_ok, iv, 0.5)

    vix_px = vols.get('^VIX', {})
    vix = np.array([vix_px.get(d, np.nan) for d in cal])
    spy = np.array([b[4] for b in bench['SPY']])
    spy200 = roll_mean(spy, 200)
    spy_age = np.array([i - (max(0, i - 251) + int(np.argmax(spy[max(0, i - 251):i + 1]))) for i in range(n)])
    spy1m = np.r_[np.full(21, np.nan), spy[21:] / spy[:-21] - 1]

    wd = np.array([date.fromisoformat(d).weekday() for d in cal])
    fridays = [i for i in range(300, n - 65) if cal[i] >= '2001-01-01' and wd[i + 1] <= wd[i]]

    # events (stock, friday) and features
    A, I = [], []
    for i in fridays:
        a = np.nonzero(ok[:, i] & np.isfinite(C[:, i]) & np.isfinite(C[:, i - 260]) & iv_ok[:, i + 1])[0]
        A.append(a)
        I.append(np.full(len(a), i))
    A, I = np.concatenate(A), np.concatenate(I)
    E = I + 1
    print(f"{len(A):,} stock-weeks", file=sys.stderr, flush=True)
    s0 = C[A, E]
    feat = {}
    with np.errstate(divide='ignore', invalid='ignore'):
        ret1m = C[A, I] / C[A, I - 21] - 1
        hi252 = np.array([np.nanmax(C[a, i - 251:i + 1]) for a, i in zip(A, I)])
        off = C[A, I] / hi252 - 1
        mom = C[A, I - 21] / C[A, I - 126] - 1
        volx = V[A, I] / v60[A, I]
        sqz = np.array([np.mean(rv20[a, i - 252:i] <= rv20[a, i]) if np.isfinite(rv20[a, i]) else np.nan for a, i in zip(A, I)])
    # cross-sectional percentiles per Friday
    momp = np.full(len(A), np.nan)
    volp = np.full(len(A), np.nan)
    order = np.argsort(I, kind='stable')
    bounds = np.r_[0, np.nonzero(np.diff(I[order]))[0] + 1, len(I)]
    rv_now = iv[A, I]
    for j in range(len(bounds) - 1):
        idx = order[bounds[j]:bounds[j + 1]]
        for src, dst in ((mom, momp), (rv_now, volp)):
            x = src[idx]
            rk = np.argsort(np.argsort(np.where(np.isfinite(x), x, -np.inf)))
            dst[idx] = rk / max(1, len(idx) - 1)
    v = vix[I]
    feat['VIX'] = {'<15': v < 15, '15-25': (v >= 15) & (v < 25), '25-35': (v >= 25) & (v < 35), '35+': v >= 35}
    age = spy_age[I]
    feat['SPY high'] = {'within 1 mo': age <= 21, '1-6 mo ago': (age > 21) & (age <= 126), '6+ mo ago': age > 126}
    feat['SPY trend'] = {'above 200d': spy[I] > spy200[I], 'below 200d': spy[I] <= spy200[I]}
    s1 = spy1m[I]
    feat['SPY last month'] = {'down 10%+': s1 <= -0.10, 'down 3-10%': (s1 > -0.10) & (s1 <= -0.03), 'flat': np.abs(s1) < 0.03, 'up 3%+': s1 >= 0.03}
    feat['stock last month'] = {'down 30%+': ret1m <= -0.3, 'down 15-30%': (ret1m > -0.3) & (ret1m <= -0.15),
                                'down 0-15%': (ret1m > -0.15) & (ret1m <= 0), 'up 0-15%': (ret1m > 0) & (ret1m < 0.15), 'up 15%+': ret1m >= 0.15}
    feat['off 52w high'] = {'at high': off >= -0.05, '5-25% off': (off < -0.05) & (off >= -0.25), '25-50% off': (off < -0.25) & (off >= -0.5), '50%+ off': off < -0.5}
    feat['6-1 strength'] = {'weakest 10%': momp <= 0.1, 'middle': (momp > 0.1) & (momp < 0.9), 'top 10%': momp >= 0.9}
    feat['volatility rank'] = {'calmest 30%': volp <= 0.3, 'middle': (volp > 0.3) & (volp < 0.8), 'wildest 20%': volp >= 0.8}
    feat['own-year quiet'] = {'quietest 10%': sqz <= 0.1, 'normal': (sqz > 0.1) & (sqz < 0.9), 'wildest 10%': sqz >= 0.9}
    feat['volume'] = {'2x+ avg': volx >= 2, 'normal': volx < 2}
    feat['price'] = {'under $15': s0 < 15, '$15-50': (s0 >= 15) & (s0 < 50), '$50+': s0 >= 50}

    def paths(days, sessions):
        T0 = days / 365
        K = s0 * OTM
        cost = bs(s0, K, T0, iv[A, E], 1) * (1 + SPREAD)
        peak = np.zeros(len(A))
        hit10 = np.full(len(A), -1)
        hit5 = np.full(len(A), -1)
        final = None
        for k in range(1, sessions + 1):
            e = E + k
            t = np.maximum(days - (ords[e] - ords[E]), 0) / 365
            val = bs(C[A, e], K, t, iv[A, e], 1) * (1 - SPREAD) / cost
            val = np.where(np.isfinite(val), val, 0)
            peak = np.maximum(peak, val)
            hit10 = np.where((hit10 < 0) & (val >= 10), k, hit10)
            hit5 = np.where((hit5 < 0) & (val >= 5), k, hit5)
            if t.max() <= 0 or k == sessions:
                final = val
        tp10 = np.where(hit10 > 0, 9.0, final - 1)
        tp5 = np.where(hit5 > 0, 4.0, final - 1)
        return dict(peak=peak, x10=peak >= 10, x5=peak >= 5, tp10=tp10, tp5=tp5, hold=final - 1)

    R = {'1-month 10% OTM call': paths(30, 21), '3-month 10% OTM call': paths(90, 62)}
    find = np.array([cal[i] < SPLIT for i in I])

    def stats(r, sel):
        k = int(sel.sum())
        if k == 0:
            return k, np.nan, np.nan, np.nan, np.nan
        return k, r['x10'][sel].mean(), r['x5'][sel].mean(), r['tp10'][sel].mean(), r['tp5'][sel].mean()

    for name, r in R.items():
        print(f"\n===== {name} =====")
        for lab, sel in (('ALL 2001-2012', find), ('ALL 2013-2026', ~find)):
            k, x10, x5, t10, t5 = stats(r, sel)
            print(f"{lab:44} n {k:>8,}  hit 10x {x10:6.2%}  hit 5x {x5:6.2%}  sell@10x {t10:+5.0%}  sell@5x {t5:+5.0%}  hold {r['hold'][sel].mean():+5.0%}")
        # single buckets
        rows = []
        for f, bk in feat.items():
            for b, mask in bk.items():
                rows.append((f"{f}: {b}", mask))
        for (f1, b1), (f2, b2) in combinations([(f, b) for f, bk in feat.items() for b in bk], 2):
            if f1 == f2:
                continue
            rows.append((f"{f1}: {b1} + {f2}: {b2}", feat[f1][b1] & feat[f2][b2]))
        scored = []
        for lab, mask in rows:
            mA, mB = mask & find, mask & ~find
            if mA.sum() < 150 or mB.sum() < 150:
                continue
            a_ = stats(r, mA)
            b_ = stats(r, mB)
            scored.append((lab, a_, b_))
        print(f"\n{'best 20 conditions, picked on 2001-2012 by sell@5x':66} | {'2001-2012 (find)':^40} | {'2013-2026 (check)':^40}")
        print(f"{'':66} | {'n':>6} {'10x':>6} {'5x':>6} {'@10x':>6} {'@5x':>6} | {'n':>6} {'10x':>6} {'5x':>6} {'@10x':>6} {'@5x':>6}")
        for lab, a_, b_ in sorted(scored, key=lambda x: -x[1][4])[:20]:
            print(f"{lab[:66]:66} | {a_[0]:6} {a_[1]:6.1%} {a_[2]:6.1%} {a_[3]:+6.0%} {a_[4]:+6.0%} | "
                  f"{b_[0]:6} {b_[1]:6.1%} {b_[2]:6.1%} {b_[3]:+6.0%} {b_[4]:+6.0%}")
        both = [x for x in scored if x[1][4] > 0 and x[2][4] > 0]
        print(f"\nconditions with sell@5x above 0 in BOTH periods: {len(both)} of {len(scored)}")
        for lab, a_, b_ in sorted(both, key=lambda x: -min(x[1][4], x[2][4]))[:15]:
            print(f"   {lab[:70]:70} find {a_[4]:+5.0%} (n {a_[0]}, 10x {a_[1]:.1%})  check {b_[4]:+5.0%} (n {b_[0]}, 10x {b_[1]:.1%})")
        # what the 10x winners looked like
        w = r['x10']
        print(f"\n{int(w.sum()):,} trades hit 10x. Share of them in each bucket vs share of all trades:")
        for f, bk in feat.items():
            parts = []
            for b, mask in bk.items():
                parts.append(f"{b} {mask[w].mean():4.0%} vs {mask.mean():4.0%}")
            print(f"   {f:18} " + ' | '.join(parts))
        yrs = {}
        for i in I[w]:
            yrs[cal[i][:4]] = yrs.get(cal[i][:4], 0) + 1
        print("   10x hits by year: " + ', '.join(f"{y}:{c}" for y, c in sorted(yrs.items())))


if __name__ == '__main__':
    main()

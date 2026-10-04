#!/usr/bin/env python3
"""What happens BEFORE a stock makes a big move - and can it be traded with options?

Every Friday close since 2001, for every stock in the dashboard's universe
(S&P 500 with join dates + Nasdaq-100; long-history data of
backtest_long_history.py, plus volume fetched once into data/.volume.pkl):

  big up    the close 20 sessions later is +20% or more
  big down  ... -20% or worse

For each pattern (feature bucket) known at that Friday close it reports how
often a big up / big down follows, and what a 1-month option bought at that
close would have returned at expiry (20 sessions later):
  call      at-the-money call
  put       at-the-money put
  strad     at-the-money call + put (wins on a big move EITHER way)
Options are Black-Scholes priced from the higher of the stock's 20- and 63-day realized volatility
+ 10 points (floor 20%), 4% rate, 3% paid on the way in. That is the catch:
an option already charges for the moves a stock usually makes, so a pattern
only pays if the move is bigger than what the option costs.

Periods: 2001-2012 (find) and 2013-2026 (check) - a pattern that only works in
one of them is probably luck.

Usage:
    python scripts/study_big_moves.py
"""
import math
import os
import pickle
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.options_sim import bs_call  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOL_CACHE = os.path.join(ROOT, 'data', '.volume.pkl')
H, BIG, RATE, COST, BUMP = 20, 0.20, 0.04, 0.03, 0.10
T = 28 / 365
SPLIT = '2013-01-01'


def volumes(tickers):
    if os.path.exists(VOL_CACHE):
        with open(VOL_CACHE, 'rb') as f:
            return pickle.load(f)
    import yfinance as yf
    out = {}
    for k in range(0, len(tickers), 100):
        part = tickers[k:k + 100]
        print(f"  volume {k + len(part)}/{len(tickers)}", file=sys.stderr, flush=True)
        df = yf.download(part + ['^VIX'] if k == 0 else part, interval='1d', start='1999-06-01',
                         group_by='ticker', auto_adjust=False, threads=True, progress=False)
        for t in part + (['^VIX'] if k == 0 else []):
            try:
                d = df[t].dropna(subset=['Close'])
            except KeyError:
                continue
            col = 'Close' if t == '^VIX' else 'Volume'
            out[t] = {ts.date().isoformat(): float(v) for ts, v in zip(d.index, d[col])}
    with open(VOL_CACHE, 'wb') as f:
        pickle.dump(out, f)
    return out


def roll_mean(x, w):
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0))
    out = np.full(len(x), np.nan)
    out[w - 1:] = (c[w:] - c[:-w]) / w
    return out


def roll_std(x, w):
    ok = np.isfinite(x)
    z = np.where(ok, x, 0.0)
    c1, c2, cn = (np.cumsum(np.insert(a, 0, 0.0)) for a in (z, z * z, ok.astype(float)))
    s1, s2, k = c1[w:] - c1[:-w], c2[w:] - c2[:-w], cn[w:] - cn[:-w]
    out = np.full(len(x), np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        v = (s2 - s1 * s1 / k) / (k - 1)
    out[w - 1:] = np.where(k >= w * 0.8, np.sqrt(np.maximum(v, 0)), np.nan)
    return out


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    vol = volumes(sorted(t for t, b in bars.items() if b))
    spy = np.array([b[4] for b in bench['SPY']])
    spy200 = roll_mean(spy, 200)
    vix = np.array([vol.get('^VIX', {}).get(d, np.nan) for d in cal])
    wd = [date.fromisoformat(d).weekday() for d in cal]
    fridays = [i for i in range(300, n - H) if cal[i] >= '2001-01-01' and wd[i + 1] <= wd[i]]

    rows = []   # one per (stock, Friday)
    print("computing features...", file=sys.stderr, flush=True)
    for t, bs in bars.items():
        if len(bs) < 300:
            continue
        O, Hh, L, C = (np.full(n, np.nan) for _ in range(4))
        for d, o, h, lo, c in bs:
            i = pos.get(d)
            if i is not None:
                O[i], Hh[i], L[i], C[i] = o, h, lo, c
        V = np.array([vol.get(t, {}).get(d, np.nan) for d in cal])
        blocked = blocked_dates(bs)
        with np.errstate(divide='ignore', invalid='ignore'):
            r1 = np.full(n, np.nan)
            r1[1:] = np.log(C[1:] / C[:-1])
            rv20, rv63 = roll_std(r1, 20) * math.sqrt(252), roll_std(r1, 63) * math.sqrt(252)
            tr = np.fmax(Hh - L, np.fmax(np.abs(Hh - np.roll(C, 1)), np.abs(L - np.roll(C, 1))))
            atr10, atr100 = roll_mean(tr / C, 10), roll_mean(tr / C, 100)
            ma50 = roll_mean(C, 50)
            v5, v60 = roll_mean(V, 5), roll_mean(V, 60)
            big1 = np.abs(r1) > 0.06
        for i in fridays:
            d = cal[i]
            if not (C[i] > 0 and C[i + H] > 0 and C[i - 260] > 0) or d in blocked or (t in sp and added.get(t, '0000') > d):
                continue
            if np.isnan(rv63[i]) or np.isnan(rv20[i]):
                continue
            hist = rv20[i - 252:i]
            hist = hist[~np.isnan(hist)]
            hi52 = np.nanmax(C[i - 252:i + 1])
            last_gap = next((k for k in range(1, 80) if big1[i - k]), 99)   # sessions since the last >6% day
            up_streak = 0
            while up_streak < 10 and r1[i - up_streak] > 0:
                up_streak += 1
            dn_streak = 0
            while dn_streak < 10 and r1[i - dn_streak] < 0:
                dn_streak += 1
            rows.append(dict(
                t=t, i=i, d=d, s=C[i], fwd=C[i + H] / C[i] - 1, iv=max(0.20, max(rv63[i], rv20[i]) + BUMP),
                squeeze=float(np.mean(hist <= rv20[i])) if len(hist) > 150 else np.nan,
                rv63=rv63[i], ret1m=C[i] / C[i - 21] - 1, mom=C[i - 21] / C[i - 126] - 1,
                off_high=C[i] / hi52 - 1, vs50=C[i] / ma50[i] - 1, range_ratio=atr10[i] / atr100[i],
                vol_surge=v5[i] / v60[i] if v60[i] > 0 else np.nan, gaps60=float(np.sum(big1[i - 59:i + 1])),
                last_gap=last_gap, up_streak=up_streak, dn_streak=dn_streak,
                spy_up=spy[i] > spy200[i], vix=vix[i], price=C[i]))
    print(f"{len(rows):,} stock-Fridays", file=sys.stderr, flush=True)
    # cross-sectional momentum percentile per Friday
    by_day = {}
    for r in rows:
        by_day.setdefault(r['i'], []).append(r)
    for rs in by_day.values():
        rs.sort(key=lambda r: r['mom'])
        for k, r in enumerate(rs):
            r['mom_pct'] = k / max(1, len(rs) - 1)
        rs.sort(key=lambda r: r['rv63'])
        for k, r in enumerate(rs):
            r['vol_pct'] = k / max(1, len(rs) - 1)

    # option returns at expiry (20 sessions ~ 28 days)
    for r in rows:
        c = bs_call(1.0, 1.0, T, r['iv'], RATE) * (1 + COST)
        p = (bs_call(1.0, 1.0, T, r['iv'], RATE) - 1 + math.exp(-RATE * T)) * (1 + COST)
        f = r['fwd']
        r['call'] = max(f, 0) / c - 1
        r['put'] = max(-f, 0) / p - 1
        r['strad'] = abs(f) / (c + p) - 1
        r['up'] = f >= BIG
        r['dn'] = f <= -BIG

    A = [r for r in rows if r['d'] < SPLIT]
    B = [r for r in rows if r['d'] >= SPLIT]

    def line(rs):
        if len(rs) < 200:
            return f"{len(rs):>7} {'(too few)':>34}"
        k = len(rs)
        return (f"{k:>7} {sum(r['up'] for r in rs) / k:5.1%} {sum(r['dn'] for r in rs) / k:5.1%} "
                f"{np.mean([r['call'] for r in rs]):+5.0%} {np.mean([r['put'] for r in rs]):+5.0%} "
                f"{np.mean([r['strad'] for r in rs]):+5.0%}")

    hdr = f"{'n':>7} {'up20':>5} {'dn20':>5} {'call':>5} {'put':>5} {'strad':>5}"
    print(f"\n{'pattern at the Friday close':40} | {'2001-2012':^34} | {'2013-2026':^34}")
    print(f"{'':40} | {hdr} | {hdr}")
    print(f"{'ALL':40} | {line(A)} | {line(B)}")

    def show(title, buckets):
        print(f"-- {title}")
        for label, fn in buckets:
            print(f"   {label:37} | {line([r for r in A if fn(r)])} | {line([r for r in B if fn(r)])}")

    show("quiet vs wild (20-day swings vs its own past year)", [
        ("quietest 10% of its year (squeeze)", lambda r: r['squeeze'] <= 0.10),
        ("10-50%", lambda r: 0.10 < r['squeeze'] <= 0.5),
        ("50-90%", lambda r: 0.5 < r['squeeze'] <= 0.9),
        ("wildest 10% of its year", lambda r: r['squeeze'] > 0.9)])
    show("how volatile vs other stocks (63-day)", [
        ("calmest 20%", lambda r: r['vol_pct'] <= 0.2), ("middle", lambda r: 0.2 < r['vol_pct'] <= 0.8),
        ("wildest 20%", lambda r: r['vol_pct'] > 0.8), ("wildest 5%", lambda r: r['vol_pct'] > 0.95)])
    show("6-1 month strength vs other stocks", [
        ("weakest 10%", lambda r: r['mom_pct'] <= 0.1), ("10-90%", lambda r: 0.1 < r['mom_pct'] <= 0.9),
        ("strongest 10%", lambda r: r['mom_pct'] > 0.9), ("strongest 2% (~top 10)", lambda r: r['mom_pct'] > 0.98)])
    show("last month's move", [
        ("down 20%+", lambda r: r['ret1m'] <= -0.2), ("down 10-20%", lambda r: -0.2 < r['ret1m'] <= -0.1),
        ("-10% to +10%", lambda r: -0.1 < r['ret1m'] < 0.1), ("up 10-20%", lambda r: 0.1 <= r['ret1m'] < 0.2),
        ("up 20%+", lambda r: r['ret1m'] >= 0.2)])
    show("distance from the 52-week high", [
        ("at the high (within 2%)", lambda r: r['off_high'] >= -0.02), ("2-15% below", lambda r: -0.15 <= r['off_high'] < -0.02),
        ("15-40% below", lambda r: -0.4 <= r['off_high'] < -0.15), ("40%+ below", lambda r: r['off_high'] < -0.4)])
    show("stretch vs 50-day average", [
        ("15%+ below", lambda r: r['vs50'] <= -0.15), ("within 5%", lambda r: abs(r['vs50']) < 0.05),
        ("15-30% above", lambda r: 0.15 <= r['vs50'] < 0.3), ("30%+ above", lambda r: r['vs50'] >= 0.3)])
    show("daily ranges, last 10 days vs last 100", [
        ("very tight (under 0.6x)", lambda r: r['range_ratio'] < 0.6), ("normal (0.8-1.2x)", lambda r: 0.8 <= r['range_ratio'] <= 1.2),
        ("wide (over 1.6x)", lambda r: r['range_ratio'] > 1.6)])
    show("volume, last 5 days vs last 60", [
        ("dried up (under 0.6x)", lambda r: r['vol_surge'] < 0.6), ("normal", lambda r: 0.8 <= r['vol_surge'] <= 1.2),
        ("surge (2x+)", lambda r: r['vol_surge'] >= 2), ("huge surge (3x+)", lambda r: r['vol_surge'] >= 3)])
    show("6%+ days in the last 60 sessions", [
        ("none", lambda r: r['gaps60'] == 0), ("1-2", lambda r: 1 <= r['gaps60'] <= 2), ("5+", lambda r: r['gaps60'] >= 5)])
    show("earnings clock (last 6%+ day ~ one quarter ago)", [
        ("last big day 55-62 sessions ago", lambda r: 55 <= r['last_gap'] <= 62),
        ("last big day 1-10 sessions ago", lambda r: r['last_gap'] <= 10),
        ("no big day in 80 sessions", lambda r: r['last_gap'] == 99)])
    show("streaks", [
        ("5+ up days in a row", lambda r: r['up_streak'] >= 5), ("5+ down days in a row", lambda r: r['dn_streak'] >= 5)])
    show("market", [
        ("SPY above 200-day", lambda r: r['spy_up']), ("SPY below 200-day", lambda r: not r['spy_up']),
        ("VIX under 15", lambda r: r['vix'] < 15), ("VIX 15-25", lambda r: 15 <= r['vix'] < 25),
        ("VIX 25-35", lambda r: 25 <= r['vix'] < 35), ("VIX 35+", lambda r: r['vix'] >= 35)])
    show("price", [("under $20", lambda r: r['price'] < 20), ("$20-100", lambda r: 20 <= r['price'] < 100),
                   ("$100+", lambda r: r['price'] >= 100)])

    # combinations built from the single patterns that held up in BOTH periods
    show("combos", [
        ("squeeze + at 52w high", lambda r: r['squeeze'] <= 0.2 and r['off_high'] >= -0.02),
        ("squeeze + top 10% strength", lambda r: r['squeeze'] <= 0.2 and r['mom_pct'] > 0.9),
        ("top 10% strength + SPY up", lambda r: r['mom_pct'] > 0.9 and r['spy_up']),
        ("top 10% strength + at high + SPY up", lambda r: r['mom_pct'] > 0.9 and r['off_high'] >= -0.02 and r['spy_up']),
        ("top 10% str + at high + SPY up + VIX<20", lambda r: r['mom_pct'] > 0.9 and r['off_high'] >= -0.02 and r['spy_up'] and r['vix'] < 20),
        ("down 20%+ last month + VIX 35+", lambda r: r['ret1m'] <= -0.2 and r['vix'] >= 35),
        ("40%+ off high + SPY below 200", lambda r: r['off_high'] < -0.4 and not r['spy_up']),
        ("weakest 10% + SPY below 200", lambda r: r['mom_pct'] <= 0.1 and not r['spy_up']),
        ("weakest 10% + SPY below + VIX<25", lambda r: r['mom_pct'] <= 0.1 and not r['spy_up'] and r['vix'] < 25),
        ("wildest 20% + VIX under 15", lambda r: r['vol_pct'] > 0.8 and r['vix'] < 15),
        ("quiet + earnings clock", lambda r: r['squeeze'] <= 0.3 and 55 <= r['last_gap'] <= 62),
        ("calm stock + earnings clock", lambda r: r['vol_pct'] <= 0.3 and 55 <= r['last_gap'] <= 62),
        ("volume surge + at 52w high", lambda r: r['vol_surge'] >= 2 and r['off_high'] >= -0.02),
        ("volume surge + 15%+ below 50-day", lambda r: r['vol_surge'] >= 2 and r['vs50'] <= -0.15),
    ])

    # the one pattern that paid in both periods, panic by panic
    print("\nCalls on stocks down 20%+ in a month while VIX is 35+, by month (each row = one panic):")
    ep = {}
    for r in rows:
        if r['ret1m'] <= -0.2 and r['vix'] >= 35:
            ep.setdefault(r['d'][:7], []).append(r)
    for m, rs in sorted(ep.items()):
        print(f"   {m}  {len(rs):5} signals  VIX {np.mean([r['vix'] for r in rs]):4.0f}  stock {np.mean([r['fwd'] for r in rs]):+6.1%}  "
              f"call {np.mean([r['call'] for r in rs]):+6.0%}  calls that won {np.mean([r['call'] > 0 for r in rs]):4.0%}")

    # the profile: average reading just BEFORE big moves vs everything else
    print("\nWhat the stock looked like at the Friday close before ... (all years)")
    keys = [('squeeze', 'swings vs own year (0=quietest)', '{:.2f}'), ('vol_pct', 'volatility rank vs others', '{:.2f}'),
            ('mom_pct', '6-1 strength rank', '{:.2f}'), ('ret1m', 'last month', '{:+.1%}'),
            ('off_high', 'below 52w high', '{:+.1%}'), ('vs50', 'vs 50-day avg', '{:+.1%}'),
            ('range_ratio', 'daily range 10d/100d', '{:.2f}'), ('vol_surge', 'volume 5d/60d', '{:.2f}'),
            ('gaps60', '6%+ days in last 60', '{:.1f}'), ('spy_up', 'SPY above 200-day', '{:.0%}'), ('vix', 'VIX', '{:.1f}'),
            ('price', 'price', '${:.0f}')]
    groups = [('big up', [r for r in rows if r['up']]), ('big down', [r for r in rows if r['dn']]),
              ('everything else', [r for r in rows if not r['up'] and not r['dn']])]
    print(f"   {'':34} " + ' '.join(f"{g:>16}" for g, _ in groups))
    for k, label, fmt in keys:
        vals = []
        for _, rs in groups:
            x = np.array([float(r[k]) for r in rs], float)
            vals.append(fmt.format(np.nanmedian(x) if k not in ('spy_up',) else np.nanmean(x)))
        print(f"   {label:34} " + ' '.join(f"{v:>16}" for v in vals))
    print(f"   {'count':34} " + ' '.join(f"{len(rs):>16,}" for _, rs in groups))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Panic-rebound calls, but only once the stock turns up (higher high + higher low).

Signal (scripts/study_big_moves.py): at a Friday close VIX is 35+ and the
stock is down 20%+ over the last month -> it goes on a watch list for 40
sessions. Variants:
  right away     buy at the next session's close (the earlier test)
  hi-hi daily    wait until its DAILY chart shows higher highs and higher lows
                 (the last 2 labeled swings HH/HL; swing = 3 bars each side,
                 the same read as the dashboard's lo-lo check), buy at the
                 next session's close
  hi-hi fast     same with 2-bar swings (turns sooner, more false starts)
Hourly bars would be a smaller time frame, but Yahoo keeps only ~2 years of
them (one panic: Apr 2025), so the daily chart is the smallest testable here.

Calls: 90-day, delta 0.70 (in the money) or 0.50 (at the money). Exits:
  hold      sell 21 days before expiry
  lo-lo     sell when the daily chart turns to lower highs + lower lows (or 21 days before expiry)
  +100%     take profit at +100% (or 21 days before expiry)
Priced with Black-Scholes from the higher of 20- and 63-day realized volatility
+ 10 points (floor 20%) - in a panic real option prices jump at once - 4% rate,
2% bid/ask each way. "[pricier]" uses +25 points.

Account: options only, 5% or 10% of the account per call, at most 10 open,
cash at 0%.

Usage:
    python scripts/backtest_panic_hihi.py
"""
import math
import os
import statistics
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import START, load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.options_sim import bs_call, strike_for_delta  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402
from study_big_moves import roll_std, volumes  # noqa: E402

RATE, SPREAD, TENOR, ROLL_AT, WATCH, VIX_MIN, DROP = 0.04, 0.02, 90, 21, 40, 35, -0.20


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    pos = {d: i for i, d in enumerate(cal)}
    vix_px = volumes(sorted(bars)).get('^VIX', {})
    vix = np.array([vix_px.get(d, np.nan) for d in cal])
    wd = [date.fromisoformat(d).weekday() for d in cal]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    C, V, J = {}, {}, {}
    for t, bs in bars.items():
        if len(bs) < 300:
            continue
        c = np.full(n, np.nan)
        j = np.full(n, -1)
        for k, b in enumerate(bs):
            i = pos.get(b[0])
            if i is not None:
                c[i], j[i] = b[4], k
        last, lastj = np.nan, -1
        for i in range(n):          # carry forward over gaps
            if np.isnan(c[i]):
                c[i], j[i] = last, lastj
            last, lastj = c[i], j[i]
        r = np.full(n, np.nan)
        with np.errstate(divide='ignore', invalid='ignore'):
            r[1:] = np.log(c[1:] / c[:-1])
        C[t], J[t] = c, j
        V[t] = np.fmax(roll_std(r, 20), roll_std(r, 63)) * math.sqrt(252)

    # Friday panic qualifiers
    qual = {}   # ticker -> sorted list of qualifying Friday indexes
    first = pos[START] if START in pos else 300
    for i in range(max(first, 300), n - 1):
        if wd[i + 1] > wd[i] or not vix[i] >= VIX_MIN:
            continue
        for t, c in C.items():
            d = cal[i]
            if d in blocked[t] or (t in sp and added.get(t, '0000') > d):
                continue
            if c[i] > 0 and c[i - 21] > 0 and c[i - 260] > 0 and c[i] / c[i - 21] - 1 <= DROP:
                qual.setdefault(t, []).append(i)
    print(f"{sum(len(v) for v in qual.values())} stock-Fridays qualify ({len(qual)} stocks)", flush=True)

    scache = {}

    def state(t, i, nb):
        key = (t, i, nb)
        if key not in scache:
            k = J[t][i]
            bs = bars[t][max(0, k - 150):k + 1]
            scache[key] = structure_signal([tuple(b) for b in bs], n=nb, lookback=2)['state'] if k >= 0 else None
        return scache[key]

    def entries(mode):
        """[(ticker, entry index)] - one trade per watch streak (a new qualifying Friday after the exit starts a new one)."""
        out = []
        for t, fr in qual.items():
            k, busy_until = 0, -1
            while k < len(fr):
                q = fr[k]
                if q < busy_until:
                    k += 1
                    continue
                if mode == 'now':
                    e = q + 1
                else:
                    nb = 3 if mode == 'daily' else 2
                    e = None
                    last_q = q
                    i = q
                    while i < min(n - 2, last_q + WATCH):
                        if state(t, i, nb) == 'uptrend':
                            e = i + 1
                            break
                        i += 1
                        while k + 1 < len(fr) and fr[k + 1] <= i:   # re-qualifying extends the watch
                            k += 1
                            last_q = fr[k]
                if e is not None and e < n:
                    out.append((t, e))
                    busy_until = e + 60
                k += 1
        return sorted(out, key=lambda x: x[1])

    def expiry(d):
        return date.fromordinal(date.fromisoformat(d).toordinal() + TENOR).isoformat()

    def trade(t, e, delta, exit_rule, bump):
        """Daily value path of one call per $1 paid: [(index, value)], last = sale."""
        s, v = C[t][e], max(0.20, V[t][e] + bump)
        if not s > 0 or np.isnan(v):
            return None
        exp = expiry(cal[e])
        k = strike_for_delta(s, TENOR / 365, v, RATE, delta)
        cost = bs_call(s, k, TENOR / 365, v, RATE) * (1 + SPREAD)
        path = []
        for i in range(e, n):
            left = (date.fromisoformat(exp) - date.fromisoformat(cal[i])).days
            vi = max(0.20, (V[t][i] if not np.isnan(V[t][i]) else v - bump) + bump)
            mid = bs_call(C[t][i], k, max(0, left) / 365, vi, RATE) / cost
            done = left <= ROLL_AT or i == n - 1
            if i > e and exit_rule == 'lolo' and state(t, i, 3) == 'downtrend':
                done = True
            if i > e and exit_rule == 'tp' and mid * (1 - SPREAD) >= 2.0:
                done = True
            if done:
                path.append((i, mid * (1 - SPREAD)))
                return path
            path.append((i, mid))
        return path

    def account(trades, risk, max_open=10):
        """trades: [(entry index, path)]."""
        by_entry = {}
        for e, p in trades:
            by_entry.setdefault(e, []).append(p)
        cash, open_, curve = 100.0, [], []
        start = pos.get(START, 0)
        for i in range(start, n):
            still = []
            for o in open_:
                val = o['path'].get(i)
                if val is None:
                    still.append(o)
                    continue
                o['val'] = val
                if i == o['end']:
                    cash += o['units'] * val
                else:
                    still.append(o)
            open_ = still
            acct = cash + sum(o['units'] * o['val'] for o in open_)
            for p in by_entry.get(i, []):
                if len(open_) >= max_open:
                    break
                spend = min(cash, acct * risk)
                if spend < acct * risk * 0.5:
                    continue
                cash -= spend
                pd = dict(p)
                open_.append(dict(path=pd, end=p[-1][0], units=spend, val=pd[i]))
            curve.append((cal[i], cash + sum(o['units'] * o['val'] for o in open_)))
        return curve

    modes = [('right away', 'now'), ('hi-hi daily', 'daily'), ('hi-hi fast', 'fast')]
    E = {m: entries(m) for _, m in modes}
    for lab, m in modes:
        print(f"  {lab:12} {len(E[m])} trades")
    print(f"\n{'per trade (call value at sale per $1 paid)':44} {'trades':>6} {'win%':>5} {'avg':>6} {'median':>7} {'best':>6} | "
          f"{'acct 5%':>8} {'/yr':>5} {'worst':>6} | {'acct 10%':>8} {'/yr':>5} {'worst':>6}")
    results = {}
    for lab, m in modes:
        for delta, dl in ((0.70, 'ITM'), (0.50, 'ATM')):
            for ex, el in (('hold', 'hold'), ('lolo', 'lo-lo exit'), ('tp', '+100%')):
                for bump, bl in ((0.10, ''), (0.25, ' [pricier]')):
                    if bl and not (delta == 0.70 and ex == 'lolo'):
                        continue
                    tr = [(e, trade(t, e, delta, ex, bump)) for t, e in E[m]]
                    tr = [(e, p) for e, p in tr if p]
                    rets = [p[-1][1] - 1 for _, p in tr]
                    a5, a10 = account(tr, 0.05), account(tr, 0.10)
                    s5, s10 = curve_stats([v for _, v in a5]), curve_stats([v for _, v in a10])
                    label = f"{lab}, {dl}, {el}{bl}"
                    results[label] = (tr, a10)
                    print(f"{label:44} {len(rets):6} {sum(1 for x in rets if x > 0) / len(rets):5.0%} {statistics.mean(rets):+6.0%} "
                          f"{statistics.median(rets):+7.0%} {max(rets):+6.0%} | {s5['total']:+8.0%} {s5['annual']:+5.0%} {s5['maxDD']:6.0%} | "
                          f"{s10['total']:+8.0%} {s10['annual']:+5.0%} {s10['maxDD']:6.0%}", flush=True)
        print()

    # panic by panic for the main comparison
    show = ['right away, ITM, hold', 'hi-hi daily, ITM, hold', 'hi-hi daily, ITM, lo-lo exit', 'hi-hi fast, ITM, lo-lo exit']
    months = sorted({cal[e][:7] for lab in show for e, _ in results[lab][0]})
    eps, cur = [], None
    for m in months:   # group months less than 3 apart into one panic
        y, mo = int(m[:4]), int(m[5:])
        k = y * 12 + mo
        if cur and k - cur[-1] <= 3:
            cur.append(k)
        else:
            cur = [k]
            eps.append(cur)
    print("By panic (entries in that stretch): trades / avg per $1 / % winners")
    print(f"   {'panic':17} " + ' | '.join(f"{s[:26]:^26}" for s in show))
    for ep in eps:
        a = f"{(ep[0] - 1) // 12}-{(ep[0] - 1) % 12 + 1:02d}"
        lo, hi = min(ep), max(ep)
        cells = []
        for lab in show:
            rs = [p[-1][1] - 1 for e, p in results[lab][0] if lo <= int(cal[e][:4]) * 12 + int(cal[e][5:7]) <= hi]
            cells.append(f"{len(rs):4} {statistics.mean(rs):+6.0%} {sum(1 for x in rs if x > 0) / len(rs):5.0%}".center(26) if rs else ' ' * 26)
        print(f"   {a:7}{'+' + str(hi - lo) + 'mo' if hi > lo else '':10} " + ' | '.join(cells))

    years = sorted({d[:4] for d in cal[pos.get(START, 0):]})
    print(f"\n{'account 10% per call, by year':40} " + ' '.join(f"{y[2:]:>5}" for y in years))
    for lab in show:
        c = results[lab][1]
        ye, prev, ys = {}, c[0][1], []
        for d, v in c:
            ye[d[:4]] = v
        for y in years:
            ys.append(f"{ye[y] / prev - 1:+5.0%}" if abs(ye[y] / prev - 1) > 0.005 else f"{'':>5}")
            prev = ye[y]
        print(f"{lab:40} " + ' '.join(ys))


if __name__ == '__main__':
    main()

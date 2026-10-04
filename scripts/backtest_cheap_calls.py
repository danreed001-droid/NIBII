#!/usr/bin/env python3
"""Calls on stocks that are QUIET (cheap options) but about to move - vs calls on the top 5.

Signals, checked every Friday on the dashboard's universe (S&P 500 + Nasdaq-100),
call bought at Monday's close (the next session), at most 3 new trades a week
(strongest 6-1 month score first, never two open on the same stock, at most
5 open at once - like the top 5, so at most ~half the account is in calls):

  1 squeeze   - the stock's 20-day volatility sank into the lowest 20% of its own
                past year, and this week it closed at a new 52-week closing high
                (a breakout out of the quiet spell).
  2 early     - 6-1 month strength ranked 10-30 (beats SPY, not yet top 5-9) and
                63-day volatility below the universe median (calm = cheaper calls).
  1+2 both    - a squeeze breakout on a stock that beats SPY on 6-1 strength and
                ranks in the top 50.
  1 or 2      - every trade from either signal (same 3-a-week cap).
  top 5       - the reference: a call each time a stock ENTERS the top 5, closed
                when the model drops it (the best trade from the earlier test).

Options: 90-day calls, delta 0.70 (in the money), 0.50 (at the money) or
0.30 (out of the money, the cheap ones). Closed 21 days before expiry, or the
"TP/SL" version: +100% take profit / -50% stop. No historical option prices
exist, so they are Black-Scholes priced from the stock's 63-day realized
volatility + 10 points (floor 20%), 4% rate, 2% bid/ask each way. Quiet stocks'
real options usually cost MORE than their recent swings suggest, so the best
rows are re-run with a 20-point cushion ("pricier").

Account: options only, 10% of the account on each new call (the premium is the
most it can lose), the rest in cash at 0%.

Usage:
    python scripts/backtest_cheap_calls.py
"""
import math
import os
import statistics
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.options_sim import bs_call, strike_for_delta  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

RATE, SPREAD, RISK, PER_WEEK, TENOR, MAX_OPEN = 0.04, 0.02, 0.10, 3, 90, 5
SQUEEZE_PCT, EARLY = 0.20, (10, 30)


def rolling_vol(c, w):
    """Annualized std of daily log returns over the last w sessions (nan until enough data)."""
    r = np.full(len(c), np.nan)
    r[1:] = np.log(c[1:] / c[:-1])
    out = np.full(len(c), np.nan)
    for i in range(w, len(c)):
        x = r[i - w + 1:i + 1]
        x = x[~np.isnan(x)]
        if len(x) >= w * 0.8:
            out[i] = x.std(ddof=1) * math.sqrt(252)
    return out


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    px = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    px.update({t: {b[0][:10]: b[4] for b in bs} for t, bs in extra.items()})
    px['SPY'] = dict(bench['SPY'])
    cal = [d for d, _ in bench['SPY']]
    n = len(cal)

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    stocks = [t for t in px if t != 'SPY']
    C = {}
    for t in stocks + ['SPY']:
        last, s = np.nan, np.empty(n)
        for i, d in enumerate(cal):
            v = px[t].get(d)
            last = v if v else last
            s[i] = last
        C[t] = s
    print(f"computing volatility for {len(stocks)} stocks...", flush=True)
    V20 = {t: rolling_vol(C[t], 20) for t in stocks}
    V63 = {t: rolling_vol(C[t], 63) for t in stocks}

    def score(t, i):
        a, b = C[t][i - 21], C[t][i - 126]
        return a / b - 1 if a > 0 and b > 0 else None

    fridays = [i for i in range(300, n - 1)
               if cal[i] >= START and (i + 1 == n or date.fromisoformat(cal[i + 1]).weekday() <= date.fromisoformat(cal[i]).weekday())]

    sig = {'1 squeeze': {}, '2 early': {}, '1+2 both': {}, '1 or 2': {}}
    for i in fridays:
        d = cal[i]
        spy = score('SPY', i)
        ranked = []
        for t in stocks:
            if not member(t, d) or np.isnan(C[t][i - 260]):
                continue
            s = score(t, i)
            if s is not None and spy is not None and s > spy:
                ranked.append((s, t))
        ranked.sort(reverse=True)
        rank = {t: k + 1 for k, (_, t) in enumerate(ranked)}
        sc = {t: s for s, t in ranked}
        vols = [V63[t][i] for _, t in ranked if not np.isnan(V63[t][i])]
        med = statistics.median(vols) if vols else 0
        squeeze, early = [], []
        for t in stocks:
            if not member(t, d) or np.isnan(C[t][i - 260]):
                continue
            c = C[t]
            # breakout this week to a new 52-week closing high, out of a quiet spell before it
            prior = np.nanmax(c[i - 256:i - 4])
            if not (np.nanmax(c[i - 4:i + 1]) > prior and c[i] >= prior):
                continue
            v_before, hist = V20[t][i - 5], V20[t][i - 257:i - 5]
            hist = hist[~np.isnan(hist)]
            if np.isnan(v_before) or len(hist) < 150 or np.mean(hist <= v_before) > SQUEEZE_PCT:
                continue
            squeeze.append(t)
        for t, r in rank.items():
            if EARLY[0] <= r <= EARLY[1] and V63[t][i] < med:
                early.append(t)
        by = lambda xs: sorted(xs, key=lambda t: -(sc.get(t) if sc.get(t) is not None else (score(t, i) or -9)))  # noqa: E731
        sig['1 squeeze'][i] = by(squeeze)
        sig['2 early'][i] = by(early)
        sig['1+2 both'][i] = by([t for t in squeeze if rank.get(t, 999) <= 50])
        sig['1 or 2'][i] = by(list(dict.fromkeys(squeeze + early)))

    # reference: top-5 entries (trade at Monday's close), closed when the model drops them
    r = run_momentum(px, cal, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    idx = {d: i for i, d in enumerate(cal)}
    episodes, prev, open_at = [], [], {}
    for d, held in r['picks']:
        for t in held:
            if t not in prev:
                open_at[t] = d
        for t in prev:
            if t not in held:
                episodes.append((t, idx[open_at.pop(t)], idx[d]))
        prev = held
    for t, d in open_at.items():
        episodes.append((t, idx[d], None))

    def trades_for(name):
        """(ticker, entry index, forced exit index or None), entries at the session after Friday."""
        if name == 'top 5':
            return sorted(episodes, key=lambda e: e[1])
        out = []
        for i, cands in sig[name].items():
            for t in cands[:PER_WEEK * 3]:
                out.append((t, i + 1, None))
        return out

    def run(name, strike, tp=None, sl=None, bump=0.10, risk=RISK):
        trades = trades_for(name)
        entries = {}
        for e in trades:
            entries.setdefault(e[1], []).append(e)

        def iv(t, i):
            v = V63[t][i]
            return max(0.20, (0.30 if np.isnan(v) else v) + bump)

        cash, openp, curve, rets, stock_rets = 100.0, [], [], [], []
        first = min(idx[START], trades[0][1])
        for i in range(first, n):
            d = cal[i]
            keep = []
            for p in openp:
                s, tt = C[p['t']][i], max(0.0, days(d, p['exp']) / 365)
                mid = bs_call(s, p['k'], tt, iv(p['t'], i), RATE)
                bid = mid * (1 - SPREAD)
                why = (p['out'] is not None and i >= p['out']) or days(d, p['exp']) <= 21 \
                    or (tp is not None and bid >= p['cost'] * (1 + tp)) or (sl is not None and bid <= p['cost'] * (1 - sl))
                if why:
                    cash += p['n'] * bid
                    rets.append(bid / p['cost'] - 1)
                    stock_rets.append(s / p['s0'] - 1)
                else:
                    p['mid'] = mid
                    keep.append(p)
            openp = keep
            acct = cash + sum(p['n'] * p['mid'] for p in openp)
            todo = entries.get(i, [])
            if name != 'top 5':
                held = {p['t'] for p in openp}
                todo = [e for e in todo if e[0] not in held][:max(0, min(PER_WEEK, MAX_OPEN - len(openp)))]
            for t, _, out in todo:
                s, v = C[t][i], iv(t, i)
                if not s > 0:
                    continue
                tt = TENOR / 365
                k = strike_for_delta(s, tt, v, RATE, strike)
                mid = bs_call(s, k, tt, v, RATE)
                cost = mid * (1 + SPREAD)
                spend = min(cash, acct * risk)
                if cost <= 0 or spend < acct * risk * 0.5:
                    continue
                cash -= spend
                exp_d = date.fromordinal(date.fromisoformat(d).toordinal() + TENOR).isoformat()
                openp.append(dict(t=t, k=k, exp=exp_d, cost=cost, n=spend / cost, out=out, mid=mid, s0=s))
            curve.append((d, cash + sum(p['n'] * p['mid'] for p in openp)))
        return rets, stock_rets, curve

    names_ = ['1 squeeze', '2 early', '1+2 both', '1 or 2', 'top 5']
    for nm in names_[:4]:
        cnt = sum(len(v[:PER_WEEK]) for v in sig[nm].values())
        weeks = sum(1 for v in sig[nm].values() if v)
        print(f"  {nm:10} signals on {weeks} of {len(sig[nm])} Fridays (up to {cnt} trades before the cash limit)")
    print()
    labels = {0.70: 'ITM d.70', 0.50: 'ATM d.50', 0.30: 'OTM d.30 (cheap)'}
    print(f"{'90-day calls, 10% per trade':38} {'trades':>6} {'win%':>5} {'per $1':>7} {'median':>7} {'best':>6} "
          f"{'stock':>6} | {'total':>8} {'/yr':>5} {'worst':>6}")
    rows = []
    for nm in names_:
        for strike in (0.70, 0.50, 0.30):
            for tp, sl in ((None, None), (1.0, 0.5)):
                rets, srets, curve = run(nm, strike, tp, sl)
                st = curve_stats([v for _, v in curve])
                label = f"{nm}: {labels[strike]}" + (' TP/SL' if tp else '')
                rows.append((label, nm, strike, tp, st, curve))
                print(f"{label:38} {len(rets):6} {sum(1 for x in rets if x > 0) / len(rets):5.0%} {statistics.mean(rets):+7.0%} "
                      f"{statistics.median(rets):+7.0%} {max(rets):+6.0%} {statistics.mean(srets):+6.1%} | "
                      f"{st['total']:+8.0%} {st['annual']:+5.0%} {st['maxDD']:6.0%}", flush=True)
        print()

    best = {}
    for row in rows:
        if row[1] not in best or row[4]['annual'] > best[row[1]][4]['annual']:
            best[row[1]] = row
    print("Pricier options (cushion 20 points instead of 10) for each signal's best row:")
    pricier = {}
    for nm, (label, _, strike, tp, st, _) in best.items():
        rets, _, curve = run(nm, strike, tp, 0.5 if tp else None, bump=0.20)
        s2 = curve_stats([v for _, v in curve])
        pricier[nm] = (label, curve)
        print(f"  {label:38} per $1 {statistics.mean(rets):+5.0%}  account {s2['total']:+8.0%} "
              f"({s2['annual']:+.0%}/yr, worst {s2['maxDD']:.0%})   was {st['annual']:+.0%}/yr")

    import json
    scan = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'momentum_scan.json')))
    table = {f"{best[nm][0]}": best[nm][5] for nm in names_}
    table.update({f"{lab} [pricier]": c for lab, c in pricier.values()})
    table['current setup (auto mix, stock)'] = scan['curves']['plan']
    for b in ('SPY', 'QQQ'):
        table['buy & hold ' + b] = [[d, v] for d, v in bench[b] if d >= START]
    years = sorted({d[:4] for d in cal if d >= START})
    print(f"\n{'by year, since 2020':52} {'total':>9} {'/yr':>5} {'worst':>6} | " + ' '.join(f"{y:>6}" for y in years))
    for label, c in table.items():
        c = [(d, v) for d, v in c if d >= START]
        st = curve_stats([v for _, v in c])
        ye, prev, ys = {}, c[0][1], []
        for d, v in c:
            ye[d[:4]] = v
        for y in years:
            if y in ye:
                ys.append(f"{ye[y] / prev - 1:+6.0%}")
                prev = ye[y]
            else:
                ys.append(f"{'':>6}")
        print(f"{label:52} {st['total']:+9.0%} {st['annual']:+5.0%} {st['maxDD']:6.0%} | " + ' '.join(ys), flush=True)


if __name__ == '__main__':
    main()

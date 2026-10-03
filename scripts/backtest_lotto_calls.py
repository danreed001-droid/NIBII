#!/usr/bin/env python3
"""Cheap far out-of-the-money calls ("lottery tickets") on new top-5 entries, since 2020.

Each time a stock enters the top 5 (dashboard rule; signal Friday, trade at
Monday's close) one call is bought with its strike set so the call costs only
1%, 2% or 3% of the stock price; expiry 30 / 60 / 90 / 180 days. The trade
ends when the model drops the stock or 7 days before expiry - or earlier at a
5x / 10x / 25x take-profit target in those versions.

Reports how often the call ever reached 5x, 10x and 25x its cost, the average
result per $1 for each exit rule, and an account that risks 1% or 2% of its
value per ticket (rest in cash at 0%). Black-Scholes pricing from 63-day
realized volatility + 10 points (floor 20%), flat across strikes - real
out-of-the-money calls are often priced differently (skew) and have wide
bid/ask spreads, so 5% is paid each way here.

Usage:
    python scripts/backtest_lotto_calls.py
"""
import math
import os
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.options_sim import bs_call  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

RATE, SPREAD = 0.04, 0.05


def realized(s, i, window=63):
    rets = [math.log(s[j] / s[j - 1]) for j in range(max(1, i - window + 1), i + 1) if s[j - 1] and s[j]]
    if len(rets) < 10:
        return 0.4
    m = sum(rets) / len(rets)
    return math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1) * 252)


def strike_for_cost(s, t, vol, frac):
    """Strike whose call (ask) costs `frac` of the stock price."""
    lo, hi = s, s * 10
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs_call(s, mid, t, vol, RATE) * (1 + SPREAD) > frac * s:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


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
    idx = {d: i for i, d in enumerate(cal)}

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    r = run_momentum(px, cal, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    episodes, prev, open_at = [], [], {}
    for d, held in r['picks']:
        for t in held:
            if t not in prev:
                open_at[t] = d
        for t in prev:
            if t not in held:
                episodes.append((t, open_at.pop(t), d))
        prev = held
    episodes += [(t, d, None) for t, d in open_at.items()]
    episodes.sort(key=lambda e: e[1])
    series = {}
    for t in {e[0] for e in episodes}:
        last, s = None, []
        for d in cal:
            last = px[t].get(d) or last
            s.append(last)
        series[t] = s

    def paths(tenor, frac, bump=0.10):
        """Per trade: (entry day, cost, [(day, bid)] until the trade's natural end)."""
        out = []
        for t, d0, dx in episodes:
            i0 = idx[d0]
            s0 = series[t][i0]
            v0 = max(0.20, realized(series[t], i0) + bump)
            exp = date.fromordinal(date.fromisoformat(d0).toordinal() + tenor)
            k = strike_for_cost(s0, tenor / 365, v0, frac)
            cost = bs_call(s0, k, tenor / 365, v0, RATE) * (1 + SPREAD)
            path = []
            for i in range(i0 + 1, len(cal)):
                d = cal[i]
                left = (exp - date.fromisoformat(d)).days
                v = max(0.20, realized(series[t], i) + bump)
                bid = bs_call(series[t][i], k, max(0, left) / 365, v, RATE) * (1 - SPREAD)
                path.append((d, bid))
                if d == dx or left <= 7:
                    break
            if path:
                out.append((d0, cost, path, k / s0 - 1, t))
        return out

    def exit_ret(cost, path, target):
        for _, bid in path:
            if target and bid >= cost * target:
                return bid / cost - 1, True
        return path[-1][1] / cost - 1, False

    def account(trades, target, risk):
        """Risk `risk` of the account per ticket; returns the account curve stats."""
        cash, openp, curve = 100.0, [], []
        by_day = {}
        for tr in trades:
            by_day.setdefault(tr[0], []).append(tr)
        ends = {}
        for d in cal:
            if d < trades[0][0]:
                continue
            # close tickets whose exit day is today
            keep = []
            for p in openp:
                bid = p['bids'].get(d)
                if bid is not None:
                    p['last'] = bid
                if d == p['end']:
                    cash += p['n'] * p['last']
                else:
                    keep.append(p)
            openp = keep
            acct = cash + sum(p['n'] * p['last'] for p in openp)
            for d0, cost, path, _, _ in by_day.get(d, []):
                end = path[-1][0]
                for dd, bid in path:
                    if target and bid >= cost * target:
                        end = dd
                        break
                spend = min(cash, acct * risk)
                if spend <= 0:
                    continue
                cash -= spend
                openp.append(dict(n=spend / cost, last=cost / (1 + SPREAD) * (1 - SPREAD), end=end,
                                  bids={dd: b for dd, b in path if dd <= end}))
            curve.append(cash + sum(p['n'] * p['last'] for p in openp))
        return curve_stats(curve)

    print(f"{len(episodes)} new top-5 entries since {START}; one cheap call each (5% bid/ask paid each way)\n")
    print(f"{'ticket':26} {'OTM by':>7} {'ever 5x':>8} {'10x':>5} {'25x':>5} | {'per $1 if held':>14} {'sell@5x':>8} {'sell@10x':>9} {'sell@25x':>9} | "
          f"{'1%/ticket acct':>14} {'2%/ticket':>10}")
    for tenor in (30, 60, 90, 180):
        for frac in (0.01, 0.02, 0.03):
            tr = paths(tenor, frac)
            peaks = [max(b for _, b in p) / c for _, c, p, _, _ in tr]
            otm = statistics.median(x[3] for x in tr)
            held = statistics.mean(exit_ret(c, p, None)[0] for _, c, p, _, _ in tr)
            res = {m: statistics.mean(exit_ret(c, p, m)[0] for _, c, p, _, _ in tr) for m in (5, 10, 25)}
            best_m = max(res, key=res.get)
            a1, a2 = account(tr, best_m if res[best_m] > held else None, 0.01), account(tr, best_m if res[best_m] > held else None, 0.02)
            print(f"{tenor:>3}d, costs {frac:.0%} of price  {otm:+7.0%} {sum(x >= 5 for x in peaks) / len(tr):8.1%} "
                  f"{sum(x >= 10 for x in peaks) / len(tr):5.1%} {sum(x >= 25 for x in peaks) / len(tr):5.1%} | "
                  f"{held:+14.0%} {res[5]:+8.0%} {res[10]:+9.0%} {res[25]:+9.0%} | "
                  f"{a1['annual']:+6.0%}/yr {a1['maxDD']:4.0%} {a2['annual']:+5.0%}/yr {a2['maxDD']:4.0%}", flush=True)
        print()
    print("Where the money came from (sell at 25x, else hold):")
    for tenor, frac in ((180, 0.01), (90, 0.01), (60, 0.01)):
        for bump, tag in ((0.10, ''), (0.20, ' pricier')):
            tr = paths(tenor, frac, bump)
            rs = sorted(((exit_ret(c, p, 25)[0], t, d0) for d0, c, p, _, t in tr), reverse=True)
            tot = sum(x[0] for x in rs)
            print(f"  {tenor}d 1%{tag}: per $1 {tot / len(rs):+.0%}; top 3 tickets " + ', '.join(f"{t} {d0[:7]} {x + 1:.0f}x" for x, t, d0 in rs[:3]) +
                  f"; without those 3: per $1 {(tot - sum(x[0] for x in rs[:3])) / (len(rs) - 3):+.0%}; "
                  f"winners {sum(1 for x in rs if x[0] > 0)}/{len(rs)}")
    print("\naccount columns use whichever exit (hold, or the best sell@ target) did better per $1; "
          "'OTM by' = median strike vs price at entry")


if __name__ == '__main__':
    main()

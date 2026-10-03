#!/usr/bin/env python3
"""Breadth exit with a "thrust" re-entry for the top-5 rule, since 2020.

Exit: 90% of S&P 500 + Nasdaq-100 stocks are below their close of 2 weeks
earlier. Then wait for a thrust day - a session where at least 80% (or 75%,
70%) of the stocks close up on the day - and buy the top 5 at that close.

Two ways to step aside:
  sell all  - go to cash at the exit's close
  freeze    - keep what you hold (the normal weekly rule may still sell a
              holding), but buy nothing new until the thrust day

Compared with the current rule and the earlier 90/85 breadth exit, on S&P
500 + Nasdaq-100 and the fair S&P-only universe.

Usage:
    python scripts/backtest_thrust.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_breadth import breadth_series, episodes, risk_states  # noqa: E402
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import SPLIT, START, WINDOWS, window_return  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402


def up_share(prices, calendar, member):
    """{date: share of member stocks closing above the previous session's close}."""
    out = {}
    for k in range(1, len(calendar)):
        d, d0 = calendar[k], calendar[k - 1]
        up = total = 0
        for t, px in prices.items():
            a, b = px.get(d0), px.get(d)
            if a and b and member(t, d):
                total += 1
                up += b > a
        if total:
            out[d] = up / total
    return out


def thrust_states(calendar, breadth, ups, exit_at=0.90, thrust=0.80):
    """{date: invested?} - out when breadth >= exit_at; back in at the close of
    the first later session where at least `thrust` of stocks closed up."""
    state, out = True, {}
    for d in calendar:
        if state and breadth.get(d, 0) >= exit_at:
            state = False
        elif not state and ups.get(d, 0) >= thrust:
            state = True
        out[d] = state
    return out


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    print("computing breadth...", file=sys.stderr)
    breadth = breadth_series(comb, calendar, member)
    ups = up_share(comb, calendar, member)
    old = risk_states(calendar, breadth, 0.90, 0.85, wait=5)
    states = {th: thrust_states(calendar, breadth, ups, 0.90, th) for th in (0.80, 0.75, 0.70)}
    base['SPY'] = dict(bench['SPY'])
    comb['SPY'] = dict(bench['SPY'])

    print("\nStep-aside episodes since 2020 (exit at 90% down over 2 weeks -> first 80% up day):")
    days = {d: i for i, d in enumerate(calendar)}
    for a, b in episodes(calendar, states[0.80], START):
        n = days[b] - days[a] if b else len(calendar) - 1 - days[a]
        spy = bench['SPY']
        s0, s1 = dict(spy)[a], dict(spy)[b or calendar[-1]]
        print(f"  out {a}  back {b or 'still out'}  ({n:3} sessions, SPY {s1 / s0 - 1:+6.1%} meanwhile)")
    print(f"  80% up days since 2020: {sum(1 for d, v in ups.items() if d >= START and v >= 0.80)}")

    def sell(st):
        return dict(risk_on=lambda d: st.get(d, True), risk_daily=True)

    def freeze(st):
        return dict(buy_ok=lambda d: st.get(d, True))

    variants = {
        'current (no protection)': {},
        'old: 90% exit, back <85% after 1wk': sell(old),
        'sell all, back on 80% up day': sell(states[0.80]),
        'sell all, back on 75% up day': sell(states[0.75]),
        'sell all, back on 70% up day': sell(states[0.70]),
        'freeze buys until 80% up day': freeze(states[0.80]),
        'freeze buys until 75% up day': freeze(states[0.75]),
    }
    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, since 2020 ==")
        print(f"{'rule':36} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} {'2025-26':>8} | "
              + ' | '.join(f"{w:>15}" for w in WINDOWS))
        for label, kw in variants.items():
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=member, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            curves[(uni, label)] = [p[:2] for p in c]
            ws = ' | '.join(f"{window_return(c, a, b):+15.1%}" for a, b in WINDOWS.values())
            print(f"{label:36} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} "
                  f"{o['total']:+8.0%} | {ws}", flush=True)
    for b in ('SPY', 'QQQ'):
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
        f = curve_stats([c for d, c in bench[b] if d >= START])
        ws = ' | '.join(f"{window_return(curves[b], a, bb):+15.1%}" for a, bb in WINDOWS.values())
        print(f"{'buy & hold ' + b:36} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {'':>17} | {ws}")
    keys = [('S&P 500 + Nasdaq-100', k) for k in variants] + ['SPY', 'QQQ']
    heads = ['current', 'old 90/85', 'sell/80', 'sell/75', 'sell/70', 'frz/80', 'frz/75', 'SPY', 'QQQ']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>10}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+10.0%}" for k in keys))


if __name__ == '__main__':
    main()

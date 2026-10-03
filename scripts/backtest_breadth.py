#!/usr/bin/env python3
"""Market-breadth exit for the top-5 rule, since 2020.

Breadth = share of S&P 500 + Nasdaq-100 stocks (members on that date) whose
close is below their close 10 sessions (2 weeks) earlier. When it reaches
`exit_at` (e.g. 90%), sell everything at that day's close; buy the current
top 5 back once at least `wait` sessions (a week) have passed AND breadth has
fallen below `reenter_below` (e.g. 85%). Compared with no exit, on the
dashboard universe and the fair S&P 500-only one, plus the Feb-Apr 2025 window.

Usage:
    python scripts/backtest_breadth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

START, SPLIT = '2020-01-02', '2025-01-01'
RULES = [(0.90, 0.85), (0.80, 0.75), (0.70, 0.65)]


def breadth_series(prices, calendar, member, days=10):
    """{date: share of member stocks below their close `days` sessions earlier}."""
    out = {}
    for k in range(days, len(calendar)):
        d, d0 = calendar[k], calendar[k - days]
        down = total = 0
        for t, px in prices.items():
            a, b = px.get(d0), px.get(d)
            if a and b and member(t, d):
                total += 1
                down += b < a
        if total:
            out[d] = down / total
    return out


def risk_states(calendar, breadth, exit_at, reenter_below, wait=5):
    """{date: invested?} - out when breadth >= exit_at; back in once `wait`
    sessions have passed since the exit and breadth < reenter_below."""
    state, out, since = True, {}, None
    for k, d in enumerate(calendar):
        b = breadth.get(d)
        if state and b is not None and b >= exit_at:
            state, since = False, k
        elif not state and k - since >= wait and b is not None and b < reenter_below:
            state = True
        out[d] = state
    return out


def episodes(calendar, states, start):
    """[(exit_date, back_in_date or None)] from START on."""
    out, prev = [], True
    for d in calendar:
        if d < start:
            prev = states[d]
            continue
        if prev and not states[d]:
            out.append([d, None])
        elif not prev and states[d] and out:
            out[-1][1] = d
        prev = states[d]
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
    since = [v for d, v in breadth.items() if d >= START]
    for lvl in (0.9, 0.8, 0.7):
        print(f"days since 2020 with >= {lvl:.0%} of stocks down over 2 weeks: {sum(v >= lvl for v in since)} of {len(since)}")
    base['SPY'] = dict(bench['SPY'])
    comb['SPY'] = dict(bench['SPY'])
    states = {r: risk_states(calendar, breadth, *r) for r in RULES}
    for r in RULES:
        eps = episodes(calendar, states[r], START)
        print(f"\nexit at {r[0]:.0%} / back below {r[1]:.0%}: {len(eps)} exits -> " +
              '; '.join(f"{a} to {b or 'still out'}" for a, b in eps[:12]) + (' ...' if len(eps) > 12 else ''))

    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, 6 months skip latest, since 2020 ==")
        print(f"{'exit rule':34} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} | {'2025-26':>8} | {'in cash':>7} | Feb19-Apr9 '25")
        for label, kw in [('no exit (current)', {})] + [
                (f"exit {a:.0%} / back below {b:.0%}", dict(risk_on=(lambda st: lambda d: st.get(d, True))(states[(a, b)]),
                                                            risk_daily=True)) for a, b in RULES]:
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=member, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            cash = sum(1 for p in c if p[2] == 0) / len(c)
            w = run_momentum(prices, calendar, '2025-02-19', look=126, skip=21, top_n=5, eligible=member,
                             rebalance_on_start=True, cost=0.0, **kw)['curve']
            w = [p for p in w if p[0] <= '2025-04-09']
            curves[(uni, label)] = [p[:2] for p in c]
            print(f"{label:34} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} | "
                  f"{o['total']:+8.0%} | {cash:7.0%} | {w[-1][1] / w[0][1] - 1:+.1%}", flush=True)
    for b in ('SPY', 'QQQ'):
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
    keys = [('S&P 500 + Nasdaq-100', 'no exit (current)'), ('S&P 500 + Nasdaq-100', 'exit 90% / back below 85%'),
            ('S&P 500 + Nasdaq-100', 'exit 80% / back below 75%'), ('S&P 500 + Nasdaq-100', 'exit 70% / back below 65%'),
            'SPY', 'QQQ']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>12}" for h in
                                                                        ['no exit', '90/85', '80/75', '70/65', 'SPY', 'QQQ']))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+12.0%}" for k in keys))


if __name__ == '__main__':
    main()

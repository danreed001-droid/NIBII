#!/usr/bin/env python3
"""Backtests "buy the strongest stocks" (mtl/momentum.py) on the S&P 500
from 2020: every weekly variant of score window x portfolio size x trend
check x SPY 200-day filter, vs buying and holding SPY/QQQ/NVDA/ARKK/BTC,
with 2020-2024 in-sample and 2025 on as the out-of-sample check. Prints
what the strongest variant holds as of the latest rebalance.

Reuses the price cache from scripts/backtest_variants.py. Stock prices are
split-adjusted closes without dividends (benchmarks include dividends), so
the stock side is slightly understated.

Membership: a stock can only be bought from the date it joined the S&P 500
(data/sp500.csv 'added'). Using today's list without that lets the test
buy companies years before the index added them - usually right after a
huge run - which is hindsight. Both versions are printed; only the
point-in-time one is a fair test. (Stocks that LEFT the index since 2020
are still missing, so even that is somewhat optimistic.)

Usage:
    python scripts/backtest_momentum.py
    python scripts/backtest_momentum.py --sizes 5,10,20 --plain   # portfolio sizes, no trend/SPY variants
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import Context, SWING_N, curve_stats, resample, state_series, with_ends  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START, SPLIT = '2020-01-02', '2025-01-01'
SCORES = {'6-1m': (126, 21), '3m': (63, 0), '12-1m': (252, 21)}
# Price histories the provider left unadjusted for a corporate action: a
# spin-off reads as a crash. Excluded rather than guessed at.
BROKEN = {'CTVA': 'Oct 2026 separation not adjusted in Yahoo history (-84% overnight)'}


def trend_map(daily, lookback=2):
    """{date: True} where the weekly and daily charts are both in an uptrend
    at that day's close."""
    ends = with_ends(daily)
    states = state_series(daily, SWING_N['daily'], lookback)
    wk = Context(*resample(daily, 'W'), SWING_N['weekly'], lookback)
    return {b[0][:10]: states[k] == 'uptrend' and wk.at(ends[k]) == 'uptrend' for k, b in enumerate(daily)}


def stats(curve):
    full = curve_stats([p[1] for p in curve])
    ins = curve_stats([p[1] for p in curve if p[0] < SPLIT])
    out = curve_stats([p[1] for p in curve if p[0] >= SPLIT])
    return full, ins, out


def main():
    names = default_universe()
    tickers = [t for t in names if t not in ETFS and t not in BROKEN]
    raw, bench = load_data(list(names))
    prices = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in tickers if raw[t].get('daily')}
    prices['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    print("computing trend states...", file=sys.stderr)
    trend = {t: trend_map(raw[t]['daily']) for t in prices if t != 'SPY'}
    spy = bench['SPY']
    above200 = {}
    for k in range(199, len(spy)):
        above200[spy[k][0]] = spy[k][1] > sum(c for _, c in spy[k - 199:k + 1]) / 200

    added = load_added()

    def member(t, d):
        return added.get(t, '0000') <= d

    def trend_ok(t, d):
        return trend[t].get(d, False)

    def combine(*fs):
        fs = [f for f in fs if f]
        return (lambda t, d: all(f(t, d) for f in fs)) if fs else None

    def risk_on(d):
        return above200.get(d, False)

    results = {}
    print(f"{'variant':38} {'hindsight':>9} | {'total':>7} {'CAGR':>6} {'maxDD':>6} | {'2020-24':>7} {'DD':>5} | {'2025-26':>7} {'DD':>5} | turn/yr")
    sizes = (10, 20)
    if '--sizes' in sys.argv:
        sizes = tuple(int(x) for x in sys.argv[sys.argv.index('--sizes') + 1].split(','))
    combos = ((False, False),) if '--plain' in sys.argv else ((False, False), (True, False), (True, True))
    for sname, (look, skip) in SCORES.items():
        for n in sizes:
            for tr, rk in combos:
                key = f"top {n}, {sname}" + (", trend check" if tr else "") + (", SPY>200d" if rk else "")
                common = dict(look=look, skip=skip, top_n=n, risk_on=risk_on if rk else None)
                hind = run_momentum(prices, calendar, START, eligible=combine(trend_ok if tr else None), **common)
                r = run_momentum(prices, calendar, START, eligible=combine(member, trend_ok if tr else None), **common)
                full, ins, out = stats(r['curve'])
                hfull = stats(hind['curve'])[0]
                results[key] = dict(full=full, inS=ins, out=out, turnover=r['turnover'], hindsight=hfull,
                                    curve=[[d, round(v, 3), h] for d, v, h in r['curve']][::5] + [r['curve'][-1]],
                                    lastPicks=r['picks'][-1] if r['picks'] else None)
                print(f"{key:38} {hfull['total']:+9.0%} | {full['total']:+7.0%} {full['annual'] or 0:+6.0%} {full['maxDD']:6.0%} | "
                      f"{ins['total']:+7.0%} {ins['maxDD']:5.0%} | {out['total']:+7.0%} {out['maxDD']:5.0%} | {r['turnover']:.1f}x",
                      flush=True)
    print()
    bres = {}
    for b in ('SPY', 'QQQ', 'NVDA', 'ARKK', 'BTC-USD'):
        pts = [p for p in bench[b] if p[0] >= START]
        full = curve_stats([c for _, c in pts], 365 if b == 'BTC-USD' else 252)
        ins = curve_stats([c for d, c in pts if d < SPLIT])
        out = curve_stats([c for d, c in pts if d >= SPLIT])
        bres[b] = dict(full=full, inS=ins, out=out)
        print(f"{'buy & hold ' + b:38} {'':9} | {full['total']:+7.0%} {full['annual'] or 0:+6.0%} {full['maxDD']:6.0%} | "
              f"{ins['total']:+7.0%} {ins['maxDD']:5.0%} | {out['total']:+7.0%} {out['maxDD']:5.0%}")

    best = max(results, key=lambda k: results[k]['inS']['total'])
    print(f"\nbest on 2020-24 alone: {best} -> 2025-26 check {results[best]['out']['total']:+.0%}")
    for key in list(dict.fromkeys([best] + [k for k in results if k.startswith('top 5,')]))[:4]:
        d, picks = results[key]['lastPicks']
        print(f"{key} holds as of {d}: " + ', '.join(f"{t} ({names[t][0]})" for t in picks))
    with open(os.path.join(ROOT, 'data', 'momentum.json'), 'w') as f:
        json.dump(dict(start=START, split=SPLIT, results=results, bench=bres, best=best), f)


if __name__ == '__main__':
    main()

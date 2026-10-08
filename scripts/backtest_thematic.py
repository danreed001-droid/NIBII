#!/usr/bin/env python3
"""The dashboard's current rule restricted to five thematic baskets (AI chips, AI platforms,
power, exchanges/financials, index funds) - 54 tickers.

Test 1 - only these can be picked: Boost 100% (6-month return skipping the last month,
must beat SPY, top 5 equal weight, kept while top 10, news-gap boost, blow-off exit
while SPY is below its 150-day average), run on the 54 alone. A ticker is eligible
from its first trading day. Dividend-adjusted prices, 0.05% cost per trade, no tax.

Test 2 - the full strategy, only list stocks bought: the point-in-time audit's
Boost 100% picks (S&P 500 members as of each date); each list stock in the holdings
is held at 1/5, a slot taken by any other stock sits in cash.

Compared with the full strategy, SPY, QQQ and the 54 in equal weight (rebalanced
monthly). Windows from 2015, 2017, 2020, 2023 and this year to date.

Usage:
    python scripts/backtest_thematic.py PICKS_JSON CURVE_JSON
      PICKS_JSON  audit picks dump (key, calendar, picks, prices) of the Boost 100% rule
      CURVE_JSON  audit daily curve dump with series XM150w0_boost
"""
import json
import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_scan import BLOWOFF, BLOWOFF_MA, LOOK, SKIP, fetch  # noqa: E402
from mtl.momentum import blowoff_exit, run_momentum  # noqa: E402
from mtl.news import booster, news_gap_days  # noqa: E402

BASKETS = {
    'Silicon_Infrastructure': ['NVDA', 'AMD', 'AVGO', 'ANET', 'ALAB', 'ARM', 'TSM', 'MRVL', 'MU', 'INTC', 'ASML', 'QCOM'],
    'Hyperscalers_Core_AI': ['MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL', 'CRM', 'PLTR', 'CRWD', 'SNOW', 'ADBE', 'TSLA'],
    'Energy_Monopolies': ['CEG', 'VST', 'NEE', 'DUK', 'SO', 'TLN', 'GEV', 'EXC', 'SRE', 'PEG', 'ETN', 'VRT'],
    'Prediction_Markets_Financials': ['CME', 'ICE', 'CBOE', 'IBKR', 'GS', 'JPM', 'MS', 'BLK', 'V', 'MA'],
    'Market_Indices': ['SPY', 'QQQ', 'TQQQ', 'SPXL', 'DIA', 'IWM', 'XLU', 'XLK', 'XLF'],
}
LIST = [t for ts in BASKETS.values() for t in ts]
START = '2015-01-02'


def stats(curve, lo, hi=None):
    c = [(d, v) for d, v in curve if d >= lo and (hi is None or d <= hi)]
    if len(c) < 10:
        return None
    v = [x[1] for x in c]
    yrs = (date.fromisoformat(c[-1][0]) - date.fromisoformat(c[0][0])).days / 365.25
    r = [v[i] / v[i - 1] - 1 for i in range(1, len(v))]
    m = sum(r) / len(r)
    sd = (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5
    dn = (sum(min(0.0, x) ** 2 for x in r) / len(r)) ** 0.5
    peak, dd = v[0], 0.0
    for x in v:
        peak = max(peak, x)
        dd = min(dd, x / peak - 1)
    ex = m * 252 - 0.015
    return dict(total=v[-1] / v[0] - 1, cagr=(v[-1] / v[0]) ** (1 / yrs) - 1 if yrs >= 0.95 else None, dd=dd,
                sharpe=ex / (sd * math.sqrt(252)) if sd else 0, sortino=ex / (dn * math.sqrt(252)) if dn else 0)


def main():
    picks_file, curve_file = sys.argv[1], sys.argv[2]
    bars = fetch(LIST, start='2013-06-01', adjusted=True)
    cal = [b[0] for b in bars['SPY']]
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    first = {t: bs[0][0] for t, bs in bars.items() if bs}
    missing = [t for t in LIST if t not in first]

    def eligible(t, d):
        # ~6 months of prices before a new listing can rank
        return t in first and first[t] <= d and t != 'SPY'
    gaps = {t: news_gap_days(bars[t]) for t in LIST if bars.get(t)}
    r1 = run_momentum(prices, cal, START, look=LOOK, skip=SKIP, top_n=5, eligible=eligible, exec_next='close',
                      prefer=booster(gaps, cal), prefer_mode='force', prefer_rank=None, prefer_pool='all',
                      hold_exit=blowoff_exit(prices, cal, BLOWOFF, market='SPY', ma=BLOWOFF_MA))
    curves = {'Test 1: top 5 of the 54 only': [(p[0], p[1]) for p in r1['curve']]}

    # Test 2: the audit's Boost 100% holdings, list stocks only, others in cash
    D = json.load(open(picks_file))
    full = json.load(open(curve_file))['series']['XM150w0_boost']['pre']
    acal = [d for d, _ in full]
    apx = D['prices']
    pk = [p for p in D['picks']]
    v, cur, out, j, prev, slots = 1.0, [], [], 0, None, []
    for d in acal:
        if prev is not None and cur:
            v *= 1 + sum(0.2 * (apx[t].get(d, apx[t].get(prev)) / apx[t][prev] - 1) for t in cur if apx[t].get(prev))
        while j < len(pk) and pk[j][0] <= d:
            cur = [t for t in pk[j][1] if t in LIST]
            j += 1
        out.append((d, v))
        slots.append(len(cur))
        prev = d
    curves['Test 2: full strategy, list stocks only'] = out
    curves['Full strategy (Boost 100%, all S&P 500)'] = [(d, x) for d, x in full]

    # the 54 in equal weight, rebalanced each month among those trading
    v, held, ew, last = 1.0, {}, [], {}
    for i, d in enumerate(cal):
        if d < START:
            continue
        if held:
            v = sum(n * (prices[t].get(d) or last[t]) for t, n in held.items())
        ew.append((d, v))
        last.update({t: prices[t][d] for t in LIST if prices.get(t, {}).get(d)})
        if i + 1 == len(cal) or cal[i + 1][:7] != d[:7] or not held:
            live = [t for t in LIST if prices.get(t, {}).get(d)]
            held = {t: v / len(live) / last[t] for t in live}
    curves['The 54 in equal weight'] = ew
    for b in ('SPY', 'QQQ'):
        curves[b] = [(d, prices[b][d]) for d in cal if d >= START and d in prices[b]]

    windows = [('2015-01-02', 'Since 2015'), ('2017-01-03', 'Since 2017'), ('2020-01-02', 'Since 2020'),
               ('2023-01-03', 'Since 2023'), (f"{cal[-1][:4]}-01-01", f"{cal[-1][:4]} to date")]
    res = {'asOf': cal[-1], 'missing': missing, 'windows': {}}
    for lo, lab in windows:
        res['windows'][lab] = {k: stats(c, lo) for k, c in curves.items()}
        print(f"\n=== {lab} (from {lo}) ===")
        for k, s_ in res['windows'][lab].items():
            if s_:
                cg = f"{s_['cagr']:7.1%}" if s_['cagr'] is not None else '      -'
                print(f"{k:42} total {s_['total']:9.1%}  per year {cg}  worst {s_['dd']:6.1%}  Sharpe {s_['sharpe']:5.2f}  Sortino {s_['sortino']:5.2f}")
    held_n = [len(p[1]) for p in r1['picks']]
    res['test1Avg'] = sum(held_n) / len(held_n)
    res['test1Now'] = r1['picks'][-1][1]
    days = {}
    for (d0, h), (d1, _) in zip(r1['picks'], r1['picks'][1:] + [[cal[-1], []]]):
        n = sum(1 for d in cal if d0 <= d < d1)
        for t in h:
            days[t] = days.get(t, 0) + n
    tot = sum(1 for d in cal if d >= r1['picks'][0][0])
    res['test1Share'] = {t: days[t] / tot for t in sorted(days, key=lambda t: -days[t])}
    res['test2Slots'] = sum(slots) / len(slots)
    res['test2Cash'] = sum(1 for x in slots if x == 0) / len(slots)
    tally = {}
    for p in pk:
        for t in p[1]:
            if t in LIST:
                tally[t] = tally.get(t, 0) + 1
    res['test2Tally'] = dict(sorted(tally.items(), key=lambda x: -x[1]))
    print(f"\nTest 1: average {res['test1Avg']:.1f} of 5 held; now {', '.join(res['test1Now'])}")
    print('Test 1 share of time held: ' + ', '.join(f"{t} {x:.0%}" for t, x in list(res['test1Share'].items())[:15]))
    print(f"Test 2: on average {res['test2Slots']:.1f} of 5 slots held a list stock; fully in cash {res['test2Cash']:.0%} of days")
    print('Test 2 list stocks in the holdings (weeks): ' + ', '.join(f"{t} {n}" for t, n in list(res['test2Tally'].items())[:20]))
    if missing:
        print('no data: ' + ', '.join(missing))
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'thematic_backtest.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()

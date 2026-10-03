#!/usr/bin/env python3
"""The top-5 rule and the current setup (auto mix) since 2000 - through the
dot-com crash, 2008, the 2009 momentum crash, 2018, COVID and 2022 - vs SPY
and QQQ (Nasdaq-100).

Same rule as the dashboard: S&P 500 + Nasdaq-100 ranked by 6-1 month strength,
must beat SPY, top 5, keep while top 10, signal Friday, trade Monday's close,
0.05% cost; auto mix = 60/40 with the best-of sleeve while 2+ holdings are in
a daily lower-low downtrend. Sleeve ETFs only exist from 2002-2007; before an
asset exists it can't be picked, and cash earns 0% before BIL (2007).

BIG CAVEAT: the stock list is today's S&P 500 (with join dates) + Nasdaq-100.
Companies that left the indexes or went bust (Lehman, Enron, WorldCom, Bear
Stearns, ...) are missing, and the further back the test goes the more that
flatters it.

Usage:
    python scripts/backtest_long_history.py
"""
import os
import pickle
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_scan import blocked_dates, fetch  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.sleeve import ASSETS, plan_curve_dynamic, sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500, momentum_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.long_hist.pkl')
FROM, START = '1998-06-01', '2000-01-03'
WINDOWS = [("Dot-com crash  Mar 2000-Oct 2002", '2000-03-24', '2002-10-09'),
           ("Financial crisis Oct 2007-Mar 2009", '2007-10-09', '2009-03-09'),
           ("Momentum crash Mar-May 2009", '2009-03-09', '2009-05-29'),
           ("Euro / downgrade Apr-Oct 2011", '2011-04-29', '2011-10-03'),
           ("Q4 2018 selloff", '2018-09-20', '2018-12-24'),
           ("COVID crash Feb-Mar 2020", '2020-02-19', '2020-03-23'),
           ("2022 bear market", '2022-01-03', '2022-10-12'),
           ("Feb-Apr 2025", '2025-02-19', '2025-04-08')]


def load():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    names = momentum_universe(refresh=False)
    bars = fetch(sorted(names), start=FROM)
    bench = fetch(['SPY', 'QQQ'], start=FROM, adjusted=True)
    assets = fetch(ASSETS, start=FROM, adjusted=True)
    data = dict(names=names, bars=bars, bench=bench, assets=assets)
    with open(CACHE, 'wb') as f:
        pickle.dump(data, f)
    return data


def main():
    D = load()
    names, bars, bench = D['names'], D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    cal = [b[0] for b in bench['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}
    have = sum(1 for t, bs in bars.items() if bs and bs[0][0] <= '2000-01-31')
    print(f"{len(bars)} stocks in today's lists; {have} have prices back to Jan 2000", file=sys.stderr)

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t not in sp or added.get(t, '0000') <= d)

    r = run_momentum(prices, cal, START, look=126, skip=21, top_n=5, eligible=eligible, exec_next='close')
    top5 = [p[:2] for p in r['curve']]
    # sleeve: an asset is pickable once it has 6 months of prices; cash = BIL, flat 0% before BIL exists
    apx = {t: {b[0]: b[4] for b in bs} for t, bs in D['assets'].items() if bs}
    bil0 = min(apx['BIL'])
    first_bil = apx['BIL'][bil0]
    for d in cal:
        if d < bil0:
            apx['BIL'][d] = first_bil
    sl, _ = sleeve_curve(apx, cal, START)
    # auto mix: 2+ holdings in a daily lower-low downtrend at the Friday close -> 60/40 next session
    pdays = [p[0] for p in r['picks']]
    dates = {t: [b[0] for b in bs] for t, bs in bars.items()}
    cache = {}

    def downs(f):
        i = bisect_right(pdays, f)
        held = r['picks'][i - 1][1] if i else []
        n = 0
        for t in held:
            if (t, f) not in cache:
                j = bisect_right(dates[t], f)
                cache[(t, f)] = structure_signal([tuple(b) for b in bars[t][max(0, j - 320):j]], n=3, lookback=2)['state'] == 'downtrend'
            n += cache[(t, f)]
        return n
    auto = plan_curve_dynamic(top5, sl, cal, lambda f: 0.6 if downs(f) >= 2 else 1.0)
    curves = {'Current setup (auto mix)': auto, 'Top 5 in stock': top5,
              'SPY': [[d, v] for d, v in ((b[0], b[4]) for b in bench['SPY']) if d >= START],
              'QQQ (Nasdaq-100)': [[d, v] for d, v in ((b[0], b[4]) for b in bench['QQQ']) if d >= START]}

    print(f"\n{'since ' + START:30} {'total':>10} {'per yr':>7} {'worst drop':>11}   $10k became")
    for k, c in curves.items():
        st = curve_stats([v for _, v in c])
        print(f"{k:30} {st['total']:+10,.0%} {st['annual']:+7.0%} {st['maxDD']:11.0%}   ${10000 * (1 + st['total']):,.0f}")

    print(f"\n{'crash windows':36}" + ''.join(f"{k[:14]:>15}" for k in curves))
    for label, a, b in WINDOWS:
        row = ''
        for k, c in curves.items():
            v = [x for d, x in c if a <= d <= b]
            row += f"{v[-1] / v[0] - 1:+15.0%}" if len(v) > 1 else f"{'':>15}"
        print(f"{label:36}{row}")

    print(f"\n{'year':6}" + ''.join(f"{k[:14]:>15}" for k in curves))
    ye = {k: {} for k in curves}
    for k, c in curves.items():
        for d, v in c:
            ye[k][d[:4]] = v
    prev = {k: c[0][1] for k, c in curves.items()}
    for y in sorted(ye['SPY']):
        row = ''
        for k in curves:
            row += f"{ye[k][y] / prev[k] - 1:+15.0%}"
            prev[k] = ye[k][y]
        print(f"{y:6}{row}")
    weeks = [f for f in last_sessions_of_weeks(cal) if f >= START]
    print(f"\nauto mix was at 60/40 in {sum(1 for f in weeks if downs(f) >= 2)} of {len(weeks)} weeks")


if __name__ == '__main__':
    main()

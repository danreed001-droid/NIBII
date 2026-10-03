#!/usr/bin/env python3
"""Fixing the 2009 rebound miss ("momentum crash"), tested 2000-2026.

After a bear market the 6-1 month leaders are the stocks that fell least, while
the rebound is led by the most beaten-down ones - the model missed 2009
(-14% / -27% vs SPY +26%). Fixes, all switched on only while SPY's own 12-month
return is negative ("bear regime"):
  3m in bear        rank by 3-month return (no skip) instead of 6-1
  1m in bear        rank by 1-month return
  3m in rebound     3-month ranking only once SPY is back above its 50-day average
  SPY / QQQ in bear hold the index instead of the top 5 (switch at Monday's close)
  50% SPY in bear   half top 5 (or auto mix), half SPY while in the bear regime
Each on the plain top 5 and with the auto mix; same caveats as
scripts/backtest_long_history.py (today's index lists flatter old years).

Usage:
    python scripts/backtest_rebound.py
"""
import os
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import START, load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.sleeve import plan_curve_dynamic, sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402

WINDOWS = [('2001-02', '2001-01-01', '2002-12-31'), ('2008', '2008-01-01', '2008-12-31'),
           ('2009', '2009-01-01', '2009-12-31'), ('2010', '2010-01-01', '2010-12-31'),
           ('2011', '2011-01-01', '2011-12-31'), ('2020', '2020-01-01', '2020-12-31'),
           ('2022', '2022-01-01', '2022-12-31'), ('2023', '2023-01-01', '2023-12-31')]


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    cal = [b[0] for b in bench['SPY']]
    spy = [prices['SPY'][d] for d in cal]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t not in sp or added.get(t, '0000') <= d)

    def bear(k):
        return k >= 252 and spy[k] < spy[k - 252]

    def rebound(k):
        return bear(k) and spy[k] > sum(spy[k - 49:k + 1]) / 50

    kidx = {d: i for i, d in enumerate(cal)}
    apx = {t: {b[0]: b[4] for b in bs} for t, bs in D['assets'].items() if bs}
    bil0 = min(apx['BIL'])
    for d in cal:
        if d < bil0:
            apx['BIL'][d] = apx['BIL'][bil0]
    sl, _ = sleeve_curve(apx, cal, START)
    dates = {t: [b[0] for b in bs] for t, bs in bars.items()}
    cache = {}

    def auto_of(r):
        pdays = [p[0] for p in r['picks']]

        def share(f):
            i = bisect_right(pdays, f)
            held = r['picks'][i - 1][1] if i else []
            n = 0
            for t in held:
                if (t, f) not in cache:
                    j = bisect_right(dates[t], f)
                    cache[(t, f)] = structure_signal([tuple(b) for b in bars[t][max(0, j - 320):j]], n=3, lookback=2)['state'] == 'downtrend'
                n += cache[(t, f)]
            return 0.6 if n >= 2 else 1.0
        return plan_curve_dynamic([p[:2] for p in r['curve']], sl, cal, share)

    def run(lookback_at=None):
        return run_momentum(prices, cal, START, look=126, skip=21, top_n=5, eligible=eligible, exec_next='close',
                            lookback_at=lookback_at)

    base = run()
    variants = {
        'current 6-1m': base,
        '3m ranking in bear': run(lambda k: (63, 0) if bear(k) else (126, 21)),
        '1m ranking in bear': run(lambda k: (21, 0) if bear(k) else (126, 21)),
        '3m ranking in rebound': run(lambda k: (63, 0) if rebound(k) else (126, 21)),
    }
    curves = {}
    for name, r in variants.items():
        curves['top 5, ' + name] = [p[:2] for p in r['curve']]
        curves['auto mix, ' + name] = auto_of(r)
    top5 = curves['top 5, current 6-1m']
    for idx_name in ('SPY', 'QQQ'):
        ic = [[b[0], b[4]] for b in bench[idx_name] if b[0] >= START]
        curves[f'top 5, hold {idx_name} in bear'] = plan_curve_dynamic(top5, ic, cal, lambda f: 0.0 if bear(kidx[f]) else 1.0)
        curves[f'top 5, hold {idx_name} in rebound'] = plan_curve_dynamic(top5, ic, cal, lambda f: 0.0 if rebound(kidx[f]) else 1.0)
    spy_c = [[b[0], b[4]] for b in bench['SPY'] if b[0] >= START]
    curves['top 5, 50% SPY in bear'] = plan_curve_dynamic(top5, spy_c, cal, lambda f: 0.5 if bear(kidx[f]) else 1.0)
    curves['auto mix, 50% SPY in bear'] = plan_curve_dynamic(curves['auto mix, current 6-1m'], spy_c, cal,
                                                              lambda f: 0.5 if bear(kidx[f]) else 1.0)
    curves['SPY'] = [[b[0], b[4]] for b in bench['SPY'] if b[0] >= START]
    curves['QQQ'] = [[b[0], b[4]] for b in bench['QQQ'] if b[0] >= START]

    print(f"{'2000-2026':34} {'per yr':>7} {'worst':>6} {'2020+/yr':>9} | " + ' '.join(f"{w[0]:>7}" for w in WINDOWS))
    for k, c in curves.items():
        st = curve_stats([v for _, v in c])
        rec = curve_stats([v for d, v in c if d >= '2020-01-01'])
        ws = []
        for _, a, b in WINDOWS:
            v = [x for d, x in c if a <= d <= b]
            ws.append(f"{v[-1] / v[0] - 1:+7.0%}")
        print(f"{k:34} {st['annual']:+7.0%} {st['maxDD']:6.0%} {rec['annual']:+9.0%} | " + ' '.join(ws), flush=True)
    print(f"\nbear regime (SPY below its level a year earlier) in {sum(1 for k in range(len(cal)) if cal[k] >= START and bear(k)) / sum(1 for d in cal if d >= START):.0%} of sessions")


if __name__ == '__main__':
    main()

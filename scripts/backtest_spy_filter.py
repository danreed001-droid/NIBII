#!/usr/bin/env python3
"""Top-5 strongest with and without the SPY 200-day filter, from 2020.

Filter: when SPY closes below its 200-day average, sell everything and hold
cash; when it closes back above, buy the current top 5. Checked either at
every close ('daily') or only at the Friday rebalance ('Friday'). Run on
the fair S&P 500-only universe (join dates) and on S&P 500 + Nasdaq-100 -
the dashboard's universe - with year-by-year returns vs SPY and QQQ.

Reuses the price caches from backtest_variants.py / backtest_combined.py.

Usage:
    python scripts/backtest_spy_filter.py
    python scripts/backtest_spy_filter.py --windows   # 3 / 6 / 12-month strength side by side
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
WINDOWS = {'3m': (63, 0), '6-1m': (126, 21), '12-1m': (252, 21)}


def above_200(spy):
    """{date: SPY close > its 200-day simple average} from [[date, close], ...]."""
    out, closes = {}, [c for _, c in spy]
    for k in range(199, len(spy)):
        out[spy[k][0]] = closes[k] > sum(closes[k - 199:k + 1]) / 200
    return out


def windows_table(base, comb, calendar, eligible, risk_on, bench):
    """3m vs 6-1m vs 12-1m, with and without the daily SPY filter, plus years."""
    print(f"{'top 5':46} {'total':>7} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>7} | {'2025-26':>7}")
    curves = {}
    for uni, prices in (('S&P 500 only', base), ('S&P 500 + Nasdaq-100', comb)):
        for wname, (look, skip) in WINDOWS.items():
            for flt, kw in (('', {}), (', SPY filter', dict(risk_on=risk_on, risk_daily=True))):
                r = run_momentum(prices, calendar, START, look=look, skip=skip, top_n=5, eligible=eligible, **kw)
                c = r['curve']
                f = curve_stats([p[1] for p in c])
                i = curve_stats([p[1] for p in c if p[0] < SPLIT])
                o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
                label = f"{uni}, {wname}{flt}"
                curves[label] = [p[:2] for p in c]
                print(f"{label:46} {f['total']:+7.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+7.0%} | {o['total']:+7.0%}",
                      flush=True)
    for b in ('SPY', 'QQQ'):
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
    show = [f"S&P 500 + Nasdaq-100, {w}" for w in WINDOWS] + ['SPY', 'QQQ']
    years = {k: yearly(curves[k]) for k in show}
    print(f"\nS&P 500 + Nasdaq-100, no filter, year by year\n{'year':6}" +
          ''.join(f"{s:>10}" for s in list(WINDOWS) + ['SPY', 'QQQ']))
    for y in sorted(years[show[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+10.0%}" for k in show))


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    base['SPY'] = dict(bench['SPY'])
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]
    up = above_200(bench['SPY'])

    def eligible(t, d):
        return t in extra or added.get(t, '0000') <= d

    def risk_on(d):
        return up.get(d, True)

    if '--windows' in sys.argv:
        return windows_table(base, comb, calendar, eligible, risk_on, bench)
    flips = sum(1 for a, b in zip(calendar, calendar[1:]) if a >= START and up.get(a) != up.get(b))
    print(f"SPY crossed its 200-day average {flips} times since 2020\n")
    print(f"{'top 5, 6-month strength':46} {'total':>7} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>7} | {'2025-26':>7} | {'in cash':>7}")
    curves = {}
    for uni, prices in (('S&P 500 only', base), ('S&P 500 + Nasdaq-100', comb)):
        for flt, kw in (('no filter', {}), ('SPY filter, Friday check', dict(risk_on=risk_on)),
                        ('SPY filter, daily check', dict(risk_on=risk_on, risk_daily=True))):
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=eligible, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            cash = sum(1 for p in c if p[2] == 0) / len(c)
            label = f"{uni}, {flt}"
            curves[label] = [p[:2] for p in c]
            print(f"{label:46} {f['total']:+7.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+7.0%} | "
                  f"{o['total']:+7.0%} | {cash:7.0%}", flush=True)
    for b in ('SPY', 'QQQ'):
        pts = [[d, c] for d, c in bench[b] if d >= START]
        f = curve_stats([c for _, c in pts])
        i = curve_stats([c for d, c in pts if d < SPLIT])
        o = curve_stats([c for d, c in pts if d >= SPLIT])
        curves[b] = [[d, c] for d, c in bench[b] if d >= '2019-12-31']
        print(f"{'buy & hold ' + b:46} {f['total']:+7.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+7.0%} | {o['total']:+7.0%}")

    show = ['S&P 500 only, no filter', 'S&P 500 only, SPY filter, daily check',
            'S&P 500 + Nasdaq-100, no filter', 'S&P 500 + Nasdaq-100, SPY filter, daily check', 'SPY', 'QQQ']
    short = ['S&P', 'S&P+filter', 'S&P+NDX', 'S&P+NDX+filter', 'SPY', 'QQQ']
    years = {k: yearly(curves[k]) for k in show}
    print(f"\n{'year':6}" + ''.join(f"{s:>16}" for s in short))
    for y in sorted(years[show[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+16.0%}" for k in show))


if __name__ == '__main__':
    main()

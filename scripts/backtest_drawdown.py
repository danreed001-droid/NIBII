#!/usr/bin/env python3
"""Ways to shrink the top-5 rule's drawdown while keeping most of its gain,
since 2020, on S&P 500 + Nasdaq-100 (and the fair S&P-only universe):

  sizing      - vol target: scale the 5 positions down when the basket has
                been swinging more than 30/40/50% a year (rest in cash)
              - inverse-vol weights: calmer picks get more money
  picking     - correlation cap: skip a buy that moves too much like a stock
                already picked (stops 5 names in one theme)
              - risk-adjusted rank: score / volatility
              - hold 7 or 10 instead of 5
  account     - mix with QQQ (70/30, 50/50, rebalanced weekly)
              - equity-curve brake: half size while the account is more than
                15% (or 20%) below its high, back to full at a new high...
                or while it is below its 50-day average

Usage:
    python scripts/backtest_drawdown.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import SPLIT, START, WINDOWS, window_return  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ENGINE = {
    'current (top 5, equal)': {},
    'vol target 50%': dict(vol_target=0.50),
    'vol target 40%': dict(vol_target=0.40),
    'vol target 30%': dict(vol_target=0.30),
    'inverse-vol weights': dict(weighting='inv_vol'),
    'correlation cap 0.6': dict(max_corr=0.6),
    'correlation cap 0.75': dict(max_corr=0.75),
    'risk-adjusted rank': dict(risk_adj=True),
    'top 7': dict(top_n=7),
    'top 10': dict(top_n=10),
    'corr 0.6 + vol target 40%': dict(max_corr=0.6, vol_target=0.40),
}


def mix(curve, other, share, calendar):
    """Weekly-rebalanced mix: `share` in the strategy, the rest in `other` {date: close}."""
    rebal = set(last_sessions_of_weeks(calendar))
    out, a, b, prev = [], share, 1 - share, None
    for d, v in curve:
        if prev:
            a *= v / prev[0]
            b *= other[d] / prev[1]
        out.append([d, a + b])
        if d in rebal:
            a, b = (a + b) * share, (a + b) * (1 - share)
        prev = (v, other[d])
    return out


def brake(curve, dd=None, ma=None, low=0.5):
    """Equity-curve brake on the strategy's own curve, decided at yesterday's close:
    hold `low` of the position while it is more than `dd` below its high (full again
    at a new high), or while it is below its `ma`-day average."""
    out, val, peak, cut, hist = [], 1.0, curve[0][1], False, []
    for i, (d, v) in enumerate(curve):
        if i:
            r = v / curve[i - 1][1] - 1
            val *= 1 + r * (low if cut else 1)
        out.append([d, val])
        hist.append(v)
        peak = max(peak, v)
        if dd is not None:
            if v <= peak * (1 - dd):
                cut = True
            elif v >= peak:
                cut = False
        if ma is not None:
            cut = len(hist) >= ma and v < sum(hist[-ma:]) / ma
    return out


def row(label, c):
    f = curve_stats([p[1] for p in c])
    i = curve_stats([p[1] for p in c if p[0] < SPLIT])
    o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
    ws = ' | '.join(f"{window_return(c, a, b):+15.1%}" for a, b in WINDOWS.values())
    calmar = f['annual'] / -f['maxDD'] if f['maxDD'] else 0
    print(f"{label:30} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} {calmar:6.2f} | "
          f"{i['total']:+8.0%} {o['total']:+8.0%} | {ws}", flush=True)


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
    base['SPY'] = dict(bench['SPY'])
    comb['SPY'] = dict(bench['SPY'])
    qqq = dict(bench['QQQ'])

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, since 2020 ==")
        print(f"{'idea':30} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | "
              + ' | '.join(f"{w:>15}" for w in WINDOWS))
        for label, kw in ENGINE.items():
            kw = dict(kw)
            n = kw.pop('top_n', 5)
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=n, eligible=member, **kw)
            c = [p[:2] for p in r['curve']]
            curves[(uni, label)] = c
            row(label, c)
        cur = curves[(uni, 'current (top 5, equal)')]
        account = {
            '70% top 5 / 30% QQQ': mix(cur, qqq, 0.7, calendar),
            '50% top 5 / 50% QQQ': mix(cur, qqq, 0.5, calendar),
            'brake: half size 15% off high': brake(cur, dd=0.15),
            'brake: half size 20% off high': brake(cur, dd=0.20),
            'brake: half below 50-day avg': brake(cur, ma=50),
        }
        for label, c in account.items():
            curves[(uni, label)] = c
            row(label, c)
    for b in ('SPY', 'QQQ'):
        c = [[d, v] for d, v in bench[b] if d >= START]
        curves[b] = c
        row('buy & hold ' + b, c)
    pick = ['current (top 5, equal)', 'vol target 40%', 'correlation cap 0.6', 'corr 0.6 + vol target 40%',
            '70% top 5 / 30% QQQ', 'brake: half size 20% off high']
    keys = [('S&P 500 + Nasdaq-100', k) for k in pick] + ['QQQ']
    heads = ['current', 'vol40', 'corr0.6', 'corr+vol', '70/30 QQQ', 'brake20', 'QQQ']
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>11}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+11.0%}" for k in keys))


if __name__ == '__main__':
    main()

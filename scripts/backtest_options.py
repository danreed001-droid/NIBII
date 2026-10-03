#!/usr/bin/env python3
"""Rough option simulation of the Top 5 Strongest rule (mtl/options_sim.py).

Same picks as the dashboard (S&P 500 + Nasdaq-100, 6-1 month strength, top 5,
keep while top 10, Friday changes) held four ways, $500 split over 5 slots:
  stock            shares
  calls, same exposure    6-month delta-0.75 calls moving like the stock slot, rest in cash
  calls, all in           6-month delta-0.75 calls with the whole slot (~3-4x leverage)
  2-month ATM calls       short-dated at-the-money calls, rolled 2 weeks before expiry
Calls are Black-Scholes priced from realized volatility +10% (no historical
option prices exist here), 1.5% spread each way, 4% rate, rolled 60 days
before expiry. Since 2020 and the four windows asked about.

Usage:
    python scripts/backtest_options.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.options_sim import simulate  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

MODES = {
    'stock': dict(mode='stock'),
    'calls, same exposure': dict(mode='equiv', delta=0.75, months=6),
    'calls, all in': dict(mode='all_in', delta=0.75, months=6),
    '2-month ATM calls, all in': dict(mode='all_in', delta='atm', months=2, roll_days=14),
    'price+premium calls, all in': dict(mode='all_in', delta='premium', months=6),
    'price+premium, same exposure': dict(mode='equiv', delta='premium', months=6),
}
WINDOWS = [('2020-01-02', None), ('2025-02-19', '2025-04-09'), ('2026-01-01', '2026-03-31'),
           ('2026-09-01', None), ('2026-09-15', None)]


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    bars = {t: [(b[0][:10],) + tuple(b[1:]) for b in raw[t]['daily']]
            for t in names if t not in ETFS and raw[t].get('daily')}
    bars.update({t: [(b[0][:10],) + tuple(b[1:]) for b in bs] for t, bs in extra.items()})
    closes = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices = dict(closes)
    prices['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t in extra or added.get(t, '0000') <= d)

    for start, end in WINDOWS:
        r = run_momentum(prices, calendar, start, look=126, skip=21, top_n=5, eligible=eligible,
                         cost=0.0, rebalance_on_start=True)
        stop = end or calendar[-1]
        picks = [p for p in r['picks'] if p[0] <= stop]
        title = f"{picks[0][0]} to {stop}"
        print(f"\n== $500 from {title} ==")
        print(f"{'held as':28} {'value':>10} {'return':>8} {'worst drop':>11} {'rolls':>6}")
        curves = {}
        for label, kw in MODES.items():
            res = simulate(picks, closes, calendar, start_value=500.0, end=stop, **kw)
            c = res['curve']
            s = curve_stats([p[1] for p in c])
            curves[label] = c
            print(f"{label:28} ${c[-1][1]:9,.2f} {c[-1][1] / 500 - 1:+8.1%} {s['maxDD']:11.1%} {res['rolls']:6}", flush=True)
        for b in ('SPY', 'QQQ'):
            pts = [c for d, c in bench[b] if picks[0][0] <= d <= stop]
            s = curve_stats(pts)
            print(f"{b + ' (same $500)':28} ${500 * pts[-1] / pts[0]:9,.2f} {pts[-1] / pts[0] - 1:+8.1%} {s['maxDD']:11.1%}")
        if end is None and start == '2020-01-02':
            years = {k: yearly(v) for k, v in curves.items()}
            print(f"\n{'year':6}" + ''.join(f"{k[:22]:>24}" for k in MODES))
            for y in sorted(years['stock']):
                print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+24.0%}" for k in MODES))


if __name__ == '__main__':
    main()

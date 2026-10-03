#!/usr/bin/env python3
"""When to place the trades: the rule decides on the Friday close, but you
can't trade after the close. Compared since 2020 on S&P 500 + Nasdaq-100:

  Friday close     - the backtest so far (a person trading in the last
                     minutes on Friday gets close to this)
  Monday open      - decide on Friday's close, trade at Monday's opening price
  Monday close     - decide on Friday's close, trade at Monday's close

Each alone and in the 80/20 plan with the best-of sleeve (the sleeve switch is
made on the same day as the stocks; its effect is tiny).

Usage:
    python scripts/backtest_execution.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra  # noqa: E402
from backtest_drawdown import row  # noqa: E402
from backtest_hedge import load_assets  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START, WINDOWS  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.sleeve import plan_curve, sleeve_curve  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    bars = {t: raw[t]['daily'] for t in sp}
    bars.update(extra)
    comb = {t: {b[0][:10]: b[4] for b in bs} for t, bs in bars.items()}
    opens = {t: {b[0][:10]: b[1] for b in bs} for t, bs in bars.items()}
    comb['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    sl, _ = sleeve_curve(load_assets(), calendar, START)

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    print(f"{'trade at':30} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | "
          + ' | '.join(f"{w:>15}" for w in WINDOWS))
    for label, ex in (('Friday close', None), ('Monday open', opens), ('Monday close', 'close')):
        c = [p[:2] for p in run_momentum(comb, calendar, START, look=126, skip=21, top_n=5, eligible=member,
                                         exec_next=ex)['curve']]
        row(f'{label}: top 5', c)
        row(f'{label}: 80/20 plan', plan_curve(c, sl, 0.8, 0.2, calendar))


if __name__ == '__main__':
    main()

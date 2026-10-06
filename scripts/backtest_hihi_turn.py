#!/usr/bin/env python3
"""Buy when the chart turns HI-HI (low -> high -> higher low -> higher high) - daily, hourly, or both.
Last 6 months only (entries 2026-04-01 .. 2026-09-15; exits by the last bar).

Structure read: the dashboard's (mtl/structure.py): swings = 3 bars each side,
the last 2 labeled swings - 'downtrend' when both are LH/LL (lo-lo), 'uptrend'
when both are HH/HL (hi-hi).

Entries
  daily hi-hi   yesterday's daily chart turned hi-hi (the day before it wasn't)
                -> buy at today's close
  hourly hi-hi  the hourly chart turns hi-hi -> buy at that hourly close
  both          the hourly chart turns hi-hi while the daily chart already reads
                hi-hi (the daily read is the previous close: nothing from the future)
Exits
  2 weeks / 4 weeks   hold 10 / 20 sessions
  hourly lo-lo        sell when the hourly chart reads lo-lo again (max 20 sessions)
Compared with the equal-weight average of all stocks (and SPY) over the same holding days.
One open trade per stock at a time. Universe: the scanner's ~500 stocks with hourly bars
(data/.bt_cache.pkl).

Usage:
    python scripts/backtest_hihi_turn.py
"""
import os
import pickle
import sys
from bisect import bisect_left, bisect_right

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.structure import structure_signal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START, LAST_ENTRY = '2026-04-01', '2026-09-15'
ETFS = {'SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLK', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC', 'SMH', 'GLD', 'TLT'}


def main():
    c = pickle.load(open(os.path.join(ROOT, 'data', '.bt_cache.pkl'), 'rb'))
    raw = c['raw']
    tick = [t for t in raw if raw[t].get('1h') and raw[t].get('daily') and t not in ETFS]
    spy = {b[0][:10]: b[4] for b in raw['SPY']['daily']} if 'SPY' in raw else {}
    days = sorted({b[0][:10] for t in tick for b in raw[t]['daily'] if b[0][:10] >= '2025-09-01'})
    dpos = {d: i for i, d in enumerate(days)}
    # equal-weight average stock (daily closes)
    close = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in tick}
    ew = [1.0]
    for i in range(1, len(days)):
        rs = [close[t][days[i]] / close[t][days[i - 1]] - 1 for t in tick
              if close[t].get(days[i]) and close[t].get(days[i - 1]) and abs(close[t][days[i]] / close[t][days[i - 1]] - 1) < 0.5]
        ew.append(ew[-1] * (1 + (np.mean(rs) if rs else 0)))
    EW = dict(zip(days, ew))
    first = dpos[next(d for d in days if d >= START)]

    trades = {k: [] for k in ('daily hi-hi', 'hourly hi-hi', 'both')}
    for n_t, t in enumerate(tick):
        D = [tuple(b) for b in raw[t]['daily']]
        Dd = [b[0][:10] for b in D]
        H = [tuple(b) for b in raw[t]['1h']]
        Hd = [b[0][:10] for b in H]
        # daily state at each day's close (from bars up to that close)
        dstate = {}
        for d in days[first - 15:]:
            j = bisect_right(Dd, d)
            if j < 30:
                continue
            dstate[d] = structure_signal(D[max(0, j - 160):j], n=3, lookback=2)['state']
        # hourly state at each hourly bar in the window
        h0 = bisect_left(Hd, days[first - 5])
        hstate = []
        for j in range(h0, len(H)):
            hstate.append((j, structure_signal(H[max(0, j - 200):j + 1], n=3, lookback=2)['state']))
        hs = {j: s for j, s in hstate}

        def daily_up(d):
            """Daily chart reads hi-hi as of the close BEFORE day d."""
            i = dpos.get(d)
            return i is not None and i >= 1 and dstate.get(days[i - 1]) == 'uptrend'

        def daily_turned(d):
            """It turned hi-hi at the close before d (the close before that it wasn't)."""
            i = dpos.get(d)
            return daily_up(d) and i >= 2 and dstate.get(days[i - 2]) != 'uptrend'

        def exit_after(entry_day, entry_px, mode):
            i = dpos[entry_day]
            hold = 10 if mode == '2w' else 20
            end_i = min(i + hold, len(days) - 1)
            if mode == 'hlolo':
                # first hourly bar after entry that reads lo-lo, within 20 sessions
                jj = bisect_right(Hd, entry_day)
                for j in range(jj, len(H)):
                    if Hd[j] > days[end_i]:
                        break
                    if hs.get(j) == 'downtrend':
                        return Hd[j], H[j][4]
            d = days[end_i]
            return d, close[t].get(d) or entry_px

        def record(kind, d_entry, px):
            for mode in ('2w', '4w', 'hlolo'):
                d_exit, px_out = exit_after(d_entry, px, mode)
                r = px_out / px - 1
                bench = EW[d_exit] / EW[d_entry] - 1
                sp = (spy.get(d_exit, 0) / spy.get(d_entry, 1) - 1) if spy.get(d_entry) else 0
                trades[kind].append((mode, t, d_entry, d_exit, r, r - bench, r - sp))

        # daily-end entries: buy at the close of the day the read is known (next day close)
        busy = ''
        for d in days[first:]:
            if d > LAST_ENTRY:
                break
            if d <= busy or not close[t].get(d):
                continue
            if daily_turned(d):
                record('daily hi-hi', d, close[t][d])
                busy = days[min(dpos[d] + 10, len(days) - 1)]
        # hourly-end entries (and 'both')
        busy_h, busy_b = '', ''
        prev_up = True
        for j, st in hstate:
            d = Hd[j]
            up = st == 'uptrend'
            if d < START or d > LAST_ENTRY:
                prev_up = up
                continue
            if up and not prev_up:
                px = H[j][4]
                if d > busy_h:
                    record('hourly hi-hi', d, px)
                    busy_h = days[min(dpos[d] + 10, len(days) - 1)]
                if d > busy_b and daily_up(d):
                    record('both', d, px)
                    busy_b = days[min(dpos[d] + 10, len(days) - 1)]
            prev_up = up
        if n_t % 100 == 0:
            print(f"  {n_t}/{len(tick)}", file=sys.stderr, flush=True)

    print(f"Buy when the chart turns hi-hi - entries {START} .. {LAST_ENTRY}, {len(tick)} stocks, exits by {days[-1]}")
    print(f"{'entry':12} {'exit':12} {'trades':>6} {'win%':>5} {'avg':>6} {'median':>7} {'vs avg stock':>12} {'beat it':>8} {'vs SPY':>7}")
    for kind, rows in trades.items():
        for mode, lab in (('2w', 'hold 2 wks'), ('4w', 'hold 4 wks'), ('hlolo', 'hourly lo-lo')):
            R = [r for r in rows if r[0] == mode]
            if not R:
                continue
            a = np.array([r[4] for r in R])
            ex = np.array([r[5] for r in R])
            sp = np.array([r[6] for r in R])
            print(f"{kind:12} {lab:12} {len(R):6} {np.mean(a > 0):5.0%} {a.mean():+6.1%} {np.median(a):+7.1%} {ex.mean():+12.1%} "
                  f"{np.mean(ex > 0):8.0%} {sp.mean():+7.1%}")
        print()
    # month by month for 'both' / 4 weeks
    R = [r for r in trades['both'] if r[0] == '4w']
    by = {}
    for r in R:
        by.setdefault(r[2][:7], []).append(r[5])
    print("both / hold 4 wks, vs the average stock by entry month: " + ', '.join(f"{m} {np.mean(v):+.1%} (n {len(v)})" for m, v in sorted(by.items())))
    allm = (EW[days[-1]] / EW[days[first]] - 1)
    print(f"the average stock {days[first]} → {days[-1]}: {allm:+.1%}; SPY {spy.get(days[-1], 0) / spy.get(days[first], 1) - 1:+.1%}")


if __name__ == '__main__':
    main()

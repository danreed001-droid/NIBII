#!/usr/bin/env python3
"""Auto mix checked every day vs only on Fridays, since 2020.

Auto mix: 100% top 5, 60/40 with the best-of sleeve while 2+ holdings are in a
daily lower-low downtrend. Friday-only (the live page): read at Friday's close,
changed at Monday's close. Daily: read at every close, changed at the next
day's close whenever the answer flips (the top 5 itself still changes weekly).
Also an 'out fast, back on Friday' hybrid: daily check to go 60/40, Friday-only
to go back to 100%.

Usage:
    python scripts/backtest_daily_check.py
"""
import os
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_drawdown import row  # noqa: E402
from backtest_hedge import load_assets  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START, WINDOWS  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.sleeve import plan_curve_dynamic, sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402


def daily_plan(main, sleeve, calendar, decide):
    """Mix reset at the next session's close whenever decide(date) (made at that
    close) differs from what is held, and every Monday back to the target split."""
    week_ends = set(last_sessions_of_weeks(calendar))
    nxt = {calendar[i]: calendar[i + 1] for i in range(len(calendar) - 1)}
    other = dict(sleeve)
    out, prev, a, b, target, pending, changes = [], None, None, None, None, {}, 0
    for d, v in main:
        if prev is None:
            target = decide(d)
            a, b = target, 1 - target
        else:
            a *= v / prev[0]
            b *= other[d] / prev[1]
        nav = a + b
        out.append([d, nav])
        if d in pending:                    # yesterday's decision fills today
            new = pending.pop(d)
            if new != target:
                changes += 1
            target = new
            a, b = nav * target, nav * (1 - target)
        s = decide(d)
        if (s != target or d in week_ends) and d in nxt:
            pending[nxt[d]] = s
        prev = (v, other[d])
    return out, changes


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    bars = {t: [(b[0][:10],) + tuple(b[1:5]) for b in raw[t]['daily']] for t in sp}
    bars.update({t: [(b[0][:10],) + tuple(b[1:5]) for b in bs] for t, bs in extra.items()})
    comb = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    comb['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    dates = {t: [b[0] for b in bs] for t, bs in bars.items()}
    sl, _ = sleeve_curve(load_assets(), calendar, START)

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    r = run_momentum(comb, calendar, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    top5 = [p[:2] for p in r['curve']]
    pdays = [p[0] for p in r['picks']]
    cache = {}

    def downs(d):
        if d not in cache:
            held = r['picks'][bisect_right(pdays, d) - 1][1] if bisect_right(pdays, d) else []
            n = 0
            for t in held:
                j = bisect_right(dates[t], d)
                n += structure_signal(bars[t][max(0, j - 320):j], n=3, lookback=2)['state'] == 'downtrend'
            cache[d] = n
        return cache[d]

    print("reading charts every day...", file=sys.stderr)
    week_ends = last_sessions_of_weeks(calendar)

    def friday(d):
        return 0.6 if downs(d) >= 2 else 1.0

    state = {'s': 1.0, 'last_fri': 1.0}

    def hybrid(d):   # daily to go defensive, Friday to come back
        if downs(d) >= 2:
            return 0.6
        return 1.0 if d in set(week_ends) else None

    print(f"{'auto mix check':34} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | "
          + ' | '.join(f"{w:>15}" for w in WINDOWS))
    curves = {}
    c = plan_curve_dynamic(top5, sl, calendar, friday)
    curves['Friday only (live page)'] = c
    row('Friday only (live page)', c)
    c, ch = daily_plan(top5, sl, calendar, friday)
    curves['every day'] = c
    row('every day', c)
    print(f"{'':34} mix changes: {ch} ({ch / (len(c) / 252):.0f} a year)")
    held = {'v': 1.0}
    we = set(week_ends)

    def hyb(d):
        if downs(d) >= 2:
            held['v'] = 0.6
        elif d in we:
            held['v'] = 1.0
        return held['v']
    c, ch = daily_plan(top5, sl, calendar, hyb)
    curves['daily out, Friday back'] = c
    row('daily out, Friday back in', c)
    print(f"{'':34} mix changes: {ch} ({ch / (len(c) / 252):.0f} a year)")
    row('always 100% top 5', top5)
    keys = list(curves)
    years = {k: yearly(curves[k]) for k in keys}
    print(f"\nyear by year\n{'year':6}" + ''.join(f"{k[:16]:>18}" for k in keys))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+18.0%}" for k in keys))


if __name__ == '__main__':
    main()

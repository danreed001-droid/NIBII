#!/usr/bin/env python3
"""100% in the top 5 normally; switch to 80/20 (top 5 / best-of sleeve) while
one of the holdings is in a lower-low downtrend - back to 100% once none is.

Downtrend = the same swing-structure read the dashboard shows on each card
(lower highs and lower lows): daily chart (3-bar swings) or weekly chart
(2-bar swings), measured at each Friday close with data up to that close.
Trades and the mix change happen at Monday's close, like the live page.

Compared with always 100% and always 80/20, since 2020, S&P 500 + Nasdaq-100.

Usage:
    python scripts/backtest_dynamic_mix.py
    python scripts/backtest_dynamic_mix.py --sp-only   # the fair S&P 500-only universe
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
from mtl.backtest import resample  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.sleeve import sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402


def dynamic_plan(main, sleeve, calendar, split_at):
    """Main/sleeve mix reset at the session after each week's last session
    (Monday's close) to split_at(friday) - the stock share decided that Friday."""
    week_ends = last_sessions_of_weeks(calendar)
    idx = {d: i for i, d in enumerate(calendar)}
    reset = {}
    for f in week_ends:
        i = idx[f] + 1
        if i < len(calendar):
            reset[calendar[i]] = split_at(f)
    other = dict(sleeve)
    out, prev, a, b, share = [], None, None, None, []
    for d, v in main:
        if prev is None:
            s = split_at(d)
            a, b = s, 1 - s
        else:
            a *= v / prev[0]
            b *= other[d] / prev[1]
        nav = a + b
        out.append([d, nav])
        if d in reset:
            a, b = nav * reset[d], nav * (1 - reset[d])
        share.append(a / (a + b))
        prev = (v, other[d])
    return out, sum(share) / len(share)


def main():
    sp_only = '--sp-only' in sys.argv
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = {} if sp_only else load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    bars = {t: [(b[0][:10] + 'T00:00:00',) + tuple(b[1:5]) for b in raw[t]['daily']] for t in sp}
    bars.update({t: [(b[0][:10] + 'T00:00:00',) + tuple(b[1:5]) for b in bs] for t, bs in extra.items()})
    comb = {t: {b[0][:10]: b[4] for b in bs} for t, bs in bars.items()}
    comb['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]
    dates = {t: [b[0][:10] for b in bs] for t, bs in bars.items()}
    sl, _ = sleeve_curve(load_assets(), calendar, START)

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    r = run_momentum(comb, calendar, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    top5 = [p[:2] for p in r['curve']]
    pick_days = [p[0] for p in r['picks']]

    def holdings(d):
        i = bisect_right(pick_days, d) - 1
        return r['picks'][i][1] if i >= 0 else []

    cache = {}

    def down(t, d, tf):
        key = (t, d, tf)
        if key not in cache:
            j = bisect_right(dates[t], d)
            if tf == 'D':
                st = structure_signal(bars[t][max(0, j - 320):j], n=3, lookback=2)['state']
            else:
                st = structure_signal(resample(bars[t][max(0, j - 800):j], 'W')[0], n=2, lookback=2)['state']
            cache[key] = st == 'downtrend'
        return cache[key]

    def rule(tf, need, low):
        def split_at(f):
            n = sum(down(t, f, tf) for t in holdings(f))
            return low if n >= need else 1.0
        return split_at

    print("computing chart structure each Friday...", file=sys.stderr)
    plans = {
        'always 100% top 5': lambda f: 1.0,
        'always 80/20': lambda f: 0.8,
        '80/20 if 1+ holding daily downtrend': rule('D', 1, 0.8),
        '80/20 if 2+ holdings daily downtrend': rule('D', 2, 0.8),
        '80/20 if 1+ holding weekly downtrend': rule('W', 1, 0.8),
        '60/40 if 1+ holding daily downtrend': rule('D', 1, 0.6),
        '60/40 if 2+ holdings daily downtrend': rule('D', 2, 0.6),
        '60/40 if 1+ holding weekly downtrend': rule('W', 1, 0.6),
    }
    print(f"{'mix':38} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | "
          + ' | '.join(f"{w:>15}" for w in WINDOWS) + " | avg in stocks")
    curves = {}
    for label, f in plans.items():
        c, avg = dynamic_plan(top5, sl, calendar, f)
        curves[label] = c
        sys.stdout.write(f"{label[:38]:38} ")
        row('', c)
        print(f"{'':38} avg share in the top 5: {avg:.0%}")
    keys = list(plans)[:5]
    years = {k: yearly(curves[k]) for k in keys}
    heads = ['100%', '80/20', 'D1 80/20', 'D2 80/20', 'W1 80/20']
    print(f"\nyear by year\n{'year':6}" + ''.join(f"{h:>11}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+11.0%}" for k in keys))


if __name__ == '__main__':
    main()

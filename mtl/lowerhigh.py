"""Lower-high exit (part of Boost + rotation, default since Oct 13, 2026).

A two-week step out of stocks when SPY's bigger swings turn down, without waiting for a weekly lower high
to be confirmed:

1. Confirmed: on SPY's weekly chart (swings LH_SWING = 4 weeks either side), the last swing high is lower
   than the one before, and SPY closes below it.
2. Early (no wait): the latest finished week that tops the LH_SWING weeks before it and every week since
   is lower than the last confirmed weekly swing high, SPY closes below that peak, and the daily chart has
   already turned: its last daily swing high (3 days either side) is lower than the one before and SPY
   closes below it.

On a fresh signal, while the plan would hold the Boost list, the whole account moves for LH_DAYS (10)
sessions into the stronger of TLT / GLD (the one in a daily uptrend with the steepest gradient, picked again
each day; T-bills when neither is rising, which the plan's no-T-bills swap turns into the one up more over
6 months if it is up, else cash: mtl/rotation.py no_bills), then goes back to whatever the plan holds. Both triggers count:
an early signal gets its two weeks, and when that same high is later confirmed (with SPY still below it)
it gets two more; otherwise the same lower high cannot fire again, only a new one can. While the plan holds TLT,
GLD or T-bills it is left alone. Like every rotation decision it is made at a close and traded at the next
close. Applied after the rotation and before the whipsaw half-switch and the narrow-market cash week.

Audit (Oct 13, 2026, stocks in the S&P 500 at the time, EP and CPWR left out, on top of the rest of the
plan): from 2000 34.9% a year before tax (22.1% after) vs 32.8% (20.8%) without it, worst drop -29% vs
-44%, Sharpe 1.16 vs 1.07; from 2010 35.9% vs 33.3% (-25% vs -34%); from 2016 43.9% vs 41.7% (-23% both);
from 2020 64.7% vs 61.4% (-27% both). Earlier versions the same day: one stretch per lower high (no second
two weeks on confirmation) 34.5%, 35.4%, 42.7%, 62.4% with the same worst drops (both triggers did better
from all four starts, most in 2010 and 2020); T-bills instead of TLT / GLD 33.7%, 34.3%, 42.4%, 61.8%,
worst drop -28% from 2000 (gold or bonds did better from all four starts, most in 2008 and 2011). Waiting for the weekly lower high to be confirmed (T-bills): 33.3%,
33.4%, 42.8%, 62.2% with worst drops -31%, -31%, -23%, -27%. The return edge depends on the timing: with
T-bills, 12 sessions instead of 10 or acting a day late beat the plan from only one of the four starts and
8 sessions from none (the smaller drops held in every variant), so count on the smaller drops, not the
extra return. Three weeks out instead of two, three-week swings, or a full daily downtrend instead of a
daily lower high each did worse than the plan from at least one start. Staying out until SPY's downtrend ended (instead of two weeks) cut
the drops but cost 2-8 points a year: momentum stocks rebound before SPY confirms. It fired about once a
year (27 confirmed signals since 2000, plus early ones), helped most in 2008, 2011, 2018 and 2022, and cost
in 2000, 2002 and 2010. It was designed after looking at the 2007-2011 and 2022 drops, so treat it as on
probation.

Pure and network-free: bars are [(date, open, high, low, close, ...)] oldest first (dividend-adjusted).
"""
from bisect import bisect_right

from mtl.rotation import weekly
from mtl.structure import find_swings

LH_SWING = 4          # weekly bars either side of a swing high
LH_DAYS = 10          # sessions out of stocks (the stronger of TLT / GLD, or cash) after a fresh signal
LH_LOOK = 700         # daily bars the weekly swings are read from
LH_DAILY_SWING = 3    # daily bars either side of a daily swing high
LH_DAILY_LOOK = 120   # daily bars the daily swings are read from
LH_TIE = 1e-6         # highs this close count as equal (rounding in dividend-adjusted prices)


def _lower(a, b):
    """True when high `a` is a lower high than `b`. An equal high (a double top) counts as lower, with a
    part-per-million tolerance so rounding in the adjusted prices can't decide a tie (Oct 16, 2026: SPY's
    $124.74 highs of Aug 3 and Sep 9, 2005 came out either way depending on the download)."""
    return a <= b * (1 + LH_TIE)


def lowerhigh_reading(daily, swing=LH_SWING):
    """The signal at the last bar of `daily` (SPY's daily bars up to the decision close, oldest first).

    Returns None when there are not two weekly swing highs yet, else a dict:
    on (bool), kind ('confirmed' / 'early' / None), key (date of the lower high that fires it),
    highs ([[date, price], [date, price]]: the last two confirmed weekly swing highs),
    peak ([date, price] or None: the early, unconfirmed weekly peak), daily ([[date, price], ...]: the last
    two daily swing highs) and close."""
    bars = list(daily[-LH_LOOK:])
    wk = weekly(bars)
    his = [s for s in find_swings(wk, n=swing) if s['type'] == 'high']
    if len(his) < 2:
        return None
    close = bars[-1][4]
    h1, h2 = his[-2], his[-1]
    out = dict(on=False, kind=None, key=h2['ts'], close=close, peak=None,
               highs=[[h1['ts'][:10], round(h1['price'], 2)], [h2['ts'][:10], round(h2['price'], 2)]], daily=[])
    dh = [s for s in find_swings(bars[-LH_DAILY_LOOK:], n=LH_DAILY_SWING) if s['type'] == 'high']
    out['daily'] = [[s['ts'][:10], round(s['price'], 2)] for s in dh[-2:]]
    if _lower(h2['price'], h1['price']) and close < h2['price']:
        out.update(on=True, kind='confirmed')
        return out
    # the latest finished week since the last confirmed high that tops the `swing` weeks before it and every week after it
    pk = None
    for q in range(len(wk) - 2, h2['i'], -1):
        if q >= swing and wk[q][2] >= max(b[2] for b in wk[q - swing:q]) and wk[q][2] > max(b[2] for b in wk[q + 1:]):
            pk = wk[q]
            break
    if pk is None:
        return out
    out['peak'] = [pk[0][:10], round(pk[2], 2)]
    if _lower(pk[2], h2['price']) and close < pk[2]:
        if len(dh) >= 2 and _lower(dh[-1]['price'], dh[-2]['price']) and close < dh[-1]['price']:
            out.update(on=True, kind='early', key=pk[0])
    return out


def lowerhigh_cash(spy_bars, calendar, start, modes, dest=None, swing=LH_SWING, days=LH_DAYS):
    """(out, log): {decision day: asset held instead of the Boost list}, and the signals that started a
    stretch, oldest first ([date, kind, key]). dest(d) picks the asset on each day of a stretch (the
    stronger of TLT / GLD, or 'BIL'); without it, T-bills. Only days the plan would hold the Boost list
    (modes[d] == 'boost') are read or changed; a signal fires when its (lower high, kind) differs from the
    last one that fired and no stretch is running, and covers `days` sessions from that close."""
    bdays = [b[0] for b in spy_bars]
    cash, log = {}, []
    key, until, frm = None, -1, 0
    for k, d in enumerate(calendar):
        if d < start or modes.get(d, 'boost') != 'boost':
            continue
        j = bisect_right(bdays, d)
        r = lowerhigh_reading(spy_bars[max(0, j - LH_LOOK):j], swing)
        if r is None:
            continue
        if r['on'] and (r['key'], r['kind']) != key and k > until:
            key, until, frm = (r['key'], r['kind']), k + days - 1, k
            log.append([d, r['kind'], r['key'][:10]])
        if frm <= k <= until:
            cash[d] = (dest(d) if dest else None) or 'BIL'
    return cash, log


def apply_lowerhigh(modes, why, cash, calendar):
    """New (modes, why): the stretch's asset on its days (cash: {date: asset}, or a set of dates for
    T-bills), with the switch reasons 'lowerhigh' (into it, or a change of asset) and 'lowerhigh-end' (back
    to the plan's own holding)."""
    m, w = dict(modes), dict(why)
    prev = None
    for d in calendar:
        if d not in modes and d not in cash:
            continue
        if d in cash:
            a = cash[d] if isinstance(cash, dict) else 'BIL'
            if prev != a:
                w[d] = 'lowerhigh'
            m[d] = a
            prev = a
        else:
            if prev not in (None, 'plan'):
                w[d] = 'lowerhigh-end'
            prev = 'plan'
    return m, w


def lowerhigh_state(spy_bars, cash, log, calendar, k, days=LH_DAYS):
    """For the scanner: today's reading, the current stretch ([first, last] decision days) if any, whether
    today is in it, and the recent signals (newest first)."""
    as_of = calendar[k]
    bdays = [b[0] for b in spy_bars]
    j = bisect_right(bdays, as_of)
    r = lowerhigh_reading(spy_bars[max(0, j - LH_LOOK):j])
    run = None
    if log and log[-1][0] <= as_of:
        k0 = calendar.index(log[-1][0])
        last = calendar[min(len(calendar) - 1, k0 + days - 1)]
        if as_of <= last or k0 + days - 1 >= len(calendar):
            run = [log[-1][0], last if k0 + days - 1 < len(calendar) else None]
    held = (cash.get(as_of) if isinstance(cash, dict) else 'BIL') if as_of in cash else None
    return dict(reading=r, inCash=as_of in cash, asset=held, run=run, log=log[::-1][:8], n=len(log),
                days=days, swing=LH_SWING)

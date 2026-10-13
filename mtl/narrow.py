"""Narrow-market cash week (part of Boost + rotation, default since Oct 13, 2026).

The warning fires at a close when three things line up:

1. SPY is within NARROW_HIGH (2%) of its 52-week (252-session) high;
2. the equal-weight S&P 500 (RSP) has lagged SPY by more than NARROW_LAG (1.5%) over the last
   NARROW_LOOK (63) sessions - a few large stocks are carrying the index;
3. the VIX is within NARROW_VIX (2) points of its 63-session low - the market is calm.

NARROW_DELAY (5) sessions after each warning day the whole account moves to T-bills for NARROW_DAYS
(5) sessions, then goes back to whatever the plan holds (stocks, TLT, GLD or T-bills). A warning that
repeats extends the cash week. Like every rotation decision it is made at a close and traded at the
next close.

Audit (Oct 13, 2026, stocks in the S&P 500 at the time, EP and CPWR left out; the warning needs RSP
and the VIX, so it can first act in 2012): from 2000 32.8% a year before tax (20.8% after) vs 30.6%
(19.6%), Sharpe 1.07 vs 0.97, worst drop -44% for both; from 2010 33.3% vs 30.1%; from 2016 41.7% vs
38.6% (worst drop -23% vs -29%); from 2020 61.4% vs 58.0% (-27% vs -31%). Since 2012 the plan lost
about 39% over the ~570 cash days, where random cash weeks of the same lengths gained in all but 0.14%
of 20,000 draws. It held with the warning thresholds moved (lag 1% or 2%, VIX within 1 or 3 points, 1%
or 3% from the high: better from all four starts each time) and with the cash week starting 3 to 7
sessions after the warning or lasting 3 to 7 sessions (better from 2000, 2010 and 2016; from 2020 some
were slightly worse). Waiting for a 5% drop in SPY or the holdings before going to cash, or using the
largest stocks or the momentum leaders lagging instead of the equal-weight index, did worse. It was
designed after looking at the 2018-2026 drops and cannot be checked before 2012 or abroad, so it is on
probation.
"""
from bisect import bisect_right

NARROW_HIGH = 0.98
NARROW_LAG = 0.015
NARROW_LOOK = 63
NARROW_VIX = 2.0
NARROW_DELAY = 5
NARROW_DAYS = 5


def _filled(px, calendar):
    """Closes on the calendar, carrying the last close forward (None before the first)."""
    out, last = [], None
    keys = sorted(px)
    j = 0
    for d in calendar:
        while j < len(keys) and keys[j] <= d:
            if px[keys[j]]:
                last = px[keys[j]]
            j += 1
        out.append(last)
    return out


def narrow_reading(spy_px, rsp_px, vix_px, calendar, k):
    """The three parts of the warning at calendar[k]: {'high', 'lag', 'vix', 'vixLow', 'on'} (None when
    there is not enough history)."""
    if k < 251:
        return None
    s = _filled(spy_px, calendar[k - 251:k + 1])
    e = _filled(rsp_px, calendar[k - NARROW_LOOK:k + 1])
    v = _filled(vix_px, calendar[k - NARROW_LOOK:k + 1])
    if None in s or None in e or None in v:
        return None
    hi = max(s)
    lag = (e[-1] / s[-1]) / (e[0] / s[-1 - NARROW_LOOK]) - 1
    vlo = min(v)
    on = s[-1] >= hi * NARROW_HIGH and lag < -NARROW_LAG and v[-1] <= vlo + NARROW_VIX
    return dict(high=s[-1] / hi - 1, lag=lag, vix=v[-1], vixLow=vlo, on=on)


def narrow_warnings(spy_px, rsp_px, vix_px, calendar):
    """Sorted warning dates on the calendar ({date: close} inputs)."""
    s = _filled(spy_px, calendar)
    e = _filled(rsp_px, calendar)
    v = _filled(vix_px, calendar)
    out = []
    for k in range(251, len(calendar)):
        win = s[k - 251:k + 1]
        if None in win or e[k] is None or e[k - NARROW_LOOK] is None or v[k] is None:
            continue
        vw = [x for x in v[k - NARROW_LOOK:k + 1] if x is not None]
        lag = (e[k] / s[k]) / (e[k - NARROW_LOOK] / s[k - NARROW_LOOK]) - 1
        if s[k] >= max(win) * NARROW_HIGH and lag < -NARROW_LAG and v[k] <= min(vw) + NARROW_VIX:
            out.append(calendar[k])
    return out


def narrow_cash_days(warn, calendar, delay=NARROW_DELAY, days=NARROW_DAYS):
    """Decision days on which the plan holds T-bills: the `days` sessions starting `delay` sessions after
    each warning day (decided at those closes, traded at the next close, like the rotation)."""
    idx = {d: i for i, d in enumerate(calendar)}
    out = set()
    for d in warn:
        i = idx.get(d)
        if i is None:
            continue
        for j in range(i + 1 + delay, min(len(calendar), i + 1 + delay + days)):
            out.add(calendar[j])
    return out


def apply_narrow(modes, why, cash, calendar):
    """New (modes, why): T-bills on the cash days whatever the plan would hold, with the switch reasons
    'narrow' (into the cash week) and 'narrow-end' (back to the plan's own holding)."""
    m, w = dict(modes), dict(why)
    prev = None
    for d in calendar:
        if d not in modes and d not in cash:
            continue
        if d in cash:
            if m.get(d) != 'BIL' or prev != 'cash':
                w[d] = 'narrow'
            m[d] = 'BIL'
            prev = 'cash'
        else:
            if prev == 'cash':
                w[d] = 'narrow-end'
            prev = 'plan'
    return m, w


def narrow_state(warn, cash, calendar, k):
    """For the scanner: the last warning, whether today is a warning day, and the current or next cash
    week ([first, last] decision days) if any."""
    as_of = calendar[k]
    past = [d for d in warn if d <= as_of]
    days = sorted(d for d in cash if d >= calendar[max(0, k - 10)])
    week = None
    if days:
        run = [days[0]]
        for d in days[1:]:
            if calendar.index(d) == calendar.index(run[-1]) + 1:
                run.append(d)
            elif run[-1] < as_of:
                run = [d]
            else:
                break
        if run[-1] >= as_of:
            week = [run[0], run[-1]]
    return dict(on=bool(past) and past[-1] == as_of, last=past[-1] if past else None,
                n=len(past), cash=week, inCash=as_of in cash)

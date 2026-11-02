"""Stretched-and-warned exit (the default plan, from Nov 2, 2026, on probation): when 3 or more of the eight dominoes are
down (mtl/dominoes.py) and SPY is stretched far above its 1-year trend, a plan in stocks steps into its haven for 20
sessions (4 weeks), starting from the first close where both are true.

The stretch: SPY's weekly closes (each week's last session) over the last 52 weeks, a straight line fitted to their
logs, and the latest weekly close's distance from that line in standard errors; 2 or more counts. Between weekly closes
the last reading holds. The dominoes read as on the scanner page; the Fed funds rate, the yield curve and oil come from
FRED a day or more late, so those three are read one session late.

Why: a market already stretched far above its trend while the dominoes have started to fall has no cushion. Strict
test (S&P 500 members as of each date, 0.15% a side; Nov 2, 2026): 45.8% a year from 2000 against 44.7%, the
spring-2000 drop -17% against -33%, Sharpe 1.38 against 1.33, the same worst drop (-33%, 2006) and the same from 2001
on. It acted only once in 26 years (Mar 24, 2000, the dot-com top; a start in Apr 2009 found the plan out of stocks) and
SPY's stretch then was 2.05, just over the line: at 2.5 the rule never acts, at 1.5 it acts 14 times and costs 1.5
points a year; with 2 dominoes it also acts twice in late 2006 (46.0%). So it rests on one trade and a line that
happens to catch it: on probation.

Pure: closes {date: close}, the dominoes' series {key: {date: value}}, a session calendar."""
from bisect import bisect_right
from datetime import date

import numpy as np

K = 3            # dominoes down
Z = 2.0          # standard errors above the 52-week line
WEEKS = 52
HOLD = 20        # sessions in the haven
START = '2026-11-02'   # live from the decision at this close
FRED_KEYS = ('fed', 'curve', 'oil')
# where the scanner reads the dominoes it needs (as scripts/dominoes.py, a shorter history)
YF = {'tech': '^IXIC', 'small': '^RUT', 'banks': 'FSRBX', 'transport': 'FSRFX', 'junk': 'VWEHX'}
FRED = {'fed': 'DFF', 'curve': 'T10Y3M', 'oil': 'DCOILWTICO'}


def _week(d):
    return date.fromisoformat(d).isocalendar()[:2]


def weekly_z(closes, calendar, weeks=WEEKS):
    """{date: z} on the calendar: each session carries the reading of the latest week-end session on or before it."""
    days = [d for d in calendar if closes.get(d)]
    ends = [days[j] for j in range(len(days)) if j + 1 == len(days) or _week(days[j]) != _week(days[j + 1])]
    zs = {}
    for j in range(weeks - 1, len(ends)):
        y = np.log([closes[d] for d in ends[j - weeks + 1:j + 1]])
        t = np.arange(weeks)
        b, a = np.polyfit(t, y, 1)
        res = y - (a + b * t)
        s = res.std(ddof=2)
        zs[ends[j]] = float(res[-1] / s) if s > 0 else 0.0
    out, keys = {}, sorted(zs)
    for d in calendar:
        i = bisect_right(keys, d) - 1
        if i >= 0:
            out[d] = zs[keys[i]]
    return out


def warn_counts(calendar, series, fred_lag=1):
    """{date: dominoes down} on the calendar (mtl/dominoes.py readings; FRED-based ones `fred_lag` sessions late)."""
    from mtl import dominoes as dm
    _, on = dm.readings(calendar, series)
    keys = [k for k, *_ in dm.DOMINOES]
    on = on.astype(int)
    for j, k in enumerate(keys):
        if k in FRED_KEYS and fred_lag:
            on[:, j] = np.r_[np.zeros(fred_lag, int), on[:-fred_lag, j]]
    return {d: int(n) for d, n in zip(calendar, on.sum(axis=1))}


def onsets(calendar, counts, zs, k=K, z=Z):
    """Closes where both conditions first hold (not at the close before)."""
    out, prev = [], False
    for d in calendar:
        now = counts.get(d, 0) >= k and zs.get(d, float('-inf')) >= z
        if now and not prev:
            out.append(d)
        prev = now
    return out


def out_days(calendar, starts, in_stocks, hold=HOLD):
    """The decision closes in the haven: from each start the plan was in stocks at, `hold` sessions (stock days only)."""
    pos = {d: i for i, d in enumerate(calendar)}
    out = set()
    for s in starts:
        if s not in pos or not in_stocks(s):
            continue
        for d in calendar[pos[s]:pos[s] + hold]:
            if in_stocks(d):
                out.add(d)
    return out


def apply_stretchwarn(modes, why, half, days, calendar, haven='BIL', reason='stretchwarn'):
    """New (modes, why, half, held): `haven` (T-bills, which the no-T-bills rule then turns into the haven pick) on the
    rule's days, with the switch reasons 'stretchwarn' (into the haven) and 'stretchwarn-end' (back to what the plan
    holds); held = the days it changed the holding."""
    m, w, h = dict(modes), dict(why), dict(half or {})
    held, prev = set(), None
    for d in calendar:
        if d not in m and d not in days:
            continue
        if d in days and m.get(d, 'boost') == 'boost':
            if prev != reason:
                w[d] = reason
            m[d] = haven
            h.pop(d, None)
            held.add(d)
            prev = reason
        else:
            if prev == reason:
                w.setdefault(d, reason + '-end')
            prev = 'plan'
    return m, w, h, held


def state(calendar, k, counts, zs, held, starts, missing=(), n=6):
    """For the scanner: tonight's reading (close k), whether the rule holds the haven at that close (active), when that
    stretch ends, the last n stretches it held ([first, last] decision days) and its starts."""
    d = calendar[k]
    runs = []
    pos = {x: i for i, x in enumerate(calendar)}
    for x in sorted(held):
        if runs and pos[runs[-1][1]] == pos[x] - 1:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    live = [x for x in starts if pos.get(x, -1) <= k < pos.get(x, -1) + HOLD]
    end = pos[live[-1]] + HOLD - 1 if live else None
    return dict(d=d, count=counts.get(d), z=round(zs[d], 2) if d in zs else None, k=K, zmin=Z, hold=HOLD, weeks=WEEKS,
                warn=counts.get(d, 0) >= K, stretched=zs.get(d, float('-inf')) >= Z, active=d in held,
                since=live[-1] if live else None, left=(end - k) if end is not None else None,
                log=runs[::-1][:n], n=len(runs), starts=list(starts)[-n:][::-1], missing=list(missing), live=START)

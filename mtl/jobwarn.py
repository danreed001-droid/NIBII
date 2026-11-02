"""Unemployment step-aside (the default plan, from Nov 2, 2026, on probation): when the unemployment rate has started to
climb (its 3-month average TH, 0.3 points, or more above its lowest 3-month average of the year before) while SPY is
under its MA-session (150-day) average, a plan in stocks holds its haven pick for HOLD sessions (21, about a month) from
the first close where both are true.

The rate is the monthly UNRATE series from FRED, each month's figure used only from LAG (36) days after the month's
first day (it is published on the first Friday of the next month). The 3-month average is over the last 63 sessions,
the year-before low over the 231 sessions ending 21 sessions earlier.

Why: a rising unemployment rate is one of the earliest signs of a recession, and with the market already under its
long average it marked the 2001-02 and 2008 bear markets. Part of the three-rule change of Nov 2, 2026 (with
mtl/nearhigh.py and mtl/hotcomm.py; see mtl/nearhigh.py for the strict-test figures); on its own it made 47.3% a year
from 2000 against 45.8%, but it was ahead in only 3 years and behind in 4, at 0.5 points it lost, and the figures
used are today's revised ones, not the first published: on probation.

Pure: SPY closes {date: close}, the monthly rate {YYYY-MM-01: %}, a session calendar."""
from bisect import bisect_right
from datetime import date, timedelta

import numpy as np

TH = 0.3
LAG = 36
MA = 150
HOLD = 21
AVG, GAP, LOW = 63, 21, 231
START = '2026-11-02'
FRED_ID = 'UNRATE'


def _onto(series, calendar, lag):
    pts = sorted(((date.fromisoformat(d) + timedelta(days=lag)).isoformat(), v) for d, v in series.items())
    ks = [p[0] for p in pts]
    out = np.full(len(calendar), np.nan)
    for i, d in enumerate(calendar):
        j = bisect_right(ks, d) - 1
        if j >= 0:
            out[i] = pts[j][1]
    return out


def _roll(a, n, f):
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        w = a[max(0, i - n + 1):i + 1]
        if np.isfinite(w).any():
            out[i] = f(w)
    return out


def readings(calendar, spy, unrate, th=TH, lag=LAG, ma=MA):
    """(flag per session, the rise above the year-before low per session, SPY / its average - 1 per session)."""
    u = _onto(unrate, calendar, lag)
    u3 = _roll(u, AVG, np.nanmean)
    past = np.r_[np.full(GAP, np.nan), u3[:-GAP]]
    lo = _roll(past, LOW, np.nanmin)
    rise = u3 - lo
    s = np.array([spy.get(d, np.nan) for d in calendar], float)
    for i in range(1, len(s)):
        if not np.isfinite(s[i]):
            s[i] = s[i - 1]
    avg = np.array([np.nanmean(s[max(0, i - ma + 1):i + 1]) for i in range(len(s))])
    flag = (np.nan_to_num(rise, nan=-9) >= th) & (s < avg)
    return flag, rise, s / avg - 1


def starts(calendar, flag, start=None):
    """Closes where the flag first holds (not at the close before), from `start` on."""
    return [d for i, d in enumerate(calendar) if flag[i] and (i == 0 or not flag[i - 1]) and (start is None or d >= start)]


def state(calendar, k, flag, rise, gap, held, sts, missing=False, n=6):
    """For the scanner: tonight's reading, whether the rule holds the haven at close k, and its last stretches."""
    d = calendar[k]
    pos = {x: i for i, x in enumerate(calendar)}
    runs = []
    for x in sorted(held):
        if runs and pos[runs[-1][1]] == pos[x] - 1:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    live = [x for x in sts if pos.get(x, -1) <= k < pos.get(x, -1) + HOLD]
    end = pos[live[-1]] + HOLD - 1 if live else None
    r = rise[k] if k < len(rise) else np.nan
    g = gap[k] if k < len(gap) else np.nan
    return dict(d=d, rise=round(float(r), 3) if np.isfinite(r) else None, spyGap=round(float(g), 4) if np.isfinite(g) else None,
                th=TH, ma=MA, hold=HOLD, on=bool(flag[k]) if k < len(flag) else False, active=d in held,
                since=live[-1] if live else None, left=(end - k) if end is not None else None,
                log=runs[::-1][:n], n=len(runs), starts=list(sts)[-n:][::-1], missing=bool(missing), live=START)

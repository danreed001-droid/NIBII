"""The candle re-entry rule (rule 19 of the default plan, from the close of Nov 5, 2026, on probation): after a real drop,
two red days that make a fresh low and then a day that closes above both of their opens put the plan in stocks for two
weeks, whatever the other rules say.

On SPY's daily bars, at the close of session k:
- sessions k-2 and k-1 are red (close under open);
- session k closes above the opens of both (the selling of two days undone in one);
- at k-1 SPY closes DROP (12%) or more under its highest close of the HIGH (252) sessions to k;
- the lower of the two red closes is at or under every close of the LOW - 1 (19) sessions before them: a fresh
  LOW (20)-session low.
Then the plan holds the Boost list on the decision days k through k + HOLD - 1 (10 sessions, two weeks), over the
rotation, the lower-high exit, the whipsaw switch, the narrow-market cash week, the rebound rule, the stretched-and-warned
exit, the unemployment step-aside and the price-break rule; only the Fed-day hold, last, still applies (it never moves the
account out of stocks). Decided at the close, traded at the next close, like the rest of the plan.

Why: in the plan's strict test (S&P 500 members as of each date, 0.15% a side; Nov 5, 2026) it made 52.6% a year from
2000 against 51.4% without it, 57.5 / 75.4 / 110.8% from 2010 / 2016 / 2020 against 55.7 / 73.2 / 106.6%, worst drop
-26% vs -27%, Sharpe 1.56 vs 1.54, ahead in 6 years and behind in 2 (t-stat 1.0). Of 27 nearby settings (an 8, 10 or
12% drop, a 15-, 20- or 30-session low, 5, 10 or 15 sessions held) 20 were ahead from every start and all 9 at 12% were.
It fired about 20 times since 2000 (2001-02, 2008, 2010, 2011, 2020, 2022, 2023) and October 2022 carries most of the
gain (+25.8 points that year); at a 10% drop it also fired in April 2025 and lost 24 points. Looser versions (any day
of a 10-15% drop, or under the 150-day average) bought back into the 2008 crash and lost 4-7 points a year with a -56%
worst drop. Found among 11 versions tried and the owner's idea from one chart: on probation.

Pure: SPY's bars [(date, open, high, low, close)] in calendar order, the session calendar."""
DROP = 0.12
HIGH = 252
LOW = 20
HOLD = 10
START = '2026-11-05'


def _series(bars, calendar):
    """(opens, closes) aligned to the calendar, None where SPY has no bar."""
    by = {b[0][:10]: b for b in bars}
    o = [by[d][1] if d in by else None for d in calendar]
    c = [by[d][4] if d in by else None for d in calendar]
    return o, c


def reading(o, c, k, drop=DROP, high=HIGH, low=LOW):
    """At session k: dict(reds, above, deep, fresh, signal, dd) or None when the bars are too short or missing."""
    if k < max(high, low + 2) or None in (o[k], c[k], o[k - 1], c[k - 1], o[k - 2], c[k - 2]):
        return None
    w = [x for x in c[k - high + 1:k + 1] if x is not None]
    lw = [x for x in c[k - low - 1:k - 2] if x is not None]
    if len(w) < high * 0.9 or not lw:
        return None
    dd = 1 - c[k - 1] / max(w)
    reds = c[k - 2] < o[k - 2] and c[k - 1] < o[k - 1]
    above = c[k] > max(o[k - 1], o[k - 2])
    deep = dd >= drop
    fresh = min(c[k - 2], c[k - 1]) <= min(lw)
    return dict(reds=bool(reds), above=bool(above), deep=bool(deep), fresh=bool(fresh), signal=bool(reds and above and deep and fresh),
                dd=round(dd, 4))


def signals(bars, calendar, start=START, **kw):
    """The sessions (indexes into calendar) from `start` on whose close the rule fires."""
    o, c = _series(bars, calendar)
    out = []
    for k in range(len(calendar)):
        if calendar[k] < start:
            continue
        r = reading(o, c, k, **kw)
        if r and r['signal']:
            out.append(k)
    return out


def candle_days(bars, calendar, start=START, hold=HOLD, **kw):
    """(days, signal dates): the decision days from `start` on which the rule holds stocks."""
    days, sig = set(), []
    for k in signals(bars, calendar, start, **kw):
        sig.append(calendar[k])
        days.update(calendar[j] for j in range(k, min(len(calendar), k + hold)))
    return days, sig


def apply_candle(modes, why, half, days, calendar):
    """New (modes, why, half, held): the Boost list (and no whipsaw half) on the rule's days, with the switch reasons
    'candle' (into stocks) and 'candle-end' (back to what the plan holds); held = the days it changed the holding."""
    m, w, h = dict(modes), dict(why), dict(half or {})
    held, prev = set(), None
    for d in calendar:
        if d not in modes and d not in days:
            continue
        if d in days:
            if m.get(d, 'boost') != 'boost' or d in h:
                if prev != 'candle':
                    w[d] = 'candle'
                m[d] = 'boost'
                h.pop(d, None)
                held.add(d)
                prev = 'candle'
            else:
                prev = 'plan'
        else:
            if prev == 'candle' and m.get(d, 'boost') != 'boost':
                w[d] = 'candle-end'
            prev = 'plan'
    return m, w, h, held


def candle_state(bars, calendar, k, held, sig, hold=HOLD, n=6):
    """For the scanner: tonight's reading, whether the rule holds stocks for the next session and how many sessions it
    has left, and the recent signals (newest first)."""
    o, c = _series(bars, calendar)
    r = reading(o, c, k) or {}
    until = None
    for s in sig:
        i = calendar.index(s) if s in calendar else None
        if i is not None and i <= k < i + hold:
            until = i + hold - 1 - k
    return dict(r, onNext=until is not None and until >= 1, left=until, active=calendar[k] in held,
                log=list(sig)[::-1][:n], n=len(sig), drop=DROP, low=LOW, hold=hold, since=START)

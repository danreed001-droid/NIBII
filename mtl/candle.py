"""The candle re-entry rule (rule 19 of the default plan, from the close of Nov 5, 2026, on probation): after a real drop,
two red days that make a fresh low and then a day that closes above both of their opens put the plan in stocks for two
weeks, whatever the other rules say.

On SPY's daily bars, at the close of session k:
- sessions k-2 and k-1 are red (close under open);
- session k closes above the opens of both (the selling of two days undone in one);
- at k-1 SPY closes DROP (12%) or more, but no more than CAP (30%), under its highest close of the HIGH (252) sessions
  to k (since Nov 7, 2026: deeper than that is a crash, where the pattern has been a bounce before more selling);
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

The 30% cap (Nov 7, 2026): replayed in six markets abroad (UK, Germany, France, Canada, Australia, Hong Kong, 2005-2026)
the rule cost points in all six, mostly by buying back in during the 2008 crash 30-50% down (Germany 2008 -48.5% with
it vs -13.6% without). Of 9 stricter versions, only the cap was ahead both in the US (54.3% a year from 2000 vs 54.1%,
the same from 2010 / 2016 / 2020, worst drop -26%; it skips Jul 2002 and Mar 24, 2020, and 2002 gains 3.7 points) and
abroad (+0.5 points a year on average, ahead in 4 markets, behind in none). Abroad the rule is still a little worse
than none (-0.7 points a year on average), so it stays on probation.

Rule 26, the crash-bottom candle (from the close of Nov 20, 2026, on probation; the owner's pasted reversal shape): at the
close of session k on SPY's daily bars
- sessions k-3, k-2 and k-1 are the setup: at least two of them red, and the lowest of their closes at or under every
  close of the C26_FRESH (10) sessions before them (a fresh low);
- session k is green, its body (close minus open) longer than each of the three setup bodies, and it closes above all
  three setup highs (wicks included);
- at k-1 SPY closes C26_DROP (8%) or more under its highest close of the 252 sessions before k (no cap: this is the
  rule that catches the deep crash bottoms rule 19's 30% cap skips).
Then the plan holds the Boost list on the decision days k through k + C26_HOLD - 1 (5 sessions, one week), exactly
like rule 19 (the two share the days and the switch reasons).

Why: in the plan's strict test (S&P 500 members as of each date, 0.15% a side; Nov 20, 2026; Lab t325-t326) the live
plan made 65.8% a year from 2000 with it against 64.4% without, worst drop -25% both, and no year worse. On SPY since 2000
the shape after an 8% drop came 12 times, up 67% of the time two weeks later (+2.8% on average vs +0.4% any day). But the
whole gain is one trade, the Mar 10, 2009 bottom (+75 points that year); the other signals came while the plan already
held stocks. Closing above the setup's bodies instead of their highs, or holding two weeks, took bad 2002 / 2007 / 2022
entries; replacing rule 19 with it lost 2011 and 2022. On probation.

Pure: SPY's bars [(date, open, high, low, close)] in calendar order, the session calendar."""
DROP = 0.12
CAP = 0.30
HIGH = 252
LOW = 20
HOLD = 10
START = '2026-11-05'
C26_DROP = 0.08
C26_FRESH = 10
C26_HOLD = 5
C26_START = '2026-11-20'


def _series(bars, calendar):
    """(opens, closes) aligned to the calendar, None where SPY has no bar."""
    by = {b[0][:10]: b for b in bars}
    o = [by[d][1] if d in by else None for d in calendar]
    c = [by[d][4] if d in by else None for d in calendar]
    return o, c


def _ohlc(bars, calendar):
    """(opens, highs, closes) aligned to the calendar, None where SPY has no bar."""
    by = {b[0][:10]: b for b in bars}
    return ([by[d][1] if d in by else None for d in calendar], [by[d][2] if d in by else None for d in calendar],
            [by[d][4] if d in by else None for d in calendar])


def reading26(o, h, c, k, drop=C26_DROP, fresh=C26_FRESH, high=HIGH):
    """Rule 26 at session k: dict(reds, green, longer, above, fresh, deep, signal, dd, need) or None when the bars are
    too short or missing; need = the close session k has to beat (the highest setup high)."""
    if k < max(high, fresh + 3) or any(x is None for x in o[k - 3:k + 1] + h[k - 3:k + 1] + c[k - 3:k + 1]):
        return None
    w = [x for x in c[k - high:k] if x is not None]
    fw = [x for x in c[k - 3 - fresh:k - 3] if x is not None]
    if len(w) < high * 0.9 or not fw:
        return None
    setup = range(k - 3, k)
    dd = 1 - c[k - 1] / max(w)
    reds = sum(c[i] < o[i] for i in setup) >= 2
    green = c[k] > o[k]
    longer = all(abs(c[k] - o[k]) > abs(c[i] - o[i]) for i in setup)
    need = max(h[i] for i in setup)
    above = c[k] > need
    fr = min(c[i] for i in setup) <= min(fw)
    deep = dd >= drop
    return dict(reds=bool(reds), green=bool(green), longer=bool(longer), above=bool(above), fresh=bool(fr),
                deep=bool(deep), signal=bool(reds and green and longer and above and fr and deep), dd=round(dd, 4),
                need=round(need, 2))


def crash_days(bars, calendar, start=C26_START, hold=C26_HOLD, **kw):
    """Rule 26's (days, signal dates): the decision days from `start` on which it holds stocks."""
    o, h, c = _ohlc(bars, calendar)
    days, sig = set(), []
    for k in range(len(calendar)):
        if calendar[k] < start:
            continue
        r = reading26(o, h, c, k, **kw)
        if r and r['signal']:
            sig.append(calendar[k])
            days.update(calendar[j] for j in range(k, min(len(calendar), k + hold)))
    return days, sig


def reading(o, c, k, drop=DROP, high=HIGH, low=LOW, cap=CAP):
    """At session k: dict(reds, above, deep, capped, fresh, signal, dd) or None when the bars are too short or missing;
    capped = the fall is no deeper than `cap` (None: no cap)."""
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
    capped = cap is None or dd <= cap
    fresh = min(c[k - 2], c[k - 1]) <= min(lw)
    return dict(reds=bool(reds), above=bool(above), deep=bool(deep), capped=bool(capped), fresh=bool(fresh),
                signal=bool(reds and above and deep and capped and fresh), dd=round(dd, 4))


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


def candle_state(bars, calendar, k, held, sig, hold=HOLD, n=6, sig26=()):
    """For the scanner: tonight's reading, whether the rule holds stocks for the next session and how many sessions it
    has left, and the recent signals (newest first); r26 = rule 26's reading and signals the same way."""
    o, c = _series(bars, calendar)
    r = reading(o, c, k) or {}

    def left(sigs, ho):
        until = None
        for s in sigs:
            i = calendar.index(s) if s in calendar else None
            if i is not None and i <= k < i + ho:
                until = max(until or 0, i + ho - 1 - k)
        return until
    until19, until26 = left(sig, hold), left(sig26, C26_HOLD)
    until = max(x for x in (until19, until26, -1) if x is not None)
    until = None if until < 0 else until
    o_, h_, c_ = _ohlc(bars, calendar)
    r26 = dict(reading26(o_, h_, c_, k) or {}, onNext=until26 is not None and until26 >= 1, left=until26,
               log=list(sig26)[::-1][:n], n=len(sig26), drop=C26_DROP, freshN=C26_FRESH, hold=C26_HOLD, since=C26_START)
    return dict(r, onNext=until is not None and until >= 1, left=until, active=calendar[k] in held,
                log=list(sig)[::-1][:n], n=len(sig), drop=DROP, cap=CAP, low=LOW, hold=hold, since=START, r26=r26)

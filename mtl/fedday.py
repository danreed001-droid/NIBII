"""Fed-day hold of Boost + rotation (the default plan, since Oct 31, 2026, on probation): when the plan's rules would
leave stocks at tonight's close and the next session is a scheduled Fed decision day, it stays in stocks one more
session and leaves at the decision day's close (if the rules still say so). Only a full move out of stocks is held;
it never moves the account into stocks.

Why: stocks have tended to rise into Fed announcements, and the plan's own stocks did too: +0.45% a day on scheduled
decision days against +0.10% on other days since 2000, in each of 2000-07, 2008-15 and 2016-26. Staying one more day
after an exit usually costs the plan (-0.32% on average over 108 exits), but before a decision day it gained in 6 of
7 cases (+1.08% on average; only 2% of random picks of 7 other exits did as well).

Strict test (S&P 500 members as of each date, 0.15% a side; Oct 31, 2026): 46.3% a year from 2000 against 45.8%,
48.6% vs 48.4% from 2010, 60.1% vs 59.8% from 2016 and 87.6% vs 86.9% from 2020, the same worst drop (-29%); still
ahead at 0.30% a side. Holding 2-3 sessions before the decision added more on paper (46.8%) but all of it from one
episode (Jan 2009), and going into stocks for every decision day lost to trading costs (44.2%). It acts rarely (7
times in 26 years), so the gain rests on few cases: treat it as on probation.

The dates come from data/fomc_dates.json (scheduled meetings only); the scanner logs an issue when it covers fewer
than COVER_DAYS days ahead."""
import json
import os
from bisect import bisect_right
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FED_PATH = os.path.join(ROOT, 'data', 'fomc_dates.json')
COVER_DAYS = 180


def load(path=FED_PATH):
    """The scheduled decision days as a sorted list of 'YYYY-MM-DD' ([] when the file is missing)."""
    try:
        with open(path) as fh:
            return sorted(json.load(fh)['dates'])
    except (OSError, ValueError, KeyError):
        return []


def apply_fedday(modes, why, half, fed, calendar, upcoming=(), start=None):
    """New (modes, why, half, held). modes: {decision close: mode} ('boost' = the stock list; a missing day is
    'boost'), each traded at the next session's close. Where a decision takes the plan out of stocks and its trade
    would come at the close just before a decision day (the session after the trade session is in `fed`), that close
    keeps 'boost' (reason 'fedday', no whipsaw half): the next close decides again and trades at the decision day's
    close. The original switch reason moves to that next close. upcoming: the sessions after the calendar's last day
    (at least two), for tonight's decision on a live run. held = the decision closes it changed."""
    fed = set(fed)
    ext = list(calendar) + [d for d in upcoming if not calendar or d > calendar[-1]]
    m, w, h = dict(modes), dict(why), dict(half or {})
    held = set()
    for i in range(1, len(calendar)):
        d, p = calendar[i], calendar[i - 1]
        if i + 2 >= len(ext) or ext[i + 2] not in fed or (start and d < start):
            continue
        if modes.get(d, 'boost') != 'boost' and modes.get(p, 'boost') == 'boost':
            reason, nx = w.get(d), ext[i + 1]
            m[d] = 'boost'
            h.pop(d, None)
            w[d] = 'fedday'
            if reason and nx not in w and m.get(nx, 'boost') != 'boost':
                w[nx] = reason
            held.add(d)
    return m, w, h, held


HAVENS = ('TLTX', 'GLDX', 'TLT', 'GLD', 'DBMF', 'BIL', 'CASH0')


def stock_share(w):
    """The share of a holding {ticker: weight} in stocks (anything but the havens, T-bills and cash)."""
    tot = sum(w.values()) or 1.0
    return sum(x for t, x in w.items() if t not in HAVENS) / tot


def apply_to_schedule(sc, fed, calendar, start=None):
    """The rule on a trade schedule [(trade date, {ticker: weight})], each held from that close: where a trade takes
    the account from mostly stocks to mostly havens at a close whose next session is a decision day, the stock
    holding stays one more session and the trade moves to the decision day's close (unless a trade is already there).
    Returns (new schedule, [closes held])."""
    fed, idx = set(fed), {d: i for i, d in enumerate(calendar)}
    out, held, have = [], [], {d for d, _ in sc}
    for j, (d, w) in enumerate(sc):
        i = idx.get(d)
        prev = out[-1][1] if out else None
        if (prev is not None and i is not None and i + 1 < len(calendar) and calendar[i + 1] in fed
                and (start is None or d >= start) and stock_share(prev) >= 0.5 > stock_share(w)):
            out.append((d, prev))
            held.append(d)
            nx = calendar[i + 1]
            if nx not in have:
                out.append((nx, w))
            continue
        out.append((d, w))
    return out, held


def next_decision(fed, today):
    """The first scheduled decision day after `today`, or None."""
    i = bisect_right(fed, today)
    return fed[i] if i < len(fed) else None


def covered(fed, today, days=COVER_DAYS):
    """True when the list runs at least `days` calendar days past `today`."""
    return bool(fed) and (date.fromisoformat(fed[-1]) - date.fromisoformat(today)).days >= days


def fedday_state(fed, calendar, k, upcoming, held):
    """For the scanner: whether tonight's decision is held in stocks by the rule (active), whether a move out of stocks
    decided tonight would be held (watch: tomorrow's trade would land just before a decision day), the next decision
    day, and whether the date list still covers the next COVER_DAYS days."""
    today, fs = calendar[k], set(fed)
    after = list(calendar[k + 1:k + 3]) + [d for d in upcoming if d > calendar[-1]]
    return dict(active=today in held, watch=len(after) >= 2 and after[1] in fs, next=next_decision(fed, today),
                covered=covered(fed, today), last=fed[-1] if fed else None)

"""Earnings-jump weighting of the Boost list (the default plan, since Nov 2, 2026, on probation): at each trade, a held
stock that closed JUMP or more higher on its last earnings report's reaction day, within the last WITHIN sessions, gets
MULT times its money (on top of the buying-volume weighting, mtl/volweight.py: the two multiply).

The reaction day is the session the market first trades on the report: the report's own date for one before or during
the session ('bmo'), the next session for one after the close ('amc'). The jump is that session's close against the
close before it. Dates come from data/earnings_dates.json (SEC 8-K item 2.02 filings from 2004, kept current from
Yahoo by the nightly scan).

Why: stocks whose earnings surprise the market keep drifting the same way for weeks ("post-earnings drift"). Strict test
(S&P 500 members as of each date, 0.15% a side; Nov 2, 2026), on top of the plan with the buying-volume weighting: 44.7%
a year from 2000 against 42.7%, 49.4% vs 47.0% from 2010, 64.7% vs 60.0% from 2016 and 94.9% vs 86.6% from 2020, worst
drop -33% vs -34%, t-stat 1.8 on monthly returns (1.5 from 2005, when the dates start); it held for jumps of 2-5%, windows
of 3-6 months and 1.5x-3x, but not for a 2-month window, nearly all the gain came in 2016-2026 and it was found in a
search of about 20 ideas, so it is on probation.

Pure: prices {ticker: {date: close}}, a session calendar."""
import json
import os
from bisect import bisect_left, bisect_right

JUMP = 0.03
WITHIN = 63
MULT = 2.0
START = '2026-11-02'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data', 'earnings_dates.json')


def load(path=PATH):
    """{ticker: [[date, 'bmo'|'amc'], ...]} ({} when the file is missing or broken)."""
    try:
        with open(path) as fh:
            return json.load(fh).get('dates') or {}
    except (OSError, ValueError):
        return {}


def reaction_sessions(rows, calendar):
    """Sorted calendar indices of the sessions that first traded on each report."""
    out = set()
    for d, when in rows:
        j = bisect_left(calendar, d)
        if j < len(calendar) and calendar[j] == d and when == 'amc':
            j += 1
        if j < len(calendar):
            out.add(j)
    return sorted(out)


class EarnJump:
    """The rule on one calendar: the last reaction session on or before close k, its jump, and the multiplier."""

    def __init__(self, prices, dates, jump=JUMP, within=WITHIN, mult=MULT):
        self.prices, self.dates, self.jump, self.within, self.mult = prices, dates, jump, within, mult
        self._rx = {}

    def last(self, t, calendar, k):
        """(reaction session index, close-to-close move) of the latest report on or before close k, or (None, None)."""
        key = (t, len(calendar))
        if key not in self._rx:
            self._rx[key] = reaction_sessions(self.dates.get(t) or [], calendar)
        ks = self._rx[key]
        i = bisect_right(ks, k) - 1
        if i < 0 or ks[i] < 1:
            return None, None
        j = ks[i]
        px = self.prices.get(t) or {}
        a, b = px.get(calendar[j - 1]), px.get(calendar[j])
        return j, (b / a - 1 if a and b else None)

    def hit(self, t, calendar, k):
        j, r = self.last(t, calendar, k)
        return j is not None and r is not None and k - j <= self.within and r >= self.jump

    def factor(self, t, calendar, k):
        return self.mult if self.hit(t, calendar, k) else 1.0

    def info(self, t, calendar, k):
        j, r = self.last(t, calendar, k)
        return dict(d=calendar[j] if j is not None else None, move=round(r, 4) if r is not None else None,
                    ago=(k - j) if j is not None else None, hit=self.hit(t, calendar, k))


def merge(dates, ticker, rows):
    """Add [date, when] rows for ticker (no duplicates of a date; a newer 'when' replaces an older one). Returns added."""
    have = {d: w for d, w in dates.get(ticker) or []}
    n = 0
    for d, w in rows:
        if have.get(d) != w:
            n += d not in have
            have[d] = w
    dates[ticker] = [[d, w] for d, w in sorted(have.items())]
    return n


def from_yahoo(index_times, today):
    """[[date, when]] from Yahoo's earnings-date timestamps (New York time) up to today: 'amc' from 4pm on."""
    out = []
    for ts in index_times:
        d = str(ts)[:10]
        if d > today:
            continue
        hhmm = str(ts)[11:16]
        out.append([d, 'amc' if hhmm >= '16:00' else 'bmo'])
    return out

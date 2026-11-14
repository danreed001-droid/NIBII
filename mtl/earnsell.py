"""The near-high earnings sell (rule 23 of the default plan, from Nov 14, 2026, on probation): a held stock that went into
its earnings report near its 52-week high, fell on the report and then kept falling is sold, as the start of a down
'storyline' (the owner's reading of AAPL in early 2006).

- The reaction day is the session the market first trades on the report: the report's date for one before or during
  the session ('bmo'), the next session for one after the close ('amc'); a date that isn't a session counts from the
  next session. Dates come from data/earnings_dates.json (SEC 8-K item 2.02 filings from 2004, kept current from Yahoo
  by the nightly scan; mtl/earnjump.py).
- It counts when the close before it was within NEAR (5%) of the highest close of the HIGH (252) sessions before, and
  the reaction day closed DROP (3%) or more down.
- It is confirmed, and the holding sold at the next close (barred from buying back for the usual 4 weeks, as the other
  exits), when within WINDOW (10) sessions after the reaction day the stock closes CONFIRM (3%) or more down on a day,
  or (from the second session on) closes under its lowest close since the reaction day. Only reactions after the day
  the stock was bought count.

Why: a stock near its high that falls on its report and keeps falling has usually started a longer slide (AAPL Jan 2006
-22% after the sale, TSLA Jan 2021 -16%, FCX Jan 2006 -13%), while one that dips on a report from lower down usually
bounces. Strict test (S&P 500 members as of each date, 0.15% a side; Nov 14, 2026): AUDIT below. Without the near-high
condition it was behind from 2010; a plain sell on any 3%+ earnings drop lost 2-4 points a year. Nearby settings (6-month
or 2-year high, within 3-15%, a 2-5% drop, a 2-4% confirming day, 5-20 sessions) all came out ahead. Only 21 sales in
21 years and a t-stat of 1.4: on probation. US only (earnings dates exist for the US).

Pure: closes {ticker: {date: close}}, report dates {ticker: [[date, 'bmo'|'amc'], ...]}, a session calendar."""
from bisect import bisect_left

NEAR = 0.05
HIGH = 252
DROP = 0.03
CONFIRM = 0.03
WINDOW = 10
START = '2026-11-14'
AUDIT = ('with rule 24: 64.4% a year from 2000 vs 61.5% without both, 67.2% vs 63.3% from 2010, 85.9% vs 82.0% from 2016, '
         '128.9% vs 122.5% from 2020, worst drop -25% both, ahead in 15 years and behind in 2 (t-stat 1.6); rule 23 alone '
         '63.9%, ahead in 9 years and behind in 4 (t-stat 1.4)')


class EarnSell:
    def __init__(self, prices, dates, calendar, near=NEAR, high=HIGH, drop=DROP, confirm=CONFIRM, window=WINDOW):
        self.prices, self.dates, self.cal = prices, dates or {}, calendar
        self.near, self.high, self.drop, self.confirm, self.window = near, high, drop, confirm, window
        self.pos = {d: i for i, d in enumerate(calendar)}
        self._c, self._r = {}, {}

    def closes(self, t):
        """Closes on the calendar, carried over a missing session (None before the first)."""
        if t not in self._c:
            px, out, last = self.prices.get(t) or {}, [], None
            for d in self.cal:
                v = px.get(d)
                last = v if v else last
                out.append(last)
            self._c[t] = out
        return self._c[t]

    def reactions(self, t):
        """[(session index, change)] of each report's reaction day that came near the high and closed DROP+ down."""
        if t not in self._r:
            c, out = self.closes(t), []
            for d, when in self.dates.get(t) or []:
                i = self.pos.get(d)
                if i is None:
                    i, when = bisect_left(self.cal, d), 'bmo'
                if when == 'amc':
                    i += 1
                if i < 1 or i >= len(self.cal) or not c[i] or not c[i - 1]:
                    continue
                r = c[i] / c[i - 1] - 1
                w = [x for x in c[max(0, i - self.high):i] if x]
                if r <= -self.drop and w and c[i - 1] >= max(w) * (1 - self.near):
                    out.append((i, r))
            self._r[t] = out
        return self._r[t]

    def sell(self, t, k, entry_k=None):
        """hold_exit(t, k, entry_k): a confirmed near-high earnings drop after the day it was bought."""
        e = -1 if entry_k is None else entry_k
        if k <= e:
            return False
        c = self.closes(t)
        if k < 1 or not c[k] or not c[k - 1]:
            return False
        for i, _ in self.reactions(t):
            if e < i < k and k - i <= self.window:
                if c[k] / c[k - 1] - 1 <= -self.confirm:
                    return True
                if k - i >= 2 and c[k] < min(x for x in c[i:k] if x):
                    return True
        return False

    def info(self, t, k, entry_k=None):
        """For the scanner: the latest near-high earnings drop within WINDOW sessions (date, change), whether it is
        confirmed today, and the last session it can still be confirmed."""
        last = next(((i, r) for i, r in reversed(self.reactions(t)) if 0 <= k - i <= self.window), None)
        if not last:
            return None
        i, r = last
        return dict(date=self.cal[i], chg=round(r, 4), sell=self.sell(t, k, entry_k),
                    until=self.cal[min(len(self.cal) - 1, i + self.window)] if i + self.window < len(self.cal) else None)

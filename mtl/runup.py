"""The run-up skip (rule 20 of the default plan, from the close of Fri Nov 6, 2026, on probation): while the market is
falling, don't buy a stock that has just shot up.

At session k a pick is not bought when both hold:
- SPY closes under its close of SPY_LOOK (126) sessions earlier (down over about 6 months);
- the stock closes more than UP (50%) above its close of LOOK (42) sessions earlier (up 50%+ in about 2 months).
It is a filter on new buys only (a stock already held is kept), applied with the other buy filters after the green
light, which does not set it aside; a skipped top-5 stock leaves its slot in cash, as the fading filter's does, until
it leaves the top 5 or stops qualifying. Closes are carried over missing sessions.

Why: a stock bought after a near-vertical run while the market is in a downtrend has often been the top of the move
(a land-drilling contractor bought in mid-2008 after a 45% run lost about 80%). In the plan's strict test (S&P 500
members as of each date, 0.15% a side; Nov 6, 2026) it made 54.1% a year from 2000 against 52.6% without it, 58.5 /
77.1 / 114.1% from 2010 / 2016 / 2020 against 57.5 / 75.4 / 110.8%, the same -26% worst drop, better in 6 years and
worse in 1 (t-stat 1.8). In the neighbour check all 8 versions with a 40% or 50% run over 2 months were ahead from
every start, whichever market measure was used (SPY under its 100- / 150- / 200-day average, or down over 6 months);
a 30% run or a 4-month window was weaker. Most of the gain is in 2003, 2009 and 2026, and the idea came from looking
at the same history (the trade table: stretched stocks bought into a weak market did worse): on probation.

Pure: closes {ticker: {date: close}} (with SPY), a session calendar."""
UP = 0.50
LOOK = 42
SPY_LOOK = 126
MARKET = 'SPY'
MIN_K = 252
START = '2026-11-06'


class RunUp:
    def __init__(self, prices, calendar, up=UP, look=LOOK, spy_look=SPY_LOOK, market=MARKET):
        self.prices, self.cal = prices, calendar
        self.up, self.look, self.spy_look, self.market = up, look, spy_look, market
        self._c = {}

    def _closes(self, t):
        if t not in self._c:
            px, out, last = self.prices.get(t) or {}, [], None
            for d in self.cal:
                v = px.get(d)
                last = v if v else last
                out.append(last)
            self._c[t] = out
        return self._c[t]

    def spy_change(self, k):
        """SPY's change over the last spy_look sessions at session k, or None."""
        c = self._closes(self.market)
        if k < max(MIN_K, self.spy_look) or k >= len(c) or not c[k] or not c[k - self.spy_look]:
            return None
        return c[k] / c[k - self.spy_look] - 1

    def falling(self, k):
        g = self.spy_change(k)
        return g is not None and g < 0

    def run(self, t, k):
        """The stock's change over the last `look` sessions at session k, or None."""
        c = self._closes(t)
        if k < MIN_K or k >= len(c) or not c[k] or not c[k - self.look]:
            return None
        return c[k] / c[k - self.look] - 1

    def blocked(self, t, k):
        r = self.run(t, k)
        return self.falling(k) and r is not None and r > self.up

    def buy_ok(self, prev=None):
        """buy_when(t, k) for mtl.momentum.run_momentum: prev(t, k) and not blocked."""
        return lambda t, k: (prev(t, k) if prev else True) and not self.blocked(t, k)

    def info(self, k, tickers):
        g = self.spy_change(k)
        rows = {t: self.run(t, k) for t in tickers}
        return dict(spyChange=None if g is None else round(g, 4), falling=self.falling(k), up=self.up, look=self.look,
                    spyLook=self.spy_look, since=START,
                    runs={t: (None if r is None else round(r, 4)) for t, r in rows.items()},
                    blocked=[t for t, r in rows.items() if self.falling(k) and r is not None and r > self.up])

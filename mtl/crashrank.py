"""The crash-rebound ranking (rule 21 of the default plan, from the close of Mon Nov 9, 2026, on probation): after a
crash, once the market has turned up, rank the stocks most likely to rebound first.

At session k the rule is on when both hold:
- SPY closed DROP (30%) or more under its highest close of the last 252 sessions at some session within the last WIN
  (126) sessions (a crash, recently);
- SPY closes above its UP (50)-session average (it has turned up).
While it is on, the N (10) best stocks by the rebound score go to the front of the plan's ranking and count as
qualified (they need not beat SPY); the rest keep the plan's order, and every other rule (the buy filters, the
weighting, the exits, the havens) works as before. The rebound score is the average of three percentiles across the
ranked stocks: 3-month volatility (high is better), distance below the stock's 1-year high (deeper is better) and share
price (lower is better). It needs at least 30 stocks with 64 sessions of closes (41+ daily changes) to rank.
Closes are carried over missing sessions.

On a 12-month look-back (LOOK 252, as the plan abroad would run) the times double: SPY above its 100-session average
and a 252-session window (settings(252)).

Why: about 650 S&P 500 stocks doubled within a year in 2001-2025; most of them started as beaten-down, volatile,
low-priced stocks right after a crash (9.2% of members doubled when SPY was 30%+ under its high, 0.9% when it was
near it), and the plan held only 20% of those rebounders because it ranks on the last 6 months, which crashes empty. In
the plan's strict test (S&P 500 members as of each date, 0.15% a side; Nov 9, 2026) it made 60.4% a year from 2000
against 54.9%, 61.9 / 82.0 / 122.5% from 2010 / 2016 / 2020 against 59.4 / 79.0 / 116.7%, the same -25% worst drop,
37.7% after tax against 34.2%, better in 5 years and worse in 1 (2002), t-stat 1.5. It was on about 8% of the time:
late 2001 to 2003, the 2009 rebound and spring-summer 2020. Without the turn-up check it bought into falling bear
markets (2002, 2022; worst drop -35% to -45%). Abroad (9 markets, 12-month plan, the doubled times) it added 0.9 points
a year, better in 5 markets and worse in 1, with no bigger worst drop; with the 50-session check on the 6-month plan,
Germany's 2008-09 false bottoms made the worst drop deeper. Most of the gain is in 2003, 2009 and 2020: on probation.

Pure: closes {ticker: {date: close}} (with SPY), a session calendar."""
import numpy as np

DROP = 0.30
WIN = 126
UP = 50
N = 10
MIN_STOCKS = 30
MARKET = 'SPY'
START = '2026-11-09'


def settings(look=126):
    """The rule's settings for the plan's look-back: the times double on a 12-month look-back."""
    if look >= 252:
        return dict(drop=DROP, win=2 * WIN, up=2 * UP, n=N)
    return dict(drop=DROP, win=WIN, up=UP, n=N)


class CrashRank:
    def __init__(self, prices, calendar, drop=DROP, win=WIN, up=UP, n=N, market=MARKET):
        self.prices, self.cal = prices, calendar
        self.drop, self.win, self.up, self.n, self.market = drop, win, up, n, market
        self._c = {}
        self._on = None

    def closes(self, t):
        if t not in self._c:
            px = self.prices.get(t)
            if not px:
                self._c[t] = None
                return None
            c = np.array([px.get(d) or np.nan for d in self.cal], float)
            for i in range(1, len(c)):       # carry gaps
                if c[i] != c[i]:
                    c[i] = c[i - 1]
            self._c[t] = c
        return self._c[t]

    def on_days(self):
        """[bool] per session: the rule is on."""
        if self._on is None:
            s = self.closes(self.market)
            on = np.zeros(len(self.cal), bool)
            if s is not None:
                last = -10 ** 9
                for k in range(252, len(s)):
                    if np.isfinite(s[k]) and s[k] <= (1 - self.drop) * np.nanmax(s[k - 251:k + 1]):
                        last = k
                    on[k] = k - last <= self.win
                    if on[k] and self.up:
                        w = s[k - self.up + 1:k + 1]
                        on[k] = bool(np.isfinite(s[k]) and s[k] > np.nanmean(w))
            self._on = on
        return self._on

    def on(self, k):
        return bool(0 <= k < len(self.cal) and self.on_days()[k])

    def scores(self, k, tickers):
        """{ticker: rebound score} at session k for the tickers with enough closes ({} when fewer than MIN_STOCKS)."""
        vv, oh, px, tk = [], [], [], []
        for t in tickers:
            c = self.closes(t)
            if c is None or k < 252 or not np.isfinite(c[k]):
                continue
            w = c[k - 63:k + 1]
            lr = np.diff(np.log(w))
            hi = np.nanmax(c[k - 251:k + 1])
            if not (np.isfinite(lr).sum() > 40 and hi > 0):
                continue
            tk.append(t); vv.append(np.nanstd(lr)); oh.append(c[k] / hi - 1); px.append(c[k])
        if len(tk) < MIN_STOCKS:
            return {}

        def pr(x):
            return (np.argsort(np.argsort(np.array(x))) + 0.5) / len(x)
        sc = pr(vv) + (1 - pr(oh)) + (1 - pr(px))
        return dict(zip(tk, sc.tolist()))

    def front(self, k, tickers):
        """The N stocks the rule puts first at session k (empty while it is off)."""
        if not self.on(k):
            return []
        sc = self.scores(k, tickers)
        return [t for _, t in sorted(((s, t) for t, s in sc.items()), reverse=True)[:self.n]]

    def reorder(self, prev=None):
        """reorder(k, rows) for mtl.momentum.run_momentum: rows [(ticker, score, qualified)] best first."""
        def fn(k, rows):
            rows = prev(k, rows) if prev else rows
            if k < 252 or not self.on(k):
                return rows
            fr = self.front(k, [r[0] for r in rows])
            if not fr:
                return rows
            fs, by = set(fr), {r[0]: r for r in rows}
            return [(t, by[t][1], True) for t in fr] + [r for r in rows if r[0] not in fs]
        return fn

    def info(self, k, tickers=()):
        s = self.closes(self.market)
        hi = float(np.nanmax(s[k - 251:k + 1])) if s is not None and k >= 252 else None
        gap = float(s[k] / hi - 1) if hi else None
        ma = float(np.nanmean(s[k - self.up + 1:k + 1])) if s is not None and k >= self.up else None
        on = self.on_days()
        last_on = next((self.cal[i] for i in range(min(k, len(on) - 1), 251, -1) if on[i]), None)
        return dict(on=self.on(k), drop=self.drop, win=self.win, up=self.up, n=self.n, since=START,
                    spyOffHigh=None if gap is None else round(gap, 4),
                    spyVsAvg=None if (ma is None or s is None) else round(float(s[k] / ma - 1), 4),
                    lastOn=last_on, front=self.front(k, list(tickers)))

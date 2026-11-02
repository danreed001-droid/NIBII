"""Near-the-high weighting (the default plan, from Nov 2, 2026, on probation): at each trade, a held stock whose close is
within NEAR (3%) of its highest close of the last year (LOOK sessions, the close itself included) gets MULT (2x) its
money. It multiplies with the buying-volume and earnings-jump weightings (mtl/volweight.py, mtl/earnjump.py), and no
stock may hold more than mtl/volweight.CAP (40%) of the account (the excess spread over the others).

Why: stocks that are strong and also at their highs have tended to keep going (the 52-week-high effect). Strict test
(S&P 500 members as of each date, 0.15% a side; Nov 2, 2026), together with the hot-commodity buy skip
(mtl/hotcomm.py) and the unemployment step-aside (mtl/jobwarn.py), with the 40% cap: 47.6% a year from 2000 against
45.8%, 52.0% vs 49.4% from 2010, 67.9% vs 64.7% from 2016, 102.0% vs 94.9% from 2020, worst drop -28% vs -33%, Sharpe 1.45
vs 1.38. But the t-stat is only 0.9, it was ahead in 14 years and behind in 13, and nearby settings (2%, 5%, 7%) gave
less and fell behind from 2016 and 2020: on probation.

Pure: prices {ticker: {date: close}}, a session calendar."""
NEAR = 0.03
MULT = 2.0
LOOK = 252
START = '2026-11-02'


class NearHigh:
    def __init__(self, prices, near=NEAR, mult=MULT, look=LOOK):
        self.prices, self.near, self.mult, self.look = prices, near, mult, look

    def reading(self, t, calendar, k):
        """(close, highest close of the last `look` sessions) at close k, or (None, None)."""
        if k < self.look:
            return None, None
        px = self.prices.get(t) or {}
        c = px.get(calendar[k])
        if not c:
            return None, None
        hi = max((px[d] for d in calendar[k - self.look + 1:k + 1] if px.get(d)), default=None)
        return c, hi

    def hit(self, t, calendar, k):
        c, hi = self.reading(t, calendar, k)
        return c is not None and hi is not None and c >= (1 - self.near) * hi

    def factor(self, t, calendar, k):
        return self.mult if self.hit(t, calendar, k) else 1.0

    def info(self, t, calendar, k):
        c, hi = self.reading(t, calendar, k)
        return dict(off=round(c / hi - 1, 4) if c and hi else None, hit=self.hit(t, calendar, k))

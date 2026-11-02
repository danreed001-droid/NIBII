"""Buying-volume weighting of the Boost list (the default plan, since Nov 2, 2026, on probation): at each trade, a held
stock whose buying volume beats its selling volume by more than most S&P 500 stocks' gets twice the money of the others.

The measure: over the last LOOK sessions (3 months), the shares traded on the stock's up days divided by the shares
traded on its other days. A stock in the top third of the eligible S&P 500 members by that ratio (members with a year
of prices) counts as "buying"; at the trade, each buying stock gets MULT shares of the stock money and every other
stock one share. The plan's stocks, its slots (an empty slot is still a fifth) and its timing don't change; with no
buying stock, or all of them, the split is equal as before.

Why: among stocks that are already the strongest, heavy volume on the up days and light volume on the pullbacks tends
to mean steady buying, and those runs have tended to last. Strict test (S&P 500 members as of each date, 0.15% a side;
Nov 1, 2026): 42.7% a year from 2000 against 40.7% without it, 47.0% vs 45.5% from 2010, 60.0% vs 57.8% from 2016 and
86.6% vs 83.8% from 2020, worst drop -34% vs -35%, better in 15 of 27 years; still ahead at 0.30% a side (34.1% vs
32.7%). It held at 1.5x, 2x and 3x, for the top quarter, third or half, and over 1, 3 or 6 months (all 22 nearby
settings ahead from 2000), but it was found among many tested ideas and did not show up in eight foreign markets, so it
is on probation (mtl/volweight_check.py).

Pure: prices {ticker: {date: close}}, volumes {ticker: {date: shares}}, a session calendar."""

LOOK = 63            # sessions of up/down volume
HIST = 252           # sessions of price history a stock needs to count
MULT = 2.0           # a buying stock's share of the stock money, against 1 for the others
TOP = 1 / 3          # the share of the eligible members counted as buying (the top third by the ratio)
START = '2026-11-02'  # live from the trade at this close
CAP = 0.40           # no stock above this share of the account (since Nov 2, 2026, with the near-the-high weighting)


def ratio(px, vol, calendar, k, look=LOOK):
    """Shares traded on up closes / shares traded on the other closes over the `look` sessions to close k, or None
    (missing prices in the window, less than HIST sessions of history, or no volume on the other days)."""
    if k < max(look, HIST) or not px.get(calendar[k - HIST]):
        return None
    closes = [px.get(calendar[j]) for j in range(k - look, k + 1)]
    if any(c is None or c <= 0 for c in closes):
        return None
    up = dn = 0.0
    for j in range(1, len(closes)):
        v = vol.get(calendar[k - look + j]) or 0
        if closes[j] > closes[j - 1]:
            up += v
        else:
            dn += v
    return up / dn if dn > 0 else None


def _quantile(xs, q):
    """Linear-interpolated quantile (numpy's default)."""
    s = sorted(xs)
    if not s:
        return None
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def capped(w, cap):
    """No weight above `cap`: the excess spread over the others in proportion to their weights (as the backtest, up to
    10 passes)."""
    w = dict(w)
    for _ in range(10):
        over = sum(max(0.0, x - cap) for x in w.values())
        if over <= 1e-12:
            break
        under = [t for t, x in w.items() if x < cap]
        w = {t: min(cap, x) for t, x in w.items()}
        tu = sum(w[t] for t in under)
        if not under or tu <= 0:
            break
        for t in under:
            w[t] += over * w[t] / tu
    return w


class VolWeight:
    """Ratios and the buying threshold at each close, cached by date (shared across runs on the same data). With
    `extra` (the earnings-jump rule, mtl/earnjump.py, and the near-the-high rule, mtl/nearhigh.py, since Nov 2, 2026),
    each stock's share is also multiplied by their factors (a stock with all three gets 8 shares of the stock money
    against 1 for one with none), and with `cap` no stock holds more than that share of the account."""

    def __init__(self, prices, volumes, eligible, top_n=5, mult=MULT, top=TOP, look=LOOK, benchmark='SPY', extra=None, cap=None):
        # extra: a rule with factor(t, calendar, k) (mtl.earnjump.EarnJump), or a list of them (and mtl.nearhigh.NearHigh)
        self.prices, self.volumes, self.eligible = prices, volumes, eligible
        self.extras = [] if extra is None else list(extra) if isinstance(extra, (list, tuple)) else [extra]
        self.extra = self.extras[0] if self.extras else None
        self.cap = cap
        self.top_n, self.mult, self.top, self.look, self.bench = top_n, mult, top, look, benchmark
        self._cut = {}

    def cut(self, calendar, k):
        """({ticker: ratio} over the eligible members at close k, the buying threshold or None)."""
        d = calendar[k]
        if d not in self._cut:
            rows = {}
            for t, px in self.prices.items():
                if t == self.bench or not px.get(d) or not self.eligible(t, d):
                    continue
                v = self.volumes.get(t)
                if not v:
                    continue
                r = ratio(px, v, calendar, k, self.look)
                if r is not None:
                    rows[t] = r
            self._cut[d] = (rows, _quantile(list(rows.values()), 1 - self.top) if len(rows) > 30 else None)
        return self._cut[d]

    def buying(self, t, calendar, k):
        rows, th = self.cut(calendar, k)
        return th is not None and t in rows and rows[t] >= th

    def weights(self, target, calendar, k):
        """{ticker: weight} for the stocks in `target` at close k: each stock's share of the account's stock part,
        summing to len(target) / top_n (an empty slot stays a fifth in cash), MULT shares for a buying stock."""
        if not target:
            return {}
        m = {}
        for t in target:
            f = self.mult if self.buying(t, calendar, k) else 1.0
            for e in self.extras:
                f *= e.factor(t, calendar, k)
            m[t] = f
        tot = sum(m.values())
        w = {t: m[t] / tot * len(target) / self.top_n for t in target}
        return capped(w, self.cap) if self.cap else w

    def fn(self, calendar):
        """weighting(target, k) for mtl.momentum.run_momentum on this calendar."""
        return lambda target, k: self.weights(target, calendar, k)

    def card(self, stocks, calendar, k):
        """For the scanner: each stock's ratio, whether it counts as buying, and its weight at close k."""
        rows, th = self.cut(calendar, k)
        w = self.weights(list(stocks), calendar, k)
        return dict(d=calendar[k], threshold=round(th, 4) if th is not None else None, mult=self.mult, top=round(self.top, 4),
                    look=self.look, since=START, n=len(rows),
                    stocks=[dict(t=t, ratio=round(rows[t], 4) if t in rows else None, buying=self.buying(t, calendar, k),
                                 w=round(w.get(t, 0.0), 6), earn=self.extra.info(t, calendar, k) if self.extra else None,
                                 near=self.extras[1].info(t, calendar, k) if len(self.extras) > 1 else None)
                            for t in stocks])

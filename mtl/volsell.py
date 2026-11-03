"""Heavy-volume selling (the default plan, from Nov 3, 2026, on probation), two parts with one idea: stay away from a stock
that big holders are dumping.
- no new buy of a stock that had a down close on K (4) times or more its average volume of the 50 sessions before
  (at least 40 of them with volume) in the last WIN (5) sessions;
- a held stock that closes DROP (6%) or more down on K times or more that average volume is sold at the next close,
  as the other exits (barred from buying back for the usual 4 weeks) - since Nov 3, 2026 only while SPY closes at or
  above its MA (150)-session average: in a falling market a heavy-volume drop is often panic near a bottom.

Why: in the plan's strict test (S&P 500 members as of each date, 0.15% a side; Nov 3, 2026) the two together made
50.0% a year from 2000 against 48.2%, 53.6 / 71.0 / 104.4% from 2010 / 2016 / 2020 against 52.6 / 69.1 / 103.6%,
worst drop -27% vs -28%, Sharpe 1.50 vs 1.47, ahead in 14 years and behind in 10. 10 of 12 nearby settings (3-5x
volume and a 3- or 5-day window for the buy part, a 4-8% drop and 4-5x volume for the sell) were ahead from 2000;
with the sell at 3x volume it fired too often and lost. But the t-stat is only 1.2, a few trades carry it (2013,
2005, 2007 ahead; 2025 behind), and it was the best of 30 combinations of near-misses: on probation.

The rising-market limit on the sell (Nov 3, 2026, on probation): 50.5% a year from 2000 vs 50.0%, 55.1 / 72.4 / 105.1% from
2010 / 2016 / 2020 vs 53.6 / 71.0 / 104.4%, the same -27% worst drop and 2006; the 100- and 200-day averages gave 50.5-50.7%
and were ahead from every start too, but at 5x volume it lost, the t-stat is only 0.6 and it changed 10 years (rebound
years better, 2001, 2007 and 2008 a little worse): on probation.

Pure: closes and volumes {ticker: {date: value}} (with SPY for the rising-market check), a session calendar."""
K = 4.0
DROP = 0.06
WIN = 5
AVG_N, MIN_N = 50, 40
START = '2026-11-03'
MA = 150                 # the sell acts only while SPY closes at or above its MA-session average (since Nov 3, 2026)
MARKET = 'SPY'


class VolSell:
    def __init__(self, prices, volumes, calendar, k=K, drop=DROP, win=WIN, ma=MA, market=MARKET):
        self.prices, self.volumes, self.cal = prices, volumes, calendar
        self.k, self.drop, self.win, self.ma, self.market = k, drop, win, ma, market
        self._c, self._up = {}, {}

    def spy_gap(self, k):
        """SPY's close / its average of the last `ma` sessions - 1 at session k (gaps carried), or None."""
        px = self.prices.get(self.market) or {}
        if not self.ma or k < self.ma - 1 or k >= len(self.cal):
            return None
        cl, last = [], None
        for d in self.cal[max(0, k - self.ma - 20):k + 1]:
            last = px.get(d, last)
            cl.append(last)
        cl = cl[-self.ma:]
        if any(x is None for x in cl) or not cl[-1]:
            return None
        return cl[-1] / (sum(cl) / len(cl)) - 1

    def rising(self, k):
        """True when SPY closes at or above its `ma`-session average (unknown counts as rising: the sell acts)."""
        if k not in self._up:
            g = self.spy_gap(k)
            self._up[k] = g is None or g >= 0
        return self._up[k]

    def _arrays(self, t):
        """(volume / its average of the 50 sessions before, close-to-close change) per session, None where unknown."""
        if t not in self._c:
            px, vol = self.prices.get(t) or {}, self.volumes.get(t) or {}
            vs = [vol.get(d) for d in self.cal]
            cs, last = [], None
            for d in self.cal:
                last = px.get(d) or last
                cs.append(last)
            ratio, ret = [None] * len(self.cal), [None] * len(self.cal)
            for i in range(1, len(self.cal)):
                if cs[i] and cs[i - 1]:
                    ret[i] = cs[i] / cs[i - 1] - 1
                if i > AVG_N and vs[i]:
                    w = [x for x in vs[i - AVG_N:i] if x]
                    if len(w) >= MIN_N:
                        ratio[i] = vs[i] / (sum(w) / len(w))
            self._c[t] = (ratio, ret)
        return self._c[t]

    def heavy_down(self, t, k):
        """A close that was not up, on K x+ average volume, at session k."""
        ratio, ret = self._arrays(t)
        return ratio[k] is not None and ratio[k] >= self.k and not (ret[k] is not None and ret[k] > 0)

    def blocked(self, t, k):
        return any(self.heavy_down(t, j) for j in range(max(0, k - self.win + 1), k + 1))

    def buy_ok(self, prev=None):
        """buy_when(t, k) for mtl.momentum.run_momentum: prev(t, k) and no heavy-volume down close in the last WIN sessions."""
        return lambda t, k: (prev(t, k) if prev else True) and not self.blocked(t, k)

    def sell(self, t, k, entry_k=None):
        """hold_exit(t, k, entry_k): a close DROP+ down on K x+ average volume, after the day it was bought."""
        if entry_k is not None and k <= entry_k:
            return False
        ratio, ret = self._arrays(t)
        return ratio[k] is not None and ratio[k] >= self.k and ret[k] is not None and ret[k] <= -self.drop and self.rising(k)

    def info(self, t, k):
        ratio, ret = self._arrays(t)
        last = next((self.cal[j] for j in range(k, max(-1, k - self.win), -1) if self.heavy_down(t, j)), None)
        return dict(ratio=round(ratio[k], 2) if ratio[k] is not None else None, chg=round(ret[k], 4) if ret[k] is not None else None,
                    heavyDown=last, sell=self.sell(t, k))

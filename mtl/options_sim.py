"""Rough option simulation for the top-5 momentum rule.

No historical option prices are available (Yahoo only serves today's
chains), so calls are priced with Black-Scholes from each stock's recent
realized volatility (+10%, floor 20%) - an approximation that misses real
skew, earnings crush and liquidity, but shows how leverage and time decay
change the rule's results.

Each of the N slots carries its own money. When the rule sells a stock, that
slot's value moves to the replacement. Modes per slot:
  'stock'      - shares
  'equiv'      - calls sized to the same stock exposure (dollar delta =
                 slot value), the rest in cash earning `rate`
  'all_in'     - the whole slot value in calls (leveraged)
Calls are bought at mid*(1+spread), sold at mid*(1-spread), marked at mid,
and rolled to a new contract when fewer than `roll_days` calendar days are
left. Pure and network-free.
"""
import math
from datetime import date

SQ2 = math.sqrt(2.0)


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / SQ2))


def bs_call(s, k, t, vol, rate):
    """Black-Scholes call price; t in years."""
    if t <= 0:
        return max(0.0, s - k)
    v = vol * math.sqrt(t)
    d1 = (math.log(s / k) + (rate + 0.5 * vol * vol) * t) / v
    return s * _ncdf(d1) - k * math.exp(-rate * t) * _ncdf(d1 - v)


def bs_delta(s, k, t, vol, rate):
    if t <= 0:
        return 1.0 if s > k else 0.0
    v = vol * math.sqrt(t)
    return _ncdf((math.log(s / k) + (rate + 0.5 * vol * vol) * t) / v)


def strike_for_delta(s, t, vol, rate, delta):
    """Strike whose call delta is `delta` (bisection on strike)."""
    lo, hi = s * 0.05, s * 3.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs_delta(s, mid, t, vol, rate) > delta:
            lo = mid      # delta too high -> strike too low
        else:
            hi = mid
    return (lo + hi) / 2


def realized_vol(closes, k, window=63, bump=0.10, floor=0.20):
    """Annualized volatility of the last `window` daily log returns up to index k, +bump, floored."""
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(max(1, k - window + 1), k + 1)
            if closes[i - 1] and closes[i]]
    if len(rets) < 10:
        return floor + bump
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252)
    return max(floor, sd + bump)


def _years(d0, d1):
    return (date.fromisoformat(d1) - date.fromisoformat(d0)).days / 365.0


class Slot:
    """One position in one mode."""

    def __init__(self, mode, delta, months, rate, spread, roll_days):
        self.mode, self.delta, self.months = mode, delta, months
        self.rate, self.spread, self.roll_days = rate, spread, roll_days
        self.t = None          # ticker
        self.units = 0.0       # shares or option contracts (per 1 share)
        self.k = None          # strike
        self.expiry = None     # 'YYYY-MM-DD'
        self.cash = 0.0        # reserve earning `rate` (equiv mode), or idle cash
        self.cash_date = None

    def _expiry(self, d):
        y, m = int(d[:4]), int(d[5:7]) + self.months
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        return f"{y:04d}-{m:02d}-{min(int(d[8:10]), 28):02d}"

    def _accrue(self, d):
        if self.cash_date and self.cash > 0:
            self.cash *= math.exp(self.rate * _years(self.cash_date, d))
        self.cash_date = d

    def mid(self, d, s, vol):
        if self.t is None:
            return 0.0
        if self.mode == 'stock':
            return self.units * s
        return self.units * bs_call(s, self.k, max(0.0, _years(d, self.expiry)), vol, self.rate)

    def value(self, d, s, vol):
        self._accrue(d)
        return self.cash + self.mid(d, s, vol)

    def close(self, d, s, vol):
        """Sell the position at the bid; everything goes to cash."""
        self._accrue(d)
        if self.t is not None:
            px = self.mid(d, s, vol)
            self.cash += px if self.mode == 'stock' else px * (1 - self.spread)
        self.t, self.units, self.k, self.expiry = None, 0.0, None, None

    def open(self, t, d, s, vol):
        """Put the slot's cash into ticker t."""
        self._accrue(d)
        cap, self.t = self.cash, t
        if self.mode == 'stock':
            self.units, self.cash = cap / s, 0.0
            return
        self.expiry = self._expiry(d)
        tt = _years(d, self.expiry)
        self.k = s if self.delta == 'atm' else strike_for_delta(s, tt, vol, self.rate, self.delta)
        ask = bs_call(s, self.k, tt, vol, self.rate) * (1 + self.spread)
        if self.mode == 'all_in':
            self.units, self.cash = cap / ask, 0.0
        else:   # 'equiv': dollar delta = slot value, the rest in cash
            dl = bs_delta(s, self.k, tt, vol, self.rate)
            units = cap / (dl * s)
            if units * ask > cap:
                units = cap / ask
            self.units, self.cash = units, cap - units * ask

    def maybe_roll(self, d, s, vol):
        if self.mode != 'stock' and self.t is not None and \
                (date.fromisoformat(self.expiry) - date.fromisoformat(d)).days < self.roll_days:
            t = self.t
            self.close(d, s, vol)
            self.open(t, d, s, vol)
            return True
        return False


def simulate(picks, closes, calendar, start_value=500.0, n=5, mode='stock', delta=0.75, months=6,
             rate=0.04, spread=0.015, roll_days=60, end=None):
    """picks: [[date, [tickers]]] rebalance holdings (first entry = initial buy);
    closes: {ticker: {date: close}}; calendar: sorted dates.
    Returns dict(curve=[[date, value]], rolls=int, trades=int)."""
    end = end or calendar[-1]
    idx = {d: i for i, d in enumerate(calendar)}
    series = {t: [closes[t].get(d) for d in calendar] for t in {x for _, h in picks for x in h}}
    for t, s in series.items():   # carry prices forward over gaps
        last = None
        for i, v in enumerate(s):
            s[i] = v if v else last
            last = s[i]
    slots = [Slot(mode, delta, months, rate, spread, roll_days) for _ in range(n)]
    for sl in slots:
        sl.cash = start_value / n
        sl.cash_date = picks[0][0]
    rebal = {d: h for d, h in picks}
    curve, rolls, trades = [], 0, 0

    def px(t, d):
        return series[t][idx[d]]

    def vol(t, d):
        return realized_vol(series[t], idx[d])

    first = picks[0][0]
    for d in calendar:
        if d < first or d > end:
            continue
        if d in rebal:
            held = rebal[d]
            current = [sl.t for sl in slots]
            for sl in slots:
                if sl.t is not None and sl.t not in held:
                    sl.close(d, px(sl.t, d), vol(sl.t, d))
                    trades += 1
            for t in [t for t in held if t not in current]:
                sl = next((x for x in slots if x.t is None), None)
                if sl is not None and px(t, d):
                    sl.open(t, d, px(t, d), vol(t, d))
                    trades += 1
        for sl in slots:
            if sl.t is not None and sl.maybe_roll(d, px(sl.t, d), vol(sl.t, d)):
                rolls += 1
        total = sum(sl.value(d, px(sl.t, d), vol(sl.t, d)) if sl.t else sl.value(d, 0, 0) for sl in slots)
        curve.append([d, total])
    return dict(curve=curve, rolls=rolls, trades=trades)

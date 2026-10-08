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
Strike choice (`delta`): a delta like 0.75 (in the money), 'atm', or
'premium' - one premium out of the money (strike = price + that call's price).
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


def strike_at_premium(s, t, vol, rate, iters=60):
    """Strike K with K = s + call(K): one premium out of the money (stock 100,
    call worth 5 -> buy the 105 call). C(K) falls as K rises, so the fixed
    point is unique; found by bisection on K - s - C(K)."""
    lo, hi = s, s * 4.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if mid - s - bs_call(s, mid, t, vol, rate) < 0:
            lo = mid
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


SLEEVE_OTM, SLEEVE_IV, SLEEVE_DAYS, SLEEVE_SPREAD = 1.20, 0.80, 182, 0.04


def third_friday(y, m):
    d = date(y, m, 15)
    return d.replace(day=15 + (4 - d.weekday()) % 7)


def sleeve_call(closes, today, rate=0.04):
    """The call-sleeve trade for one stock at best-case pricing: a ~6-month call 20%
    out of the money, worth buying only while its implied volatility is at most 0.8 x
    the stock's 63-day realized volatility (the price the backtest's best case assumed)
    and the bid/ask is at most 4% of the mid price. `closes` = recent daily closes,
    oldest first. Returns dict(price, rv, maxIv, strike, expiry, maxPrice) or None."""
    if len(closes) < 64 or not closes[-1]:
        return None
    s = closes[-1]
    rv = realized_vol(closes, len(closes) - 1, bump=0.0, floor=0.0)
    t0 = date.fromisoformat(today)
    target = t0.toordinal() + SLEEVE_DAYS
    cands = [third_friday(t0.year + (t0.month - 1 + n) // 12, (t0.month - 1 + n) % 12 + 1) for n in range(4, 10)]
    exp = min(cands, key=lambda d: abs(d.toordinal() - target))
    step = 1 if s < 50 else 5 if s < 200 else 10
    k = round(s * SLEEVE_OTM / step) * step
    iv = max(0.20, rv * SLEEVE_IV)
    px = bs_call(s, k, (exp.toordinal() - t0.toordinal()) / 365.0, iv, rate)
    return dict(price=round(s, 2), rv=round(rv, 4), maxIv=round(iv, 4), strike=k, expiry=exp.isoformat(),
                maxPrice=round(px, 2))


def implied_vol(price, s, k, t, rate=0.04):
    """Black-Scholes implied volatility of a call price (bisection); None if out of range."""
    if price <= max(0.0, s - k * math.exp(-rate * t)) or t <= 0:
        return None
    lo, hi = 0.01, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs_call(s, k, t, mid, rate) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def quote_check(ticker, call, today):
    """Live best-case check for a sleeve call from the option chain (yfinance): the
    listed expiry and strike nearest the target, bid/ask, mid, implied vol of the mid,
    and ok = True/False (None when there is no two-sided quote, e.g. outside market hours)."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        exps = list(tk.options or [])
        if not exps:
            return None
        exp = min(exps, key=lambda e: abs(date.fromisoformat(e).toordinal() - date.fromisoformat(call['expiry']).toordinal()))
        ch = tk.option_chain(exp).calls
        row = ch.iloc[(ch['strike'] - call['strike']).abs().argsort()[:1]]
        k, bid, ask = float(row['strike'].iloc[0]), float(row['bid'].iloc[0] or 0), float(row['ask'].iloc[0] or 0)
    except Exception:   # noqa: BLE001 - quotes are best effort
        return None
    out = dict(expiry=exp, strike=k, bid=round(bid, 2), ask=round(ask, 2), mid=None, iv=None, spread=None, ok=None)
    if bid > 0 and ask >= bid:
        mid = (bid + ask) / 2
        t = (date.fromisoformat(exp).toordinal() - date.fromisoformat(today).toordinal()) / 365.0
        iv = implied_vol(mid, call['price'], k, t)
        out.update(mid=round(mid, 2), spread=round((ask - bid) / mid, 4), iv=round(iv, 4) if iv else None)
        out['ok'] = bool(iv and iv <= call['maxIv'] and (ask - bid) / mid <= SLEEVE_SPREAD)
    return out


def call_sleeve_curve(stock_curve, picks, prices, calendar, weight=0.20, budget=0.10, ivm=SLEEVE_IV,
                      spread=0.02, otm=SLEEVE_OTM, days=SLEEVE_DAYS, exit_before=21, rate=0.04):
    """Account value of the stock plan plus the call sleeve, daily.

    stock_curve: [[date, value]] of the stock plan; picks: [[date, [tickers]]] its
    holdings (each change = the day the trade fills). (1 - weight) follows the stock
    plan; `weight` is the sleeve: when a stock enters, a call `otm` above its price
    expiring ~`days` out is bought with budget / (calls held + 1) of the account (paid
    from sleeve cash), and sold when the stock leaves (or `exit_before` days before
    expiry). Every January the split is reset. Calls are Black-Scholes priced at
    best case: implied vol = ivm x 63-day realized vol (floor 20%), `spread` paid
    each way; idle cash earns nothing. No historical option prices are used."""
    idx = {d: i for i, d in enumerate(calendar)}
    ser = {}

    def series(t):
        if t not in ser:
            last, s = None, []
            for d in calendar:
                last = prices.get(t, {}).get(d) or last
                s.append(last)
            ser[t] = s
        return ser[t]
    vc = {}

    def vol(t, i):
        if (t, i) not in vc:
            s = series(t)
            r = [math.log(s[j] / s[j - 1]) for j in range(max(1, i - 62), i + 1) if s[j] and s[j - 1]]
            if len(r) < 20:
                vc[(t, i)] = 0.20
            else:
                m = sum(r) / len(r)
                vc[(t, i)] = max(0.20, math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252) * ivm)
        return vc[(t, i)]

    def price(p, i):
        s = series(p['t'])[i]
        return bs_call(s, p['k'], max(0.0, _years(calendar[i], p['exp'])), vol(p['t'], i), rate) if s else 0.0

    entries, exits, prev = {}, {}, []
    for d, held in picks:
        for t in held:
            if t not in prev:
                entries.setdefault(d, []).append(t)
        for t in prev:
            if t not in held:
                exits.setdefault(d, []).append(t)
        prev = held
    values = dict((d, v) for d, v in stock_curve)
    days_ = [d for d, _ in stock_curve if d in idx]
    stock, cash = values[days_[0]] * (1 - weight), values[days_[0]] * weight
    openp, out, year, prev_d = [], [], days_[0][:4], days_[0]
    for d in days_:
        i = idx[d]
        stock *= values[d] / values[prev_d]
        prev_d = d
        for p in list(openp):
            if p['t'] in exits.get(d, []) or _years(d, p['exp']) * 365 <= exit_before:
                cash += p['n'] * price(p, i) * (1 - spread)
                openp.remove(p)
        optv = sum(p['n'] * price(p, i) * (1 - spread) for p in openp)
        total = stock + cash + optv
        if d[:4] != year:
            year = d[:4]
            cash = max(0.0, total * weight - optv)
            stock = total - optv - cash
        for t in entries.get(d, []):
            s0 = series(t)[i]
            spend = min(cash, total * budget / (len(openp) + 1))
            if not s0 or spend <= 0:
                continue
            p = dict(t=t, k=s0 * otm, exp=date.fromordinal(date.fromisoformat(d).toordinal() + days).isoformat())
            cost = price(p, i) * (1 + spread)
            if cost <= 0:
                continue
            p['n'] = spend / cost
            cash -= spend
            openp.append(p)
        out.append([d, stock + cash + sum(p['n'] * price(p, i) * (1 - spread) for p in openp)])
    return out


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
        if self.delta == 'atm':
            self.k = s
        elif self.delta == 'premium':
            self.k = strike_at_premium(s, tt, vol, self.rate)
        else:
            self.k = strike_for_delta(s, tt, vol, self.rate, self.delta)
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

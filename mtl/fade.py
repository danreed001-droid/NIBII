"""Fading-energy filter on new buys (default plan since Oct 16, 2026).

A stock is fading when, at the decision close, both:
- its trading volume has dried up: average shares traded over the last 21 sessions is under VOL_TH (70%) of
  the average over the 105 sessions before them, and
- its daily swings have shrunk: the volatility of its last 21 daily moves is under SWING_TH (55%) of its normal
  volatility (the 189 sessions before the last 63).

The default plan doesn't buy a fading stock. With `buy_max_rank` = top_n (mtl/momentum.py) its slot stays in
cash instead of going to the next-ranked stock, until the stock drops out of the top 5 or stops fading. A stock
already held is kept as usual. You-2 applies the same check to the viewer's stocks (mtl/you2.py).

Found by studying the plan's own picks (big losers were mostly stocks whose run had gone quiet), so it was
checked against the overfitting tests before it went in: research/validation/README.md."""
import math

VOL_TH = 0.70
SWING_TH = 0.55


def _closes(px, calendar, k, n):
    """Closes for calendar[k - n .. k], carried forward over gaps; None if any is missing or not positive."""
    out, last = [], None
    for j in range(max(0, k - n - 60), k + 1):        # a little run-in to carry a missing first close
        c = px.get(calendar[j])
        last = c if c else last
        if j >= k - n:
            out.append(last)
    if len(out) < n + 1 or any(not c or c <= 0 for c in out):
        return None
    return out


def ratios(prices, volumes, calendar, t, k):
    """(volume ratio, swing ratio) for ticker t at calendar index k, either None when there isn't enough data."""
    vr = sr = None
    if k >= 130:
        v = volumes.get(t) or {}
        a = [v.get(calendar[j]) for j in range(k - 20, k + 1)]
        b = [v.get(calendar[j]) for j in range(k - 125, k - 20)]
        a, b = [x for x in a if x is not None], [x for x in b if x is not None]
        if len(a) >= 15 and len(b) >= 70 and sum(b) > 0:
            vr = (sum(a) / len(a)) / (sum(b) / len(b))
    c = _closes(prices.get(t) or {}, calendar, k, 252) if k >= 252 else None
    if c:
        r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]

        def sd(xs):
            m = sum(xs) / len(xs)
            return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
        normal = sd(r[:189])
        if normal > 0:
            sr = sd(r[-21:]) / normal
    return vr, sr


def fading(prices, volumes, calendar, vol_th=VOL_TH, swing_th=SWING_TH):
    """fading(t, k) -> True when ticker t is fading at calendar index k (both ratios under their thresholds)."""
    cache = {}

    def f(t, k):
        if (t, k) not in cache:
            vr, sr = ratios(prices, volumes, calendar, t, k)
            cache[(t, k)] = vr is not None and sr is not None and vr < vol_th and sr < swing_th
        return cache[(t, k)]
    return f


def buy_ok(prices, volumes, calendar, vol_th=VOL_TH, swing_th=SWING_TH):
    """run_momentum's buy_when: a stock not held is bought only while it isn't fading."""
    f = fading(prices, volumes, calendar, vol_th, swing_th)
    return lambda t, k: not f(t, k)

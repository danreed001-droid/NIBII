"""Dip add: lean into a Boost-list holding the day after it drops hard.

When a stock held in the Boost list closes down DIP_DROP (10%) or more on a day the plan
is fully in the Boost list (not rotated out, no whipsaw half-switch), its weight goes to
DIP_MULT (1.5x) at the next session's close and the other holdings are trimmed to make
room. The overweight lasts until the list next trades (the weekly rebalance, or an exit),
which puts every holding back to equal weight. No dip add is made on a day the list trades
anyway, and a second dip before the rebalance replaces the first.

Why: across 2000-2026, a top-5 holding that fell 10%+ in a day while the plan was in stocks
beat SPY by about 4 points over the next week and 9 over the next four (6.8 points over four
weeks in 2013-2026 alone, 10.3 in 2000-2012), against about 0.5 and 1.6 on an ordinary day:
in a strong trend these drops are mostly shakeouts. Default from Oct 12, 2026: 34.5% a year
before tax from 2000 (22.4% after) vs 33.7% (21.9%), worst drop -40% vs -41%; from 2010 30.3%
vs 29.1%, from 2016 37.9% vs 38.1%, from 2020 57.5% vs 55.8% with a worst drop of -32% vs
-31%. Keeping the 1.5x for a full four weeks did better from 2000 but worse from 2010 and
2020. Abroad (Japan, UK, Germany, India, Hong Kong) it was about neutral. On its own the
rule's gain is not statistically significant, so treat it as small and unproven live.

Pure and network-free.
"""
from bisect import bisect_right

DIP_DROP = 0.10      # a holding's one-day close-to-close fall that triggers the add
DIP_MULT = 1.5       # its weight relative to an equal share while the add lasts


def dip_events(picks, prices, calendar, ok_day, drop=DIP_DROP):
    """[(signal day, trade day, {ticker: that day's change})]: a Boost-list holding (as held at
    the signal day's close) fell `drop` or more that day, ok_day(signal day) is true (the plan is
    fully in the Boost list), and the list does not trade on the next session anyway.
    picks: [[fill date, [tickers]]] from run_momentum; prices: {ticker: {date: close}}."""
    days = [p[0] for p in picks]
    trades = set(days)
    out = []
    for k in range(1, len(calendar) - 1):
        f, d = calendar[k], calendar[k + 1]
        if d in trades or not ok_day(f):
            continue
        i = bisect_right(days, f) - 1
        if i < 0:
            continue
        chg = {}
        for t in picks[i][1]:
            a, b = (prices.get(t) or {}).get(calendar[k - 1]), (prices.get(t) or {}).get(f)
            if a and b and b / a - 1 <= -drop:
                chg[t] = b / a - 1
        if chg:
            out.append((f, d, chg))
    return out


def dip_weights(held, dropped, top_n, mult=DIP_MULT):
    """{ticker: weight} for the add: an equal 1/top_n share each, the dropped ones x mult, scaled
    so the stock total is unchanged (empty slots stay cash)."""
    w = {t: 1.0 / top_n for t in held}
    w2 = {t: v * (mult if t in dropped else 1.0) for t, v in w.items()}
    s = sum(w.values()) / sum(w2.values())
    return {t: v * s for t, v in w2.items()}


def dip_curve(boost_curve, picks, prices, calendar, events, top_n, mult=DIP_MULT, cost=0.0005):
    """The Boost-list curve ([[date, value]]) with the dip adds: from each add's trade-day close
    until the list next trades (or the next add), the day's return changes by the extra weight
    times each stock's return; each move in and out pays `cost` on the weight moved."""
    days = [p[0] for p in picks]
    idx = {d: i for i, d in enumerate(calendar)}
    extra = {}       # date -> added return
    fee = {}         # date -> cost of moving weight at that close
    ev = sorted(events, key=lambda e: e[1])
    for n, (f, d, chg) in enumerate(ev):
        i = bisect_right(days, d) - 1
        if i < 0 or d not in idx:
            continue
        held = picks[i][1]
        w2 = dip_weights(held, chg, top_n, mult)
        delta = {t: w2[t] - 1.0 / top_n for t in held}
        moved = sum(abs(x) for x in delta.values())
        nxt_trade = days[i + 1] if i + 1 < len(days) else None
        nxt_dip = ev[n + 1][1] if n + 1 < len(ev) else None
        end = min(x for x in (nxt_trade, nxt_dip, calendar[-1]) if x)
        fee[d] = fee.get(d, 0.0) + moved * cost
        if end != nxt_dip:
            fee[end] = fee.get(end, 0.0) + moved * cost
        for j in range(idx[d] + 1, idx[end] + 1):
            a_, b_ = calendar[j - 1], calendar[j]
            add = 0.0
            for t, x in delta.items():
                p0, p1 = (prices.get(t) or {}).get(a_), (prices.get(t) or {}).get(b_)
                if p0 and p1:
                    add += x * (p1 / p0 - 1)
            extra[b_] = extra.get(b_, 0.0) + add
    out, v, prev = [], None, None
    for d, val in boost_curve:
        if v is None:
            v = val
        else:
            r = val / prev - 1 if prev else 0.0
            v *= (1 + r + extra.get(d, 0.0)) * (1 - fee.get(d, 0.0))
        out.append([d, v])
        prev = val
    return out

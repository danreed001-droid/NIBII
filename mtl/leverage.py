"""Trend-gated leverage: lever a plan up while the market is in an uptrend,
cut it back while it isn't.

Every week's last session, SPY's close is compared with its 200-session
average. Above it, the plan is held at `hi` x the account (the extra
borrowed at `rate` a year); below it, at `lo` x, with the rest in cash
(T-bills). The new level is applied from the next session, like the plan's
own Monday trades.

Tested on Auto + News boost (Oct 2026, github.com/danreed001-droid/volume:
scripts/backtest_boost_leverage_ideas.py, backtest_gated_robustness.py),
2000-2026, borrowing at 6%:
  plain Boost              +32% a year, worst drop -62%, worst year -43%
  1.25x up / 0.6x down     +34% a year, worst drop -61%, worst year -28%
  1.5x up / 0.6x down      +38% a year, worst drop -67%, worst year -29%
The gain held for 8 of 9 different trend signals (SPY 100-250 day, QQQ
200-day, SPY 10-month, SPY vs a year ago, VIX < 25), and 2000-2025 without
2026's run: +31% vs +27% a year (1.5x). Constant leverage, by contrast,
loses it all in bear markets: 2x without the gate fell 91% (2000-02, 2008).

Pure and network-free.
"""
from mtl.momentum import last_sessions_of_weeks

SMA_DAYS = 200
HI, LO = 1.25, 0.6
RATE = 0.06


def trend_up(prices, calendar, n=SMA_DAYS):
    """{date: True while prices[date] > its average over the last n sessions}.
    Sessions without a price carry the last answer; fewer than n prices so
    far counts as up (no evidence of a downtrend yet)."""
    out, window, total, state = {}, [], 0.0, True
    for d in calendar:
        p = prices.get(d)
        if p is not None:
            window.append(p)
            total += p
            if len(window) > n:
                total -= window.pop(0)
            state = len(window) < n or p > total / n
        out[d] = state
    return out


def gated_curve(plan, cash, calendar, up, hi=HI, lo=LO, rate=RATE):
    """[[date, value]] from 1.0: `plan` ([[date, value]]) held at hi x while
    up[friday] else lo x, decided at each week's last session and applied
    from the next session. Above 1x the extra is borrowed at `rate` a year
    (charged per session, 252 a year); below 1x the rest earns `cash`
    ({date: T-bill value}). An account that hits zero stays at zero."""
    weeks = set(last_sessions_of_weeks(calendar))
    out, prev, lev, nav = [], None, None, 1.0
    for d, v in plan:
        if prev is None:
            lev = hi if up.get(d, True) else lo
        else:
            pd_, pv = prev
            r = v / pv - 1
            c = cash[d] / cash[pd_] - 1 if cash.get(d) and cash.get(pd_) else 0.0
            nav *= 1 + lev * r - max(0.0, lev - 1) * rate / 252 + max(0.0, 1 - lev) * c
            nav = max(nav, 0.0)
        out.append([d, nav])
        if d in weeks:
            lev = hi if up.get(d, True) else lo
        prev = (d, v)
    return out

"""Momentum ("buy the strongest stocks") portfolio backtest.

Every rebalance day (the last session of each week), rank the universe by
a trailing-return score measured only with closes up to that day, and hold
the top N in equal weight until the next rebalance:

- score: return from `look` sessions ago to `skip` sessions ago - the
  classic "6-1" is look=126, skip=21 (six months, ignoring the latest
  month, which tends to mean-revert short term).
- a stock must beat SPY's score over the same window to qualify - if fewer
  than N do, the leftover slots sit in cash.
- hysteresis: a holding is kept while it still ranks within `keep_rank`
  (default 2N), so names hovering around the cut-off don't churn weekly.
- eligible(ticker, date) -> bool: optional extra filter (e.g. the weekly
  and daily charts must both be in an uptrend).
- risk_on(date) -> bool: optional market filter; False = all cash.
- cost: charged on every dollar bought or sold at each rebalance.

Pure and network-free; positions are marked to each session's close and a
holding without a close that day carries its last price.
"""


def last_sessions_of_weeks(calendar):
    """The last date of each ISO week in a sorted list of 'YYYY-MM-DD'."""
    from datetime import date
    out = []
    for k, d in enumerate(calendar):
        nxt = calendar[k + 1] if k + 1 < len(calendar) else None
        if nxt is None or date.fromisoformat(nxt).isocalendar()[:2] != date.fromisoformat(d).isocalendar()[:2]:
            out.append(d)
    return out


def score_at(prices, calendar, k, look, skip):
    """Trailing return from calendar[k-look] to calendar[k-skip], or None."""
    if k - look < 0:
        return None
    a, b = prices.get(calendar[k - look]), prices.get(calendar[k - skip])
    if not a or not b:
        return None
    return b / a - 1.0


def run_momentum(prices, calendar, start, benchmark='SPY', look=126, skip=21, top_n=10,
                 keep_rank=None, eligible=None, risk_on=None, cost=0.0005, start_value=100.0):
    """prices: {ticker: {date: close}} (must include `benchmark`);
    calendar: sorted session dates. Returns dict(curve=[[date, value,
    holdings]], picks=[[date, [tickers]]], turnover=annualized fraction)."""
    keep_rank = keep_rank or 2 * top_n
    rebal = set(last_sessions_of_weeks(calendar))
    tickers = [t for t in prices if t != benchmark]
    value, cash = start_value, start_value
    shares = {}          # ticker -> shares held
    last_px = {}         # ticker -> last seen close
    curve, picks, traded = [], [], 0.0
    started = False
    for k, d in enumerate(calendar):
        for t in shares:
            px = prices[t].get(d)
            if px:
                last_px[t] = px
        value = cash + sum(n * last_px[t] for t, n in shares.items())
        if d >= start:
            started = True
        if not started:
            continue
        if d in rebal:
            target = []
            if risk_on is None or risk_on(d):
                bench = score_at(prices[benchmark], calendar, k, look, skip)
                scored = []
                for t in tickers:
                    s = score_at(prices[t], calendar, k, look, skip)
                    if s is None or bench is None or s <= bench or not prices[t].get(d):
                        continue
                    if eligible and not eligible(t, d):
                        continue
                    scored.append((s, t))
                scored.sort(reverse=True)
                rank = {t: i for i, (_, t) in enumerate(scored)}
                keep = [t for t in shares if rank.get(t, 10 ** 9) < keep_rank]
                keep.sort(key=lambda t: rank[t])
                target = keep[:top_n]
                for _, t in scored:
                    if len(target) >= top_n:
                        break
                    if t not in target:
                        target.append(t)
            # rebalance to equal weight across the N slots (unfilled = cash)
            for t in target:
                last_px[t] = prices[t][d]
            slot = value / top_n
            new_shares = {t: slot / last_px[t] for t in target}
            moved = sum(abs(new_shares.get(t, 0.0) - shares.get(t, 0.0)) * last_px[t]
                        for t in set(shares) | set(new_shares))
            fee = moved * cost
            traded += moved
            value -= fee
            slot = value / top_n
            shares = {t: slot / last_px[t] for t in target}
            cash = value - sum(n * last_px[t] for t, n in shares.items())
            picks.append([d, list(target)])
        curve.append([d, value, len(shares)])
    years = max(len(curve) / 252, 1e-9)
    avg_value = sum(p[1] for p in curve) / len(curve) if curve else 1.0
    return dict(curve=curve, picks=picks, turnover=traded / avg_value / years / 2)

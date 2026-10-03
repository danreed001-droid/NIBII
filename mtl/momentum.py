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


def score_table(prices, calendar, k, look=126, skip=21, windows=None, blend='rank',
                eligible=None, benchmark='SPY'):
    """[(ticker, score, beats_benchmark)] best first for every eligible stock
    with a score on calendar[k].

    One window (windows=None): score = return from `look` to `skip` sessions
    ago; beats_benchmark = score > the benchmark's score.
    Blended (windows=[(look, skip), ...]): each window's return is computed,
    and the score is either their average return (blend='mean') or the average
    of the stock's percentile rank in each window (blend='rank', 1 = best, so
    every window counts equally). beats_benchmark = the stock's average excess
    return over the benchmark across the windows is positive."""
    d = calendar[k]
    cands = [t for t in prices if t != benchmark and prices[t].get(d) and (eligible is None or eligible(t, d))]
    if not windows:
        b = score_at(prices[benchmark], calendar, k, look, skip) if benchmark in prices else None
        rows = []
        for t in cands:
            sc = score_at(prices[t], calendar, k, look, skip)
            if sc is not None:
                rows.append((t, sc, b is not None and sc > b))
    else:
        bench = [score_at(prices[benchmark], calendar, k, lk, sk) if benchmark in prices else None
                 for lk, sk in windows]
        rets = {}
        for t in cands:
            r = [score_at(prices[t], calendar, k, lk, sk) for lk, sk in windows]
            if all(x is not None for x in r):
                rets[t] = r
        if blend == 'mean':
            score = {t: sum(r) / len(r) for t, r in rets.items()}
        else:
            score = {t: 0.0 for t in rets}
            n = len(rets)
            for w in range(len(windows)):
                order = sorted(rets, key=lambda t: rets[t][w])
                for i, t in enumerate(order):
                    score[t] += (i + 1) / n / len(windows) if n else 0.0
        ok = all(x is not None for x in bench)
        rows = [(t, score[t], ok and sum(a - b for a, b in zip(rets[t], bench)) > 0) for t in rets]
    rows.sort(key=lambda x: -x[1])
    return rows


def run_momentum(prices, calendar, start, benchmark='SPY', look=126, skip=21, top_n=10,
                 keep_rank=None, eligible=None, risk_on=None, cost=0.0005, start_value=100.0,
                 rebalance_on_start=False, risk_daily=False, windows=None, blend='rank'):
    """prices: {ticker: {date: close}} (must include `benchmark`);
    calendar: sorted session dates. Returns dict(curve=[[date, value,
    holdings]], picks=[[date, [tickers]]], turnover=annualized fraction)."""
    keep_rank = keep_rank or 2 * top_n
    rebal = set(last_sessions_of_weeks(calendar))
    if rebalance_on_start:   # buy on the first session >= start, not the next week-end
        rebal.add(next(d for d in calendar if d >= start))
    tickers = [t for t in prices if t != benchmark]
    value, cash = start_value, start_value
    shares = {}          # ticker -> shares held
    last_px = {}         # ticker -> last seen close
    curve, picks, traded = [], [], 0.0
    started = False
    prev_risk = None
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
        flip = False
        if risk_on is not None and risk_daily:
            cur_risk = bool(risk_on(d))
            flip = prev_risk is not None and cur_risk != prev_risk
            prev_risk = cur_risk
        if d in rebal or flip:
            target = []
            if risk_on is None or risk_on(d):
                scored = [(sc, t) for t, sc, beats in
                          score_table(prices, calendar, k, look, skip, windows, blend, eligible, benchmark)
                          if beats]
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


def run_rank_climbers(prices, calendar, start, benchmark='SPY', look=126, skip=21, top=100,
                      slots=10, mode='decliners', max_new=None, swap=5, eligible=None,
                      cost=0.0005, start_value=100.0, change_weeks=1, exit_rank=50):
    """Buy the stocks CLIMBING the momentum ranking, not the ones already on top.

    Every week-end session: rank every eligible stock by its trailing score
    (look/skip as in run_momentum; rank 0 = strongest) and compare with
    last week's rank (improvement = last week's rank - this week's).
    Candidates are this week's top `top` stocks. Then, holding `slots`
    stocks in equal weight:

    mode='decliners': sell every holding whose rank got worse or that left
                      the top `top`; refill with the biggest climbers
                      (at most `max_new` buys a week if set - unfilled
                      slots stay in cash).
    mode='swap':      sell anything that left the top `top`, then swap the
                      `swap` holdings with the worst rank change for the
                      `swap` biggest climbers.
    mode='hold':      the gentle version - keep a holding while it ranks
                      within `exit_rank`, whatever its weekly wobble, and
                      fill open slots with the biggest climbers.
    change_weeks: measure the climb against the rank this many weeks ago
                  (1 = last week; 4 = a steadier month-long climb).
    Returns dict(curve, picks, turnover) like run_momentum."""
    rebal = set(last_sessions_of_weeks(calendar))
    tickers = [t for t in prices if t != benchmark]
    cash, shares, last_px = start_value, {}, {}
    curve, picks, traded = [], [], 0.0
    history, started = [], False
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
            scored = []
            for t in tickers:
                s = score_at(prices[t], calendar, k, look, skip)
                if s is None or not prices[t].get(d) or (eligible and not eligible(t, d)):
                    continue
                scored.append((s, t))
            scored.sort(reverse=True)
            rank = {t: i for i, (_, t) in enumerate(scored)}
            prev_rank = history[-change_weeks] if len(history) >= change_weeks else None
            if prev_rank is not None:
                def change(t):
                    return prev_rank[t] - rank[t] if t in prev_rank and t in rank else None
                climbers = [t for t in rank if rank[t] < top and (change(t) or 0) > 0]
                climbers.sort(key=lambda t: (-change(t), rank[t]))
                held = [t for t in shares if rank.get(t, 10 ** 9) < top]
                if mode == 'hold':
                    keep = [t for t in shares if rank.get(t, 10 ** 9) < exit_rank]
                    new = [t for t in climbers if t not in keep][:max(0, slots - len(keep))]
                elif mode == 'decliners':
                    keep = [t for t in held if (change(t) or 0) >= 0]
                    new = [t for t in climbers if t not in keep][:max(0, slots - len(keep))]
                    if max_new is not None:
                        new = new[:max_new]
                else:
                    fresh = [t for t in climbers if t not in held]
                    if len(held) < slots:          # open slots (e.g. the first week): fill them
                        keep, new = held, fresh[:slots - len(held)]
                    else:                          # full: swap the worst `swap` for the best climbers
                        held.sort(key=lambda t: change(t) if change(t) is not None else -10 ** 9)
                        new = fresh[:swap]
                        keep = held[len(new):]
                target = keep + new
                for t in target:
                    last_px[t] = prices[t][d]
                slot = value / slots
                new_shares = {t: slot / last_px[t] for t in target}
                moved = sum(abs(new_shares.get(t, 0.0) - shares.get(t, 0.0)) * last_px[t]
                            for t in set(shares) | set(new_shares))
                traded += moved
                value -= moved * cost
                slot = value / slots
                shares = {t: slot / last_px[t] for t in target}
                cash = value - sum(n * last_px[t] for t, n in shares.items())
                picks.append([d, list(target)])
            history.append(rank)
        curve.append([d, value, len(shares)])
    years = max(len(curve) / 252, 1e-9)
    avg_value = sum(p[1] for p in curve) / len(curve) if curve else 1.0
    return dict(curve=curve, picks=picks, turnover=traded / avg_value / years / 2)


def ranking(prices, calendar, k, look=126, skip=21, eligible=None, benchmark='SPY', windows=None, blend='rank'):
    """[(ticker, score)] best first, for every eligible stock with a score at
    calendar[k] (the same ranking run_momentum uses on that day)."""
    return [(t, sc) for t, sc, _ in score_table(prices, calendar, k, look, skip, windows, blend, eligible, benchmark)]


def trades_from_picks(picks):
    """[(date, 'buy'|'sell', ticker)] from consecutive rebalance holdings."""
    out, prev = [], []
    for d, held in picks:
        for t in prev:
            if t not in held:
                out.append((d, 'sell', t))
        for t in held:
            if t not in prev:
                out.append((d, 'buy', t))
        prev = held
    return out

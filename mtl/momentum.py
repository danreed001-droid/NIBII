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
    if isinstance(blend, tuple) and blend[0] == 'regime':   # ('regime', fn): fn(k) True -> plain 6-1 score
        if blend[1](k):
            windows = None
        blend = 'rank'
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
        def ratio(r, down):
            m = sum(r) / len(r)
            if down:
                dd = (sum(min(x, 0.0) ** 2 for x in r) / len(r)) ** 0.5
            else:
                dd = (sum((x - m) ** 2 for x in r) / max(len(r) - 1, 1)) ** 0.5
            return m / dd if dd > 1e-12 else (1e6 if m > 0 else 0.0)
        if blend == 'mean':
            score = {t: sum(r) / len(r) for t, r in rets.items()}
        elif blend in ('sortino', 'sharpe'):
            score = {t: ratio(r, blend == 'sortino') for t, r in rets.items()}
        elif blend == 'rank_ret':     # consensus: average of the weekly rank-sum and the 6-1 month return places
            n = len(rets)
            W = len(windows)
            rs = {t: 0.0 for t in rets}
            for w in range(W):
                for i, t in enumerate(sorted(rets, key=lambda t: rets[t][w])):
                    rs[t] += i + 1
            r61 = {t: score_at(prices[t], calendar, k, look, skip) or -1e9 for t in rets}
            p1 = {t: (i + 1) / n for i, t in enumerate(sorted(rets, key=lambda t: rs[t]))}
            p2 = {t: (i + 1) / n for i, t in enumerate(sorted(rets, key=lambda t: r61[t]))}
            score = {t: (p1[t] + p2[t]) / 2 for t in rets}
        elif blend in ('rank_resid', 'rank_52'):
            n = len(rets)
            W = len(windows)
            if blend == 'rank_resid' and all(x is not None for x in bench):
                # residual momentum: each week's return less beta x SPY's week, beta fit over the windows
                mb = sum(bench) / W
                vb = sum((x - mb) ** 2 for x in bench) or 1e-12
                use = {}
                for t, r in rets.items():
                    mr = sum(r) / W
                    beta = sum((x - mr) * (y - mb) for x, y in zip(r, bench)) / vb
                    use[t] = [x - beta * y for x, y in zip(r, bench)]
            else:
                use = rets
            rs = {t: 0.0 for t in use}
            for w in range(W):
                for i, t in enumerate(sorted(use, key=lambda t: use[t][w])):
                    rs[t] += i + 1
            if blend == 'rank_52':      # blend with closeness to the 52-week high (closes)
                near = {}
                for t in rets:
                    px = prices[t]
                    hs = [px.get(calendar[j]) for j in range(max(0, k - 251), k + 1)]
                    hs = [h for h in hs if h]
                    near[t] = px[d] / max(hs) if hs else 0.0
                p1 = {t: (i + 1) / n for i, t in enumerate(sorted(rets, key=lambda t: rs[t]))}
                # average rank for ties (many stocks sit exactly at their 52-week high)
                order = sorted(rets, key=lambda t: near[t])
                p2, i = {}, 0
                while i < n:
                    j = i
                    while j + 1 < n and near[order[j + 1]] == near[order[i]]:
                        j += 1
                    for q in range(i, j + 1):
                        p2[order[q]] = ((i + j) / 2 + 1) / n
                    i = j + 1
                score = {t: (p1[t] + p2[t]) / 2 for t in rets}
            else:
                score = {t: rs[t] / n / W for t in rets}
        elif blend == 'rank_sortino':   # average of the weekly rank-sum percentile and the Sortino percentile
            W = len(windows)
            rs = {t: 0.0 for t in rets}
            for w in range(W):
                for i, t in enumerate(sorted(rets, key=lambda t: rets[t][w])):
                    rs[t] += i + 1
            so = {t: ratio(r, True) for t, r in rets.items()}
            n = len(rets)
            p1 = {t: (i + 1) / n for i, t in enumerate(sorted(rets, key=lambda t: rs[t]))}
            p2 = {t: (i + 1) / n for i, t in enumerate(sorted(rets, key=lambda t: so[t]))}
            score = {t: (p1[t] + p2[t]) / 2 for t in rets}
        else:
            # blend=('rank', bonus, top_k, recent): a week where the stock ranks in the top
            # `top_k` adds `bonus` (in units of one week's best rank); `recent` > 0 weights
            # the newest window up to (1 + recent) times the oldest, linearly
            bonus, top_k, recent = (blend[1], blend[2], blend[3]) if isinstance(blend, tuple) else (0.0, 0, 0.0)
            score = {t: 0.0 for t in rets}
            n = len(rets)
            W = len(windows)
            shape = blend[4] if isinstance(blend, tuple) and len(blend) > 4 else 'lin'
            xs = [(W - 1 - j) / max(W - 1, 1) for j in range(W)]   # 0 = oldest week, 1 = newest
            if shape == 'exp':        # geometric: newest = (1 + recent) x oldest
                wts = [(1 + recent) ** x for x in xs]
            elif shape.startswith('pow'):   # flat for old weeks, rising steeply into the present
                pw = float(shape[3:])
                wts = [1 + recent * x ** pw for x in xs]
            else:
                wts = [1 + recent * x for x in xs]
            tot = sum(wts)
            for w in range(W):
                order = sorted(rets, key=lambda t: rets[t][w])
                for i, t in enumerate(order):
                    score[t] += wts[w] * ((i + 1) / n + (bonus if n - i <= top_k else 0.0)) / tot if n else 0.0
        ok = all(x is not None for x in bench)
        rows = [(t, score[t], ok and sum(a - b for a, b in zip(rets[t], bench)) > 0) for t in rets]
    rows.sort(key=lambda x: -x[1])
    return rows


def run_momentum(prices, calendar, start, benchmark='SPY', look=126, skip=21, top_n=10,
                 keep_rank=None, eligible=None, risk_on=None, cost=0.0005, start_value=100.0,
                 rebalance_on_start=False, risk_daily=False, windows=None, blend='rank',
                 trail_stop=None, cooldown=20, group_of=None, max_per_group=None,
                 sector_of=None, top_sectors=None, sector_grace=1, sector_min=3,
                 rsi_exit=None, rsi_period=14, buy_ok=None, weighting='equal', vol_target=None,
                 vol_window=63, max_corr=None, corr_window=63, risk_adj=False, exec_next=None,
                 exit_when=None, exit_daily=True, buy_when=None, lookback_at=None,
                 prefer=None, prefer_rank=20, prefer_mode='fill', prefer_pool='qualified',
                 rebal_dates=None, rank_key=None):
    """prices: {ticker: {date: close}} (must include `benchmark`);
    calendar: sorted session dates. Returns dict(curve=[[date, value,
    holdings]], picks=[[date, [tickers]]], turnover=annualized fraction,
    stops=number of trailing-stop exits).

    trail_stop: e.g. 0.20 - checked every session: a holding that closes 20%
      below its highest close since it was bought is sold at that close and
      replaced by the best-ranked qualifying stock not held; the stopped
      stock can't be bought again for `cooldown` sessions.
    group_of / max_per_group: {ticker: industry} and a cap - at most that many
      holdings from one industry (keepers and new buys alike).
    sector_of / top_sectors: {ticker: sector}; each rebalance ranks sectors by
      the median score of their stocks (sectors with fewer than `sector_min`
      scored stocks are skipped) and only buys stocks from the top
      `top_sectors`. A holding whose sector is out of the top is sold once it
      has been out for more than `sector_grace` consecutive rebalances
      (1 = it gets one week's grace).
    rsi_exit: e.g. 40 - checked every session: a holding whose daily RSI
      (Wilder, `rsi_period`) closes below this level is sold at that close and
      replaced by the best-ranked qualifying stock not held; it is barred for
      `cooldown` sessions, and no stock is bought while its RSI is below the
      level. Counted in `stops`.
    buy_ok: optional callable(date) -> bool; while False no new stock is
      bought - holdings that still qualify are kept, sold ones leave their
      slot in cash.
    weighting: 'equal' (each holding 1/top_n) or 'inv_vol' (the same total, split
      in proportion to 1 / each stock's `vol_window`-day volatility).
    vol_target: e.g. 0.30 - at each rebalance, scale every position down so the
      basket's volatility over the last `vol_window` sessions would have been
      at most 30% a year (never above 100% invested); the rest sits in cash.
    max_corr: e.g. 0.7 - skip a new buy whose daily returns over the last
      `corr_window` sessions correlate above this with a stock already chosen.
    risk_adj: rank buy candidates by score / volatility instead of score.
    exec_next: None = trade at the deciding session's close. 'close' = decide
      at that close but trade at the next session's close; or a
      {ticker: {date: price}} map (e.g. opens) = trade at the next session's
      price from that map (falling back to the last close). Picks are dated
      by the trading session.
    exit_when: optional callable(ticker, k) -> bool (e.g. "the daily chart is in a
      lower-low downtrend at calendar[k]"). A holding for which it is True is
      sold (checked every session with exit_daily=True, else only on
      rebalance days) and barred for `cooldown` sessions; no stock is bought
      while it is True for that stock - the next-best ranked one is taken.
      Counted in `stops`.
    buy_when: optional callable(ticker, k) -> bool; a stock not held is only
      bought when it is True (e.g. "its daily chart is in an uptrend") - the
      next-best ranked stock that passes is taken instead.
    lookback_at: optional callable(k) -> (look, skip) to change the strength
      window by regime (e.g. 3 months while the market's 12-month return is
      negative); defaults to (look, skip).
    prefer: optional callable(ticker, k) -> bool (e.g. "gapped up 10%+ on news
      this week"). On a rebalance, qualifying stocks ranked within
      `prefer_rank` for which it is True jump the queue for open slots.
      prefer_mode='force' also lets them replace the lowest-ranked holding
      when no slot is open (at most one swap per preferred stock).
      prefer_rank=None: any rank. prefer_pool='all': flagged stocks qualify even
      when they don't beat the benchmark (ranked by score among all stocks).
    rebal_dates: optional set of decision dates replacing the default week-ends
      (e.g. month-ends). The result's `weights` lists [trade date, {ticker: weight}]
      for every trade (weights below 1 in total = the rest sits in cash).
    rank_key: optional callable(ticker, k, score) -> sort key (smaller = better) that
      replaces the plain best-score-first order of qualifying stocks, for both the
      buy order and the keep-while-ranked test."""
    keep_rank = keep_rank or 2 * top_n
    rebal = set(rebal_dates) if rebal_dates is not None else set(last_sessions_of_weeks(calendar))
    wlog = []
    if rebalance_on_start:   # buy on the first session >= start, not the next week-end
        rebal.add(next(d for d in calendar if d >= start))
    tickers = [t for t in prices if t != benchmark]
    value, cash = start_value, start_value
    shares = {}          # ticker -> shares held
    last_px = {}         # ticker -> last seen close
    curve, picks, traded = [], [], 0.0
    started = False
    prev_risk = None
    peak, banned_until, stops = {}, {}, 0
    sector_out = {}
    rsi_cache = {}
    ret_cache = {}

    def rets(t, k, n):
        """Daily returns of t for the n sessions ending at calendar[k] (gaps carry the price)."""
        if t not in ret_cache:
            out, last, prev = [0.0] * len(calendar), None, None
            for i, d in enumerate(calendar):
                px = prices[t].get(d) or last
                out[i] = px / prev - 1 if px and prev else 0.0
                prev = last = px
            ret_cache[t] = out
        return ret_cache[t][max(1, k - n + 1):k + 1]

    def vol(t, k):
        r = rets(t, k, vol_window)
        if len(r) < 2:
            return 1.0
        m = sum(r) / len(r)
        return max(1e-4, (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5 * 252 ** 0.5)

    def corr(a, b):
        n = len(a)
        if n < 3:
            return 0.0
        ma, mb = sum(a) / n, sum(b) / n
        sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        sa = sum((x - ma) ** 2 for x in a) ** 0.5
        sb = sum((y - mb) ** 2 for y in b) ** 0.5
        return sab / (sa * sb) if sa and sb else 0.0

    rank_now = {}

    def weights(target, k):
        if not target:
            return {}
        if weighting == 'inv_vol':
            inv = {t: 1 / vol(t, k) for t in target}
            tot = sum(inv.values())
            w = {t: inv[t] / tot * len(target) / top_n for t in target}
        elif isinstance(weighting, str) and weighting.startswith('drift'):
            # let winners run: each new buy gets a normal 1/top_n slot; the kept holdings share the
            # rest in proportion to their current values (no trimming of winners), each capped
            cap = float(weighting.split(':')[1]) if ':' in weighting else 1.0
            cur = {t: shares[t] * last_px[t] for t in target if t in shares and last_px.get(t)}
            new = [t for t in target if t not in cur]
            w = {t: 1.0 / top_n for t in new}
            room = len(target) / top_n - len(new) / top_n
            tot_c = sum(cur.values())
            for t, v in cur.items():
                w[t] = room * v / tot_c if tot_c > 0 else room / len(cur)
            for _ in range(5):          # cap, spreading the excess over the uncapped ones
                over = sum(max(0.0, x - cap) for x in w.values())
                if over <= 1e-12:
                    break
                under = [t for t, x in w.items() if x < cap]
                w = {t: min(cap, x) for t, x in w.items()}
                if not under:
                    break
                tot_u = sum(w[t] for t in under)
                for t in under:
                    w[t] += over * w[t] / tot_u if tot_u else over / len(under)
        elif weighting == 'top3x':
            best = min(target, key=lambda t: rank_now.get(t, 10 ** 9))
            w = {t: (3.0 if t == best else 1.0) / (top_n + 2) for t in target}
        elif weighting == 'rankw':   # top_n, top_n-1, ... 1 by rank
            order = sorted(target, key=lambda t: rank_now.get(t, 10 ** 9))
            tot = top_n * (top_n + 1) / 2
            w = {t: (top_n - i) / tot for i, t in enumerate(order)}
        elif weighting == 'top2x':   # the best-ranked holding gets twice the others' weight
            best = min(target, key=lambda t: rank_now.get(t, 10 ** 9))
            w = {t: (2.0 if t == best else 1.0) / (top_n + 1) for t in target}
        else:
            w = {t: 1 / top_n for t in target}
        if vol_target:
            basket = [sum(w[t] * r for t, r in zip(target, day)) for day in
                      zip(*[rets(t, k, vol_window) for t in target])]
            if len(basket) > 2:
                m = sum(basket) / len(basket)
                pv = (sum((x - m) ** 2 for x in basket) / (len(basket) - 1)) ** 0.5 * 252 ** 0.5
                scale = min(1.0, vol_target / pv) if pv > 0 else 1.0
                w = {t: x * scale for t, x in w.items()}
        return w

    def rsi_at(t, k):
        if t not in rsi_cache:
            from mtl.backtest import rsi_series
            idx, closes = [], []
            for i, d in enumerate(calendar):
                px = prices[t].get(d)
                if px:
                    idx.append(i)
                    closes.append(px)
            vals = rsi_series(closes, rsi_period)
            out, j = [None] * len(calendar), 0
            for i in range(len(calendar)):   # carry the last value over missing sessions
                while j < len(idx) and idx[j] <= i:
                    j += 1
                out[i] = vals[j - 1] if j else None
            rsi_cache[t] = out
        return rsi_cache[t][k]

    def rsi_weak(t, k):
        r = rsi_at(t, k)
        return r is not None and r < rsi_exit

    def top_sector_set(rows):
        groups = {}
        for t, sc, _ in rows:
            sec = sector_of.get(t)
            if sec:
                groups.setdefault(sec, []).append(sc)
        med = {}
        for sec, v in groups.items():
            if len(v) >= sector_min:
                v = sorted(v)
                m = len(v) // 2
                med[sec] = v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2
        return set(sorted(med, key=lambda x: -med[x])[:top_sectors])

    def choose(k, d, keep_from, exclude=()):
        """Target holdings on day k: keepers (ranked within keep_rank, or every
        name in keep_from when keep_from is a forced keep-list) then the best
        ranked qualifying stocks, honoring the industry cap and cooldowns."""
        lk, sk = lookback_at(k) if lookback_at else (look, skip)
        rows = score_table(prices, calendar, k, lk, sk, windows, blend, eligible, benchmark)
        if rank_key is not None:
            rows = sorted(rows, key=lambda r: rank_key(r[0], k, r[1]))
        rank_now.clear()
        rank_now.update({r[0]: i for i, r in enumerate(rows)})
        scored = [(sc, t) for t, sc, beats in rows
                  if beats and banned_until.get(t, -1) < k and t not in exclude
                  and not (rsi_exit and t not in shares and rsi_weak(t, k))]
        allowed = None
        if sector_of and top_sectors:
            allowed = top_sector_set(rows)
            scored = [(sc, t) for sc, t in scored if sector_of.get(t) in allowed]
        rank = {t: i for i, (_, t) in enumerate(scored)}
        if isinstance(keep_from, list):
            keep = list(keep_from)
        else:
            full_rank = {t: i for i, (t, sc, beats) in enumerate([r for r in rows if r[2]])}
            keep = []
            for t in shares:
                if banned_until.get(t, -1) >= k:
                    continue          # stopped out today: sell even on a rebalance day
                if allowed is not None and sector_of.get(t) not in allowed:
                    sector_out[t] = sector_out.get(t, 0) + 1
                    if sector_out[t] > sector_grace:
                        continue      # its sector has been out of the top too long: sell
                else:
                    sector_out.pop(t, None)
                if full_rank.get(t, 10 ** 9) < keep_rank:
                    keep.append(t)
            keep.sort(key=lambda t: full_rank[t])
        target, count = [], {}

        def fits(t):
            return not (group_of and max_per_group) or count.get(group_of.get(t, t), 0) < max_per_group

        def add(t):
            target.append(t)
            g = group_of.get(t, t) if group_of else t
            count[g] = count.get(g, 0) + 1

        for t in keep:
            if len(target) < top_n and fits(t):
                add(t)
        if buy_ok is not None and not buy_ok(d):
            return [t for t in target if t in shares]
        if risk_adj:
            scored = sorted(scored, key=lambda x: -x[0] / vol(x[1], k))
        if prefer is not None and not isinstance(keep_from, list):
            if prefer_pool == 'all':
                pool = [(sc, t) for t, sc, _ in rows if banned_until.get(t, -1) < k and t not in exclude]
            else:
                pool = scored
            pool = pool if prefer_rank is None else pool[:prefer_rank]
            pref = [x for x in pool if x[1] not in target and prefer(x[1], k)]
            if prefer_mode == 'force':
                for _, t in pref:
                    if len(target) >= top_n and fits(t):
                        held = [u for u in target if u in rank or u in shares]
                        worst = max(held, key=lambda u: rank.get(u, 10 ** 9)) if held else None
                        if worst is not None:
                            target.remove(worst)
                            g = group_of.get(worst, worst) if group_of else worst
                            count[g] -= 1
            scored = pref + [x for x in scored if x not in pref]
        for _, t in scored:
            if len(target) >= top_n:
                break
            if t not in target and fits(t):
                if exit_when and t not in shares and exit_when(t, k):
                    continue          # its chart is breaking down: take the next one
                if buy_when and t not in shares and not buy_when(t, k):
                    continue
                if max_corr is not None and any(corr(rets(t, k, corr_window), rets(u, k, corr_window)) > max_corr
                                                for u in target):
                    continue
                add(t)
        return target

    pending = None

    def trade(target, w, d, px_of):
        nonlocal shares, cash, value, traded
        fill = {t: px_of(t) for t in set(shares) | set(target)}
        if any(not fill[t] for t in target):   # no price to trade at (e.g. delisted that day): that slot stays cash
            target = [t for t in target if fill[t]]
            w = {t: x for t, x in w.items() if t in target}
        value = cash + sum(n * fill[t] for t, n in shares.items())
        new_shares = {t: value * w[t] / fill[t] for t in target}
        moved = sum(abs(new_shares.get(t, 0.0) - shares.get(t, 0.0)) * fill[t]
                    for t in set(shares) | set(new_shares))
        traded += moved
        value -= moved * cost
        for t in target:
            if t not in shares:
                peak[t] = fill[t]
        for t in list(peak):
            if t not in target:
                peak.pop(t)
        for t in list(sector_out):
            if t not in target:
                sector_out.pop(t)
        shares = {t: value * w[t] / fill[t] for t in target}
        last_px.update({t: fill[t] for t in target})
        cash = value - sum(n * fill[t] for t, n in shares.items())
        picks.append([d, list(target)])
        wlog.append([d, dict(w)])

    for k, d in enumerate(calendar):
        if pending is not None:   # yesterday's decision fills today
            target, w = pending
            pending = None
            if exec_next == 'close':
                trade(target, w, d, lambda t: prices[t].get(d) or last_px.get(t))
            else:
                trade(target, w, d, lambda t: exec_next.get(t, {}).get(d) or prices[t].get(d) or last_px.get(t))
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
        stopped = []
        if trail_stop and shares:
            for t in shares:
                peak[t] = max(peak.get(t, last_px[t]), last_px[t])
                if last_px[t] <= peak[t] * (1 - trail_stop):
                    stopped.append(t)
        if rsi_exit and shares:
            stopped += [t for t in shares if t not in stopped and rsi_weak(t, k)]
        if exit_when and shares and (exit_daily or d in rebal):
            stopped += [t for t in shares if t not in stopped and exit_when(t, k)]
        for t in stopped:
            banned_until[t] = k + cooldown
            stops += 1
        if d in rebal or flip or stopped:
            target = []
            if risk_on is None or risk_on(d):
                if d in rebal or flip:
                    target = choose(k, d, None)
                else:   # mid-week stop: keep the others, replace only the stopped names
                    target = choose(k, d, [t for t in shares if t not in stopped])
            # rebalance to the target weights (equal by default; unfilled slots = cash)
            w = weights(target, k)
            if exec_next is None:
                trade(target, w, d, lambda t: prices[t].get(d) or last_px.get(t))
            else:
                pending = (target, w)
        curve.append([d, value, len(shares)])
    years = max(len(curve) / 252, 1e-9)
    avg_value = sum(p[1] for p in curve) / len(curve) if curve else 1.0
    return dict(curve=curve, picks=picks, turnover=traded / avg_value / years / 2, stops=stops, weights=wlog)


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

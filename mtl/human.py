"""Scores the viewer's own weekly calls ("Mine", the human model) on real prices.

A call is keyed by its signal Friday and carries forward until the next one:
  m       'auto' | 'boost' | 'boost100' | 'steps' | 'cash' | 'custom' ('del' = removed);
          'boost' follows the News-boost list (its own five stocks) with its Auto mix,
          'boost100' the same list always 100% in the stocks, 'cushion' the same list
          with 25% in the sleeve while SPY's 6-month return is negative
  s, v, c custom stock / sleeve / cash percentages
  swaps   [[model_pick, replacement], ...]  replacement must rank in the top 10
  drops   [model_pick, ...]                 that slot sits in cash
Each week trades at the session after its signal Friday (Monday's close), like
the live page: the stock money is split into the model's five slots; a dropped
slot holds cash, a swapped slot holds the replacement - as long as the model
still holds the stock it replaced and the replacement still ranks in the top
10 at that Friday; otherwise the slot goes back to the model's pick.

Pure and network-free.
"""
SWAP_RANK = 10
LIVE = ('auto', 'boost', 'boost100', 'cushion', 'steps', 'cash', 'custom')


def live_calls(calls):
    """Only real calls (no removals), keys sorted."""
    return {k: calls[k] for k in sorted(calls or {}) if isinstance(calls[k], dict) and calls[k].get('m') in LIVE}


def signature(calls):
    """What the scoring depends on, to tell the page which calls it scored."""
    return [[k, c['m'], c.get('s'), c.get('v'), sorted([list(x) for x in c.get('swaps') or []]), sorted(c.get('drops') or [])]
            for k, c in live_calls(calls).items()]


def call_for(calls, friday):
    keys = [k for k in calls if k <= friday]
    return calls[keys[-1]] if keys else None


def mix_of(call, auto_share, steps_share, boost_share=None, cushion_share=None):
    """(stocks, sleeve, cash) fractions for a call."""
    m = call['m']
    if m == 'auto':
        return auto_share, 1 - auto_share, 0.0
    if m == 'boost100':
        return 1.0, 0.0, 0.0
    if m == 'cushion':
        c_ = 1.0 if cushion_share is None else cushion_share
        return c_, 1 - c_, 0.0
    if m == 'boost':
        b = auto_share if boost_share is None else boost_share
        return b, 1 - b, 0.0
    if m == 'steps':
        return steps_share, 1 - steps_share, 0.0
    if m == 'cash':
        return 0.0, 0.0, 1.0
    s = max(0.0, min(100.0, float(call.get('s') or 0)))
    v = max(0.0, min(100.0 - s, float(call.get('v') or 0)))
    return s / 100, v / 100, (100 - s - v) / 100


def slots_for(model, call, ranks):
    """The stocks actually held: model picks with the call's drops (None = cash)
    and swaps applied where still valid."""
    drops = set(call.get('drops') or []) if call else set()
    swaps = {a: b for a, b in (call.get('swaps') or [])} if call else {}
    out, used = [], set(model)
    for t in model:
        if t in drops:
            out.append(None)
        elif t in swaps and ranks.get(swaps[t], 10 ** 9) <= SWAP_RANK and swaps[t] not in used:
            out.append(swaps[t])
            used.add(swaps[t])
        else:
            out.append(t)
    return out


def score(calls, calendar, weeks, picks_at, ranks_at, closes, sleeve, cash, slots_n=5, apply_picks=True,
          boost_picks_at=None, boostx_picks_at=None):
    """weeks: [(signal_friday, trade_day, auto_share, steps_share[, boost_share[, cushion_share]])], oldest first;
    picks_at(trade_day) -> the model's holdings traded that day (boost_picks_at: the
    News-boost list's, used for 'boost' calls; boostx_picks_at: that list with the blow-off
    exit, used for 'boost100' and 'cushion' calls - boost_picks_at when not given); ranks_at(friday)
    -> {ticker: rank}; closes {ticker: {date: close}}; sleeve / cash {date: value}.
    apply_picks=False ignores swaps and drops (same mixes, the model's own stocks).
    Returns dict(curve=[[date, nav]], weeks=[[friday, trade_day, slots, [s, v, c]]]) or None."""
    calls = live_calls(calls)
    if not calls:
        return None
    first = min(calls)
    todo = [w for w in weeks if w[0] >= first and w[1] in calendar]
    if not todo:
        return None
    trade = {w[1]: w for w in todo}
    start = todo[0][1]
    last_px = {}

    def px(t, d):
        p = closes.get(t, {}).get(d)
        if p:
            last_px[t] = p
        return last_px.get(t)

    nav, sh, sl_units, cash_units = 1.0, {}, 0.0, 0.0
    curve, out_weeks, prev = [], [], None
    for d in calendar:
        if d < start:
            continue
        if prev is not None:
            nav = sum(n * px(t, d) for t, n in sh.items()) + sl_units * sleeve[d] + cash_units * cash[d]
        for t in list(sh):   # keep last prices current even on quiet days
            px(t, d)
        if d in trade:
            f, _, a_sh, s_sh = trade[d][:4]
            b_sh = trade[d][4] if len(trade[d]) > 4 else None
            c_sh = trade[d][5] if len(trade[d]) > 5 else None
            call = call_for(calls, f)
            s, v, c = mix_of(call, a_sh, s_sh, b_sh, c_sh)
            if call['m'] in ('boost100', 'cushion') and (boostx_picks_at or boost_picks_at):
                model = list((boostx_picks_at or boost_picks_at)(d))
            else:
                model = list((boost_picks_at if call['m'] == 'boost' and boost_picks_at else picks_at)(d))
            slots = slots_for(model, call if apply_picks else None, ranks_at(f)) if model else []
            per = nav * s / slots_n
            sh = {}
            empty = slots_n - sum(1 for t in slots if t)
            for t in slots:
                if t and px(t, d):
                    sh[t] = sh.get(t, 0.0) + per / px(t, d)
                elif t:
                    empty += 1
            sl_units = nav * v / sleeve[d]
            cash_units = (nav * c + per * empty) / cash[d]
            out_weeks.append([f, d, slots, [round(s, 4), round(v, 4), round(c, 4)]])
        curve.append([d, round(nav, 6)])
        prev = d
    return dict(curve=curve, weeks=out_weeks)

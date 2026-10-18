"""Market phase for the scanner page (information only: no rule reads it). From SPY's closes, with the usual
definitions: a bear market is SPY 20%+ under its high; a new bull run starts when SPY has risen 20% from a bear-market
low and lasts until a new high; a correction is 10-20% under the high; otherwise a bull run while SPY is above its
200-day average. During a correction, a bear market or a new bull run it also lists which early signs of a bottom
have fired in the last month. Backtested on the plan from 2000 (Oct 18, 2026), none of these signs helped as a
trade signal: they fire 1-2 weeks after real bottoms but just as quickly in bear-market rallies."""
BEAR, CORR, NEW = 0.20, 0.10, 0.20


def swings(closes):
    """The 20% bull/bear swings: [(state, start index, extreme index)]. A bear market starts at a high that SPY then
    fell 20% under; it ends at its lowest close once SPY has risen 20% off it, which starts the next bull run."""
    out, state, ext = [], 'bull', 0
    start = 0
    for k, x in enumerate(closes):
        if state == 'bull':
            if x >= closes[ext]:
                ext = k
            elif x <= closes[ext] * (1 - BEAR):
                out.append(('bull', start, ext))
                state, start, ext = 'bear', ext, k
        else:
            if x <= closes[ext]:
                ext = k
            elif x >= closes[ext] * (1 + NEW):
                out.append(('bear', start, ext))
                state, start, ext = 'bull', ext, k
    out.append((state, start, ext))
    return out


def early_signs(cal, spy, spy_vol, vix, prices, members):
    """Signs of a bottom that fired in the last 21 sessions: [(name, date)]."""
    K, out = len(cal), []
    if K < 260:
        return out
    look = range(K - 21, K)
    # breadth: the day's rising share of members, its 10-day average, and the share above their 50-day average
    ks = range(K - 60, K)
    ratio, above = {}, {}
    for k in ks:
        up = dn = ab = n50 = 0
        for t in members:
            p = prices.get(t) or {}
            a, b = p.get(cal[k]), p.get(cal[k - 1])
            if a and b:
                up += a > b; dn += a < b
            w = [p.get(cal[i]) for i in range(k - 49, k + 1)]
            if a and all(w):
                n50 += 1; ab += a > sum(w) / 50
        ratio[k] = up / max(up + dn, 1)
        above[k] = 100 * ab / max(n50, 1)
    ema, e = {}, 0.5
    for k in ks:
        e += 2 / 11 * (ratio[k] - e); ema[k] = e
    ma200 = lambda k: sum(spy[k - 199:k + 1]) / 200
    for k in look:
        d = cal[k]
        if k - 10 >= ks[0] and ema[k] > 0.615 and min(ema[i] for i in range(k - 10, k)) < 0.40:
            out.append(('breadth thrust: the 10-day share of rising stocks jumped from under 40% to over 61.5%', d))
        if k - 30 >= ks[0] and above[k] >= 60 and min(above[i] for i in range(k - 30, k)) <= 15:
            out.append(('breadth recovery: 60% of S&P stocks back above their 50-day average, from 15% or less', d))
        lo = k - 25 + min(range(26), key=lambda i: spy[k - 25 + i])
        hi = max(spy[max(0, k - 251):k + 1])
        if 4 <= k - lo <= 15 and spy[k] / hi - 1 <= -0.08 and spy[k] / spy[k - 1] - 1 >= 0.015 \
                and spy_vol.get(cal[k], 0) > spy_vol.get(cal[k - 1], 0):
            out.append(('follow-through day: SPY up 1.5%+ on rising volume, 4-15 days after a low', d))
        vk = [vix.get(cal[i]) for i in range(k - 62, k + 1) if vix.get(cal[i])]
        if vk and max(vk) >= 35 and vix.get(d) and vix[d] <= 0.6 * max(vk) and vix[d] < 25:
            out.append((f'fear fading: the VIX at {vix[d]:.0f}, down 40%+ from its {max(vk):.0f} spike', d))
        if spy[k] > ma200(k) and spy[k - 1] <= ma200(k - 1) and min(spy[i] / max(spy[max(0, i - 251):i + 1]) - 1
                                                                       for i in range(k - 125, k + 1)) <= -0.15:
            out.append(('SPY back above its 200-day average after a 15%+ drop', d))
    seen, res = set(), []
    for name, d in reversed(out):   # the latest firing of each
        key = name.split(':')[0]
        if key not in seen:
            seen.add(key); res.append((name, d))
    return res


def market_phase(cal, spy, spy_vol=None, vix=None, prices=None, members=()):
    """{phase, since, dd, high, low, above200, signs} on cal[-1] from SPY closes aligned with cal. Phases: 'bull run'
    (within 10% of its high), 'correction' (10-20% under it), 'new bull run' (up 20% from a bear-market low, no new
    high yet), 'bear market' (20%+ under its high), 'recovering' (a bear market's rally that hasn't reached +20%)."""
    K = len(cal)
    sw = swings(spy)
    state, start, ext = sw[-1]
    above200 = K >= 200 and spy[-1] > sum(spy[-200:]) / 200
    if state == 'bear':
        pk, lo = start, ext
        up = spy[-1] / spy[lo] - 1
        phase = 'bear market' if spy[-1] <= spy[pk] * (1 - BEAR) else 'recovering'
        return dict(phase=phase, since=cal[pk], dd=round(spy[-1] / spy[pk] - 1, 4), high=cal[pk], low=cal[lo],
                    up=round(up, 4), above200=above200,
                    signs=[dict(what=w, d=d) for w, d in early_signs(cal, spy, spy_vol or {}, vix or {}, prices or {}, members)]
                    if prices is not None else [])
    lo, pk = start, ext
    prev_peak = sw[-2][1] if len(sw) >= 2 else None          # the high the last bear market started from
    newhigh = prev_peak is None or spy[pk] >= spy[prev_peak]
    dd = spy[-1] / spy[pk] - 1
    if not newhigh:
        phase = 'new bull run'
    elif dd <= -CORR:
        phase = 'correction'
    else:
        phase = 'bull run'
    signs = []
    if phase in ('correction', 'new bull run') and prices is not None:
        signs = [dict(what=w, d=d) for w, d in early_signs(cal, spy, spy_vol or {}, vix or {}, prices, members)]
    return dict(phase=phase, since=cal[lo] if len(sw) > 1 else None, dd=round(dd, 4), high=cal[pk],
                low=cal[lo] if len(sw) > 1 else None, up=round(spy[-1] / spy[lo] - 1, 4), above200=above200, signs=signs)

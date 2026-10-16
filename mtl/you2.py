"""You-2: the viewer's own stocks, timed by the default plan (Boost + rotation).

The viewer enters a stock list on the dashboard (saved in docs/my_calls.json under "you2": {date: {stocks,
note, at}}). Whenever the default plan holds the Boost list, You-2 holds the viewer's list instead, in equal
weights; whenever the plan is out of stocks (the rotation, the downtrend and lower-high exits, the narrow-market
cash week, no T-bills) or holds the whipsaw half, You-2 does exactly the same, and the rebound rule puts it back
in the viewer's stocks. Like the plan, a list (or a switch) decided at a close is traded at the next close.

Since Oct 16, 2026 it also follows the plan's fading-energy filter (mtl/fade.py): a stock on the list whose volume
and daily swings have both faded when the list is bought isn't bought; its share stays in cash and it is checked
again at each week's last close, then bought at the next close once it no longer fades.

Started Oct 14, 2026 with the default's own five stocks."""
from mtl.rotation import CASH, SWITCH_COST, WHIP_SHARE, rotation_curve

YOU2_START = '2026-10-14'
YOU2_MAX = 10          # stocks in one list


def entries_of(doc):
    """{date: [tickers]} from docs/my_calls.json's "you2" block (deleted entries left out)."""
    out = {}
    for d, e in ((doc or {}).get('you2') or {}).items():
        if isinstance(e, dict) and e.get('m') != 'del' and e.get('stocks'):
            out[d] = [t for t in e['stocks']][:YOU2_MAX]
    return out


def active_list(entries, day):
    """The list decided at or before `day`'s close (the newest entry dated <= day), or []."""
    keys = [k for k in sorted(entries) if k <= day]
    return entries[keys[-1]] if keys else []


def _week_end(calendar, k):
    from datetime import date
    return k + 1 >= len(calendar) or date.fromisoformat(calendar[k + 1]).isocalendar()[:2] != date.fromisoformat(calendar[k]).isocalendar()[:2]


def picks_curve(entries, prices, calendar, start, cost=SWITCH_COST, skip=None):
    """[[date, value]] from 1.0 at `start`: the viewer's stocks in equal weights, bought at the close after the
    list's date and left to drift until the next list (changing the list costs `cost`); cash before the first
    list is traded. prices: {ticker: {date: close}}; a stock with no price on a day keeps its value.
    skip(t, k) -> True: don't buy t at the close after calendar[k] (the fading-energy filter); its equal share stays
    in cash and it is bought once skip is False at a week's last close."""
    idx = {d: i for i, d in enumerate(calendar)}
    ds = [d for d in calendar if d >= start]
    out, w, cur, prev, waiting = [], {}, None, None, []
    val = 1.0
    for d in ds:
        if prev is not None and w:
            for t in w:
                if t == CASH:
                    continue
                p0, p1 = prices.get(t, {}).get(prev), prices.get(t, {}).get(d)
                if p0 and p1:
                    w[t] *= p1 / p0
            val = sum(w.values())
        k = idx[d]
        lst = active_list(entries, calendar[k - 1]) if k > 0 else []   # decided yesterday, traded at today's close
        lst = [t for t in lst if prices.get(t, {}).get(d)]
        if lst and lst != cur:
            val *= 1 - (cost if cur else 0.0)
            waiting = [t for t in lst if skip and k > 0 and skip(t, k - 1)]
            share = val / len(lst)
            w = {t: share for t in lst if t not in waiting}
            if waiting:
                w[CASH] = share * len(waiting)
            cur = lst
        elif waiting and k > 0 and _week_end(calendar, k - 1):
            for t in [t for t in waiting if not skip(t, k - 1)]:
                amt = min(w.get(CASH, 0.0), val / len(cur))
                w[CASH] = w.get(CASH, 0.0) - amt
                w[t] = amt
                waiting.remove(t)
        out.append([d, val])
        prev = d
    return out


def you2_curve(entries, prices, asset_px, calendar, modes, half, start=YOU2_START, skip=None):
    """[[date, value]] from 1.0 at `start`: picks_curve while the plan holds stocks, the plan's own holding
    (rotation_curve on the same modes and whipsaw half) otherwise."""
    pc = picks_curve(entries, prices, calendar, start, skip=skip)
    if not pc:
        return []
    cv = rotation_curve(pc, asset_px, calendar, modes, half=half)
    v0 = cv[0][1] or 1.0
    return [[d, v / v0] for d, v in cv]


def holding(modes, half, calendar, k):
    """What You-2 holds after calendar[k]'s close: 'stocks', an asset (TLT / GLD / CASH), or the whipsaw switch's
    asset ('stocks+X' while the switch kept part in stocks; what the plan decided at the previous close, traded
    at this one)."""
    y = calendar[k - 1] if k > 0 else calendar[k]
    m = modes.get(y, 'boost')
    if m != 'boost':
        return 'cash' if m == CASH else m
    h = (half or {}).get(y)
    return (h if WHIP_SHARE >= 1 else f'stocks+{h}') if h else 'stocks'


def block(doc, prices, asset_px, calendar, modes, half, plan_curve, spy_px, k, start=YOU2_START, skip=None, why=None):
    """The dashboard's You-2 payload at calendar[k]: the entries, today's list, what it holds now and what it
    will hold after the next close, and its value since `start` next to the default plan's and SPY's.
    skip(t, k): the fading-energy filter (stocks on today's list it flags are listed under `fading`, with
    why(t, k) -> (volume ratio, swing ratio) when given)."""
    entries = entries_of(doc)
    day = calendar[k]

    def rebase(c):
        pts = [[d, v] for d, v in c if start <= d <= day and v]
        return [[d, round(v / pts[0][1], 4)] for d, v in pts] if pts else []
    curve = you2_curve(entries, prices, asset_px, calendar[:k + 1], modes, half, start, skip=skip) if entries else []
    fading = []
    for t in active_list(entries, day) if skip else []:
        if prices.get(t, {}).get(day) and skip(t, k):
            vr, sr = why(t, k) if why else (None, None)
            fading.append(dict(t=t, vol=None if vr is None else round(vr, 3), swing=None if sr is None else round(sr, 3)))
    nxt = modes.get(day, 'boost')
    return dict(start=start, entries=[[d, entries[d]] for d in sorted(entries)], stocks=active_list(entries, day),
                holds=holding(modes, half, calendar, k),
                next='stocks' if nxt == 'boost' and not (half or {}).get(day) else
                ((half[day] if WHIP_SHARE >= 1 else 'stocks+' + half[day]) if nxt == 'boost' else ('cash' if nxt == CASH else nxt)),
                curve=[[d, round(v, 4)] for d, v in curve], plan=rebase(plan_curve),
                spy=rebase([[d, spy_px[d]] for d in calendar if d in spy_px]),
                missing=sorted({t for l in entries.values() for t in l if not prices.get(t, {}).get(day)}), fading=fading)

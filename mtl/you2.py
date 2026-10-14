"""You-2: the viewer's own stocks, timed by the default plan (Boost + rotation).

The viewer enters a stock list on the dashboard (saved in docs/my_calls.json under "you2": {date: {stocks,
note, at}}). Whenever the default plan holds the Boost list, You-2 holds the viewer's list instead, in equal
weights; whenever the plan is out of stocks (the rotation, the downtrend and lower-high exits, the narrow-market
cash week, no T-bills) or holds the whipsaw half, You-2 does exactly the same, and the rebound rule puts it back
in the viewer's stocks. Like the plan, a list (or a switch) decided at a close is traded at the next close.

Started Oct 14, 2026 with the default's own five stocks."""
from mtl.rotation import CASH, SWITCH_COST, rotation_curve

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


def picks_curve(entries, prices, calendar, start, cost=SWITCH_COST):
    """[[date, value]] from 1.0 at `start`: the viewer's stocks in equal weights, bought at the close after the
    list's date and left to drift until the next list (changing the list costs `cost`); cash before the first
    list is traded. prices: {ticker: {date: close}}; a stock with no price on a day keeps its value."""
    idx = {d: i for i, d in enumerate(calendar)}
    ds = [d for d in calendar if d >= start]
    out, w, cur, prev = [], {}, None, None
    val = 1.0
    for d in ds:
        if prev is not None and w:
            for t in w:
                p0, p1 = prices.get(t, {}).get(prev), prices.get(t, {}).get(d)
                if p0 and p1:
                    w[t] *= p1 / p0
            val = sum(w.values())
        k = idx[d]
        lst = active_list(entries, calendar[k - 1]) if k > 0 else []   # decided yesterday, traded at today's close
        lst = [t for t in lst if prices.get(t, {}).get(d)]
        if lst and lst != cur:
            val *= 1 - (cost if cur else 0.0)
            w = {t: val / len(lst) for t in lst}
            cur = lst
        out.append([d, val])
        prev = d
    return out


def you2_curve(entries, prices, asset_px, calendar, modes, half, start=YOU2_START):
    """[[date, value]] from 1.0 at `start`: picks_curve while the plan holds stocks, the plan's own holding
    (rotation_curve on the same modes and whipsaw half) otherwise."""
    pc = picks_curve(entries, prices, calendar, start)
    if not pc:
        return []
    cv = rotation_curve(pc, asset_px, calendar, modes, half=half)
    v0 = cv[0][1] or 1.0
    return [[d, v / v0] for d, v in cv]


def holding(modes, half, calendar, k):
    """What You-2 holds after calendar[k]'s close: 'stocks', an asset (TLT / GLD / CASH), or 'stocks+X' for the
    whipsaw half (what the plan decided at the previous close, traded at this one)."""
    y = calendar[k - 1] if k > 0 else calendar[k]
    m = modes.get(y, 'boost')
    if m != 'boost':
        return 'cash' if m == CASH else m
    h = (half or {}).get(y)
    return f'stocks+{h}' if h else 'stocks'


def block(doc, prices, asset_px, calendar, modes, half, plan_curve, spy_px, k, start=YOU2_START):
    """The dashboard's You-2 payload at calendar[k]: the entries, today's list, what it holds now and what it
    will hold after the next close, and its value since `start` next to the default plan's and SPY's."""
    entries = entries_of(doc)
    day = calendar[k]

    def rebase(c):
        pts = [[d, v] for d, v in c if start <= d <= day and v]
        return [[d, round(v / pts[0][1], 4)] for d, v in pts] if pts else []
    curve = you2_curve(entries, prices, asset_px, calendar[:k + 1], modes, half, start) if entries else []
    nxt = modes.get(day, 'boost')
    return dict(start=start, entries=[[d, entries[d]] for d in sorted(entries)], stocks=active_list(entries, day),
                holds=holding(modes, half, calendar, k),
                next='stocks' if nxt == 'boost' and not (half or {}).get(day) else
                ('stocks+' + half[day] if nxt == 'boost' else ('cash' if nxt == CASH else nxt)),
                curve=[[d, round(v, 4)] for d, v in curve], plan=rebase(plan_curve),
                spy=rebase([[d, spy_px[d]] for d in calendar if d in spy_px]),
                missing=sorted({t for l in entries.values() for t in l if not prices.get(t, {}).get(day)}))

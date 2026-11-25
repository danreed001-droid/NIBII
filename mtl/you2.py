"""You-2: the viewer's own stocks, timed by the default plan (Boost + rotation).

The viewer enters a stock list on the dashboard (saved in docs/my_calls.json under "you2": {date: {stocks,
note, at}}). Whenever the default plan holds the Boost list, You-2 holds the viewer's list instead, in equal
weights; whenever the plan is out of stocks (the rotation, the downtrend and lower-high exits, the narrow-market
cash week, no T-bills) or holds the whipsaw half, You-2 does exactly the same, and the rebound rule puts it back
in the viewer's stocks. Like the plan, a list (or a switch) decided at a close is traded at the next close.

Since Oct 16, 2026 it also follows the plan's fading-energy filter (mtl/fade.py): a stock on the list whose volume
and daily swings have both faded when the list is bought isn't bought; its share stays in cash and it is checked
again at each week's last close, then bought at the next close once it no longer fades.

Started Oct 14, 2026 with the default's own five stocks.

The viewer's actual moves (docs/my_calls.json "moves": {date: {to, note, at}}) give a second line, "You (actual)":
it follows You-2 until the first move, then holds what the viewer moved into - 'cash', 'stocks' (the viewer's list),
'GLD', 'TLT' or 'DBMF', or a 'mix' of up to 10 tickers with their shares (e.g. half TLT, half MRNA, bought at that
close and left to drift) - from that date's close (the viewer trades on the day, not at the next close), and 'plan'
hands it back to You-2's timing."""
from mtl.rotation import CASH, SWITCH_COST, WHIP_SHARE, rotation_curve

YOU2_START = '2026-10-14'
YOU2_MAX = 10          # stocks in one list
MOVES = ('cash', 'stocks', 'GLD', 'TLT', 'DBMF', 'plan', 'mix')   # what the viewer can log moving into
MIX_MAX = 10           # tickers in one mix


def _source(doc, name=None):
    """The dated entries of You-2 (name None) or of the viewer's named plan `name` (docs/my_calls.json "plans")."""
    if name is None:
        return (doc or {}).get('you2') or {}
    return ((doc or {}).get('plans') or {}).get(name) or {}


def entries_of(doc, name=None):
    """{date: [tickers]} from docs/my_calls.json's "you2" block, or a named plan's (deleted entries left out)."""
    out = {}
    for d, e in _source(doc, name).items():
        if isinstance(e, dict) and e.get('m') != 'del' and e.get('stocks'):
            out[d] = [t for t in e['stocks']][:YOU2_MAX]
    return out


def notes_of(doc, name=None):
    """{date: note} for the entries of You-2 or a named plan (the viewer's reason for each list)."""
    return {d: str(e.get('note') or '') for d, e in _source(doc, name).items() if isinstance(e, dict) and e.get('stocks')}


def plan_names(doc):
    """The viewer's named plans with at least one live list, in the order first saved."""
    out = []
    for nm, ent in ((doc or {}).get('plans') or {}).items():
        if isinstance(ent, dict) and entries_of(doc, nm):
            out.append((min(entries_of(doc, nm)), nm))
    return [nm for _, nm in sorted(out)]


def mix_of(e):
    """A logged move's mix {ticker: share} (shares add up to 1), or None when it has no valid mix."""
    m = (e or {}).get('mix') if isinstance(e, dict) else None
    if not isinstance(m, dict):
        return None
    w = {str(t).upper(): float(v) for t, v in m.items() if isinstance(v, (int, float)) and v > 0}
    w = dict(sorted(w.items(), key=lambda x: -x[1])[:MIX_MAX])
    tot = sum(w.values())
    return {t: v / tot for t, v in w.items()} if tot > 0 else None


def mix_label(w):
    """'50% TLT + 50% MRNA'."""
    return ' + '.join(f'{round(v * 100)}% {t}' for t, v in sorted(w.items(), key=lambda x: -x[1]))


def tickers_of(doc):
    """Every ticker on any list of You-2 or a named plan, and in any logged mix."""
    out = {t for l in entries_of(doc).values() for t in l}
    for e in ((doc or {}).get('moves') or {}).values():
        out |= set(mix_of(e) or {})
    for nm in plan_names(doc):
        out |= {t for l in entries_of(doc, nm).values() for t in l}
    return out


def moves_of(doc):
    """{date: (to, note)} of the viewer's logged moves (deleted ones and unknown targets left out), oldest first;
    a mix's `to` is its {ticker: share}."""
    out = {}
    for d, e in sorted(((doc or {}).get('moves') or {}).items()):
        if isinstance(e, dict) and e.get('m') != 'del' and e.get('to') in MOVES:
            if e['to'] == 'mix':
                w = mix_of(e)
                if w:
                    out[d] = (w, str(e.get('note') or ''))
            else:
                out[d] = (e['to'], str(e.get('note') or ''))
    return out


def mine_curve(y2_curve, picks, asset_px, calendar, moves, cost=SWITCH_COST, prices=None):
    """[[date, value]] on y2_curve's dates from its first value: You-2's moves until the viewer's first logged move,
    then what each move went into, from the close of the move's date (a non-session date counts at the session
    before it; one before the start at the start). picks: the viewer's list alone (picks_curve); a mix {ticker: share}
    is bought at the move's close and left to drift (prices: {ticker: {date: close}}, else asset_px; a missing close
    keeps the last one); a switch costs `cost` of the account."""
    if not y2_curve:
        return []
    y2, pk, ds = dict(y2_curve), dict(picks or []), [d for d, _ in y2_curve]
    at = {}
    for m in sorted(moves):
        k = max([i for i, d in enumerate(ds) if d <= m] or [0])
        at[ds[k]] = moves[m][0]

    def ret(h, a, b):
        if h == 'plan':
            return y2[b] / y2[a] if y2.get(a) else 1.0
        if h == 'stocks':
            return pk[b] / pk[a] if pk.get(a) and pk.get(b) else 1.0
        if h == 'cash':
            return 1.0
        p0, p1 = (asset_px.get(h) or {}).get(a), (asset_px.get(h) or {}).get(b)
        return p1 / p0 if p0 and p1 else 1.0
    px_all, last_px = dict(asset_px or {}), {}
    px_all.update(prices or {})

    def px(t, d):
        v = (px_all.get(t) or {}).get(d)
        if v:
            last_px[t] = v
        return last_px.get(t)
    out, val, held, prev, units = [], y2[ds[0]] or 1.0, 'plan', None, {}
    for d in ds:
        if isinstance(held, dict):
            for t in held:
                px(t, d)
            if prev is not None:
                val = sum(u * (last_px.get(t) or 0) for t, u in units.items())
        elif prev is not None:
            val *= ret(held, prev, d)
        if d in at and at[d] != held:
            val *= 1 - cost
            held = at[d]
            if isinstance(held, dict):
                units = {}
                cash_share = 0.0
                for t, w in held.items():
                    p_ = px(t, d)
                    if p_:
                        units[t] = val * w / p_
                    else:
                        cash_share += w
                units['__cash__'] = val * cash_share
                last_px['__cash__'] = 1.0
        out.append([d, val])
        prev = d
    v0 = out[0][1] or 1.0
    return [[d, v / v0] for d, v in out]


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


def block(doc, prices, asset_px, calendar, modes, half, plan_curve, spy_px, k, start=YOU2_START, skip=None, why=None, name=None):
    """The dashboard's You-2 payload at calendar[k]: the entries, today's list, what it holds now and what it
    will hold after the next close, and its value since `start` next to the default plan's and SPY's.
    skip(t, k): the fading-energy filter (stocks on today's list it flags are listed under `fading`, with
    why(t, k) -> (volume ratio, swing ratio) when given). name: a named plan of the viewer's instead of You-2.
    Each entry is [date, tickers, note, its return, the default plan's return] over the span the list was held
    (from the date's close to the next list's date or today; None before it is traded)."""
    entries = entries_of(doc, name)
    notes = notes_of(doc, name)
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
    pc = rebase(plan_curve)

    def span(c, a, b):
        pts = [v for d, v in c if a <= d <= b]
        return round(pts[-1] / pts[0] - 1, 4) if len(pts) >= 2 and pts[0] else None
    ds_ = sorted(entries)
    cal_k = calendar[:k + 1]

    def traded(d):   # a list decided at d's close is bought at the next session's close
        nxt = [x for x in cal_k if x > d]
        return nxt[0] if nxt else None
    rows = []
    for i, d in enumerate(ds_):
        a = traded(d)
        b = (traded(ds_[i + 1]) or day) if i + 1 < len(ds_) else day
        rows.append([d, entries[d], notes.get(d, ''), span(curve, a, b) if a else None, span(pc, a, b) if a else None])
    mine = {}
    mv = moves_of(doc) if name is None else {}
    if mv and curve:   # the viewer's actual moves: "You (actual)" (mtl/you2.mine_curve)
        pk = picks_curve(entries, prices, calendar[:k + 1], start, skip=skip)
        mc = mine_curve(curve, pk, asset_px, calendar[:k + 1], {d: v for d, v in mv.items() if d <= day}, prices=prices)
        last = [to for d, (to, _) in mv.items() if d <= day]
        h = last[-1] if last else 'plan'
        lab = lambda x: mix_label(x) if isinstance(x, dict) else x
        mine = dict(mine=[[d, round(v, 4)] for d, v in mc], moves=[[d, lab(to), note] for d, (to, note) in mv.items()],
                    mineHolds=holding(modes, half, calendar, k) if h == 'plan' else ('CASH' if h == 'cash' else lab(h)))
    return dict(**mine, start=start, entries=rows, stocks=active_list(entries, day),
                holds=holding(modes, half, calendar, k),
                next='stocks' if nxt == 'boost' and not (half or {}).get(day) else
                ((half[day] if WHIP_SHARE >= 1 else 'stocks+' + half[day]) if nxt == 'boost' else ('cash' if nxt == CASH else nxt)),
                curve=[[d, round(v, 4)] for d, v in curve], plan=pc,
                spy=rebase([[d, spy_px[d]] for d in calendar if d in spy_px]),
                missing=sorted({t for l in entries.values() for t in l if not prices.get(t, {}).get(day)}), fading=fading)


def plans_block(doc, prices, asset_px, calendar, modes, half, plan_curve, spy_px, k, skip=None, why=None):
    """{name: block} for each of the viewer's named plans, each from its first list's date."""
    out = {}
    for nm in plan_names(doc):
        st = min(entries_of(doc, nm))
        if st <= calendar[k]:
            out[nm] = block(doc, prices, asset_px, calendar, modes, half, plan_curve, spy_px, k, start=st, skip=skip, why=why, name=nm)
    return out

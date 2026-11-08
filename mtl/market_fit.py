"""Market fitness: does stock picking work in this market, and which way? Reviewed once a year (each January), from the
previous WIN (7) years only. Information only for the live US plan: it never changes the plan by itself.

At each month-end of the history:
- doublers: members up 100%+ over the last 252 sessions (at $5 or more), and for each one whether it gave back half of
  that gain within the next 126 sessions (known only once those sessions have passed) and how much of the gain came
  from its 5 biggest days;
- the full plan's month (its backtest curve), the simple top-5 pick on a 12-month look-back (the last month skipped,
  kept while in the top 10, COST a side on the names changed, out to cash while the index is under its 10-month
  average) and the index.
At a review (January of year Y, data before it), from the doublers alone (no past returns):
- quality gate: if more than GATE (25%) of the doublers gave back half their gain within 6 months, the index;
- otherwise supply: GOOD (2) or more good doublers a month on average (doublers that kept at least half the gain over
  the next 6 months) -> the full plan, fewer -> the simple 12-month pick.
A change of mode needs two reviews in a row. The plan's and the pick's past returns are shown, not used.

Why: replayed walk-forward 2012-2026 on 13 pools (the S&P 500 on its real member lists, the Nasdaq-100, the Dow, the
Russell 2000, the UK, Germany, France, Canada, Australia, Hong Kong, Spain, Italy and Sweden), this rule kept the S&P
500 on the full plan every year (its good doublers dipped under 2 a month once, to 1.8 at the 2021 review, and the
next review was back at 5.1, so the two-review rule kept the plan), sent the thin markets (0.1-1.7 good
doublers) to the 12-month pick and kept the Russell 2000 (give-back 30-36%) on its index: 24.6% a year on average
against 11.0% for the index, ahead of the index in 12 of 13 pools (the 13th held it). Cut-offs of 1.5-2.5 good
doublers gave nearly the same; an earlier version that chose by the plan's own 7-year record was fooled in Spain (6.1%
vs 11.6%: the plan's 2008 exits made its record look good). Reviews every 6, 3 or 1 months switched 3-10 times as
often and did worse. Nov 8, 2026.

Pure: closes {ticker: {date: close}}, a session calendar, member(t, d) -> bool, index closes {date: close}, the plan's
curve {date: value}."""
import math

WIN = 7          # years of history a review reads
GATE = 0.25      # the quality gate: the most give-back still treated as good runners
GOOD = 2.0       # good doublers a month (7-year average) for the full plan
LOOK = 252       # the simple pick's look-back (12 months), the last SKIP sessions left out
SKIP = 21
TOP, KEEP = 5, 10
COST = 0.0015
MINPX = 5.0
TREND = 210      # the index's 10-month average (sessions)


def _carry(series, calendar, gap=5):
    out, last, miss = [], None, 99
    for d in calendar:
        v = series.get(d)
        if v:
            last, miss = v, 0
        else:
            miss += 1
        out.append(last if last is not None and miss <= gap else None)
    return out


def month_ends(calendar):
    return [i for i in range(len(calendar) - 1) if calendar[i + 1][:7] != calendar[i][:7]]


def records(closes, calendar, member, index, plan, minpx=MINPX, cost=COST):
    """(rows, events): one row per month-end (m, ew, pick, idx, up, plan) and one event per doubler (month, resolved
    month, gave_back, spike)."""
    tick = sorted(closes)
    C = {t: _carry(closes[t], calendar) for t in tick}
    IX = _carry(index, calendar, gap=10)
    PL = _carry(plan or {}, calendar, gap=10)
    me = month_ends(calendar)
    rows, events, held = [], [], []
    n = len(calendar)
    for k in range(len(me) - 1):
        i, j = me[k], me[k + 1]
        if i < LOOK + SKIP:
            continue
        live = [t for t in tick if C[t][i] and C[t][j] and C[t][i - LOOK] and C[t][i] >= minpx and member(t, calendar[i])]
        if len(live) < 15:
            continue
        ret = {t: C[t][j] / C[t][i] - 1 for t in live}
        ew = sum(ret.values()) / len(ret)
        sc = {t: C[t][i - SKIP] / C[t][i - SKIP - LOOK] - 1 for t in live if C[t][i - SKIP] and C[t][i - SKIP - LOOK]}
        rk = sorted(sc, key=lambda t: -sc[t])
        keep = [t for t in held if t in rk[:KEEP]]
        new = keep + [t for t in rk if t not in keep][:TOP - len(keep)]
        turn = len(set(new) - set(held)) / TOP * 2
        held = new
        pick = (sum(ret[t] for t in new) / len(new) - cost * turn) if new else 0.0
        ix_ok = IX[i] and IX[j]
        w = [x for x in IX[max(0, i - TREND):i + 1] if x]
        up = bool(IX[i] and w and IX[i] >= sum(w) / len(w))
        for t in live:
            if C[t][i] / C[t][i - LOOK] < 2:
                continue
            seg = C[t][i - LOOK:i + 1]
            if any(x is None for x in seg):
                continue
            lr = [math.log(b / a) for a, b in zip(seg, seg[1:])]
            tot = sum(lr)
            fut = [x for x in C[t][i:min(n, i + 127)] if x]
            half = C[t][i - LOOK] + 0.5 * (C[t][i] - C[t][i - LOOK])
            events.append((calendar[i][:7], calendar[min(n - 1, i + 126)][:7], min(fut) <= half, sum(sorted(lr)[-5:]) / tot))
        rows.append(dict(m=calendar[i][:7], ew=ew, pick=pick if up else 0.0, idx=(IX[j] / IX[i] - 1) if ix_ok else None,
                         plan=(PL[j] / PL[i] - 1) if PL[i] and PL[j] else None))
    return rows, events


def _cagr(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 48:
        return None
    v = 1.0
    for x in xs:
        v *= 1 + x
    return v ** (12 / len(xs)) - 1


def readings(rows, events, year, win=WIN):
    """The review of January `year`, from the `win` years before it, or None when the history is too short."""
    a, b = f'{year - win}-01', f'{year}-01'
    rs = [r for r in rows if a <= r['m'] < b]
    if len(rs) < 48:
        return None
    ev = [e for e in events if a <= e[0] and e[1] < b]
    give = sum(1 for e in ev if e[2]) / len(ev) if len(ev) >= 10 else None
    kept = {}
    for e in ev:
        if not e[2]:
            kept[e[0]] = kept.get(e[0], 0) + 1
    good = sum(kept.get(r['m'], 0) for r in rs) / len(rs)
    spike = sorted(e[3] for e in ev)[len(ev) // 2] if ev else None
    counts = {}
    for e in events:
        if a <= e[0] < b:
            counts[e[0]] = counts.get(e[0], 0) + 1
    dbl = sorted(counts.get(r['m'], 0) for r in rs)[len(rs) // 2]
    return dict(year=year, giveBack=give, spike=spike, doublers=dbl, good=round(good, 2), events=len(ev),
                plan=_cagr([r['plan'] for r in rs]), pick=_cagr([r['pick'] for r in rs]), index=_cagr([r['idx'] for r in rs]))


def choose(r, gate=GATE, good=GOOD):
    """'plan', 'pick' (the simple 12-month pick) or 'index' for one review's readings, from the doublers alone."""
    if r is None or r['giveBack'] is None or r['giveBack'] > gate:
        return 'index'
    return 'plan' if r.get('good', 0) >= good else 'pick'


def decide(reviews):
    """The mode in force after each review (a change needs two reviews in a row): [(year, choice, mode)]."""
    out, cur, pend = [], None, None
    for r in reviews:
        c = choose(r)
        if cur is None:
            cur = c
        elif c != cur:
            if pend == c:
                cur, pend = c, None
            else:
                pend = c
        else:
            pend = None
        out.append((r['year'] if r else None, c, cur))
    return out


def summary(rows, events, years, live_mode='plan'):
    """The yearly reviews and the alarm for a market whose live mode is `live_mode`."""
    rev = [readings(rows, events, y) for y in years]
    rev = [r for r in rev if r]
    dec = decide(rev)
    last = rev[-1] if rev else None
    mode = dec[-1][2] if dec else None
    choice = dec[-1][1] if dec else None
    why = []
    if last and last['giveBack'] is not None and last['giveBack'] > GATE:
        why.append('runner quality broke: %.0f%% of doublers gave back half their gain within 6 months (gate %.0f%%)'
                   % (last['giveBack'] * 100, GATE * 100))
    if last and last.get('good') is not None and last['good'] < GOOD:
        why.append('runner supply thinned: %.1f good doublers a month over the last %d years (the full plan needs %.0f)'
                   % (last['good'], WIN, GOOD))
    return dict(win=WIN, gate=GATE, good=GOOD, reviews=[dict(r, choice=c, mode=m) for r, (_, c, m) in zip(rev, dec)],
                mode=mode, choice=choice, alarm=bool(mode != live_mode), watch=bool(choice != live_mode), why=why)

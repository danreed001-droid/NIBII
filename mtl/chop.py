"""Choppy-market watch (information only): is the default plan whipsawing?

The default plan holds either the Boost list or, the whole account, one asset (TLT or GLD, through the whipsaw
switch too since Oct 28, 2026 (SPY before), DBMF or cash). The watch counts the closes at which that holding changed in the last LOOK sessions and is on
when there were NEED or more: the plan is flipping, as in late 2015 (17 moves in four months; the plan lost 12% while
SPY rose 7%). It changes nothing the plan does. Tested as rules on top of the plan (Oct 20, 2026), with this signal
and others (SPY's efficiency ratio, a choppiness index): a minimum hold of 5 to 15 sessions after any move, holding
the strongest of SPY / gold / bonds, holding the stocks, or parking in cash or DBMF while all three move little - none
beat following the plan from all four start years, because the same signal also fires at the start of real crashes
(2008, 2020, 2022). On about 30% of sessions in the 2000-2026 backtest (data/plan_history.json).

Pure and network-free."""
from bisect import bisect_right

LOOK = 40   # sessions (about two months)
NEED = 3    # holding changes in that window


def holding(modes, half, d):
    """What the plan holds after close d: 'boost' (the Boost list) or the asset that holds the whole account."""
    m = modes.get(d, 'boost')
    return (half or {}).get(d) or 'boost' if m == 'boost' else m


def moves(modes, half, calendar, k):
    """[(close, from, to)] for every holding change decided at a close up to calendar[k], oldest first."""
    out, prev = [], None
    for d in calendar[:k + 1]:
        if d not in modes:
            continue
        h = holding(modes, half, d)
        if prev is not None and h != prev:
            out.append((d, prev, h))
        prev = h
    return out


def watch(modes, half, calendar, k, look=LOOK, need=NEED):
    """The watch read at the close of calendar[k]: on, prevOn (at the close before), n (moves in the last `look`
    sessions), the moves in that window, since (the close the current spell turned on) and the last spells."""
    mv = moves(modes, half, calendar, k)
    idx = {d: i for i, d in enumerate(calendar)}
    at = [idx[d] for d, _, _ in mv]

    def count(j):       # moves at closes j-look+1 .. j (`at` is sorted)
        return bisect_right(at, j) - bisect_right(at, j - look)

    on_at = {}
    first = min(at) if at else k
    for j in range(max(0, first), k + 1):
        on_at[j] = count(j) >= need
    on, prev_on = on_at.get(k, False), on_at.get(k - 1, False)
    spells, start = [], None
    for j in range(max(0, first), k + 1):
        if on_at[j] and start is None:
            start = j
        if not on_at[j] and start is not None:
            spells.append([calendar[start], calendar[j - 1]])
            start = None
    if start is not None:
        spells.append([calendar[start], None])
    window = [[d, a, b] for d, a, b in mv if idx[d] > k - look]
    return dict(on=on, prevOn=prev_on, n=count(k), look=look, need=need, moves=window,
                since=spells[-1][0] if on and spells else None, spells=spells[-5:],
                daysOn=sum(1 for v in on_at.values() if v), days=len(on_at))

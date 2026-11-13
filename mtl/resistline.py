"""The resistance-line exit (rule 22 of the default plan, from the close of Nov 13, 2026, on probation): when SPY, near
its high and just after a sharp down day, comes back up to a falling line through its recent lower highs and closes
under it on a Friday, the plan steps out of stocks for up to two weeks: into TLT if TLT is rising, else cash.

On SPY's daily bars (dividend-adjusted, as the plan reads them), at the close of session k, the last session of a week:
- swing highs: a session whose high is the highest of the W (3) sessions either side of it (known W sessions later);
- a falling line runs through two swing highs within the LOOK (120) sessions to k, the first higher than the second and
  at least MIN_SPAN (15) sessions before k, and no close since the first one is more than TOL (0.6%) above the line;
- the line counts TOUCHES (4) or more: the swing highs since its start within TOL of it, plus session k itself;
- session k tests it: its high is within TOL of the line (or above it) and its close is under the line;
- SPY closes within NEAR (10%) of its highest close of the last 252 sessions (a pullback near the highs, not a bear
  market), and one of the last DROP_DAYS (10) sessions closed DROP (2%) or more down.
Then, where the plan would hold stocks, it holds TLT if TLT is up over the last 3 months (63 sessions) at that close,
else cash (nothing bought), from that decision; at the close of each later
week's last session it goes back to the plan when SPY closes BREAK (0.5%) or more above the line, or after MAX_WEEKS (2)
weeks at the latest. While it is out a new signal can't start. Applied after the no-T-bills swap (so the cash stays
cash) and before the price-break rule and the Fed-day hold. Decided at the close, traded at the next close.

Why: the owner's idea from SPY's chart on Nov 13, 2026 (a falling line from the Oct 6 high touched 4-5 times, the -4.4%
day on Nov 5, SPY back up to the line on a Friday) and the human-review lesson "act early in a pullback near the highs,
not deep in a bear market". Strict test (S&P 500 members as of each date, 0.15% a side; Nov 13, 2026): AUDIT below.
In the research replay it fired 5 times since 2000 (Mar 2000, Dec 2007, Nov and Dec 2011, Sep 2024) and helped in 4;
without the near-the-high condition every one of 144 versions did worse than the plan (the same setup after a crash, as
in Apr 2003, Apr 2009, Apr 2020 and Apr 2025, is the start of a rebound), and with it only 28 of 128 nearby versions
were ahead. Very few cases and settings chosen after looking: on probation.

Pure: SPY's bars [(date, open, high, low, close)] in calendar order, the session calendar."""
from datetime import date

W = 3
LOOK = 120
TOL = 0.006
TOUCHES = 4
MIN_SPAN = 15
NEAR = 0.10
DROP = 0.02
DROP_DAYS = 10
BREAK = 0.005
MAX_WEEKS = 2
HIGH = 252
START = '2026-11-13'
AUDIT = ('61.6% a year from 2000 vs 60.4% without it, 62.8% vs 61.9% from 2010, 81.3% vs 82.0% from 2016, 121.2% vs 122.5% '
         'from 2020, worst drop -25% both, ahead in 3 years and behind in 1 (t-stat 1.4); cash every time 61.2%, TLT every '
         'time 61.6% (TLT was rising at every past signal); Sep 2024 is the miss that costs the 2016 and 2020 starts')


def _series(bars, calendar):
    """(highs, closes) aligned to the calendar, carried over a missing session."""
    by = {b[0][:10]: b for b in bars}
    h, c, lh, lc = [], [], None, None
    for d in calendar:
        if d in by:
            lh, lc = by[d][2], by[d][4]
        h.append(lh)
        c.append(lc)
    return h, c


def week_ends(calendar, week_closed=True):
    """The sessions (indexes) that are the last of their week; the calendar's last day counts when week_closed."""
    iso = [date.fromisoformat(d).isocalendar()[:2] for d in calendar]
    out = {k for k in range(len(calendar) - 1) if iso[k + 1] != iso[k]}
    if calendar and week_closed:
        out.add(len(calendar) - 1)
    return out


def lines_at(h, c, k, w=W, look=LOOK, tol=TOL, min_span=MIN_SPAN):
    """The falling lines session k tests and closes under: [(touches, first, second, slope, line at k)]."""
    lo = max(w, k - look)
    piv = [i for i in range(lo, k - w + 1)
           if h[i] is not None and None not in h[i - w:i + w + 1] and h[i] == max(h[i - w:i + w + 1])]
    out = []
    for x, a in enumerate(piv):
        if k - a < min_span:
            continue
        for b in piv[x + 1:]:
            if h[b] >= h[a]:
                continue
            m = (h[b] - h[a]) / (b - a)
            line = [h[a] + m * (i - a) for i in range(a, k + 1)]
            if any(c[i] is not None and c[i] > line[i - a] * (1 + tol) for i in range(a, k + 1)):
                continue
            lk = line[-1]
            if not (h[k] >= lk * (1 - tol) and c[k] < lk):
                continue
            n = sum(1 for p in piv if p >= a and abs(h[p] - line[p - a]) <= tol * line[p - a]) + (0 if k in piv else 1)
            out.append((n, a, b, m, lk))
    return out


def reading(h, c, k, touches=TOUCHES, near=NEAR, drop=DROP, drop_days=DROP_DAYS, high=HIGH):
    """At session k: dict(line, touches, dd, bigDrop, near, signal) (line: the strongest line tested, or None)."""
    if k < max(LOOK, high) or c[k] is None:
        return None
    ls = [x for x in lines_at(h, c, k) if x[0] >= touches]
    best = max(ls, key=lambda x: (x[0], -x[1])) if ls else None
    win = [x for x in c[k - high + 1:k + 1] if x is not None]
    dd = c[k] / max(win) - 1
    rets = [c[i] / c[i - 1] - 1 for i in range(k - drop_days + 1, k + 1) if c[i] is not None and c[i - 1]]
    big = bool(rets) and min(rets) <= -drop
    nr = dd >= -near
    return dict(line=None if not best else dict(touches=best[0], fromDate=best[1], viaDate=best[2], slope=best[3], at=round(best[4], 2)),
                dd=round(dd, 4), worstDay=round(min(rets), 4) if rets else None, bigDrop=big, near=nr,
                signal=bool(best) and big and nr)


def out_days(bars, calendar, start=START, in_stocks=lambda d: True, week_closed=True, dest=lambda k: 'CASH'):
    """(days, log): {decision day: holding} from `start` on where the rule holds TLT or cash (dest(k), picked at the
    signal's close for the whole stretch), and its stretches [{date, to, line, touches, back}] (back: the decision day it
    went back to the plan, None while still out)."""
    h, c = _series(bars, calendar)
    ends = week_ends(calendar, week_closed)
    days, log, k, n = {}, [], 0, len(calendar)
    while k < n:
        if calendar[k] < start or k not in ends or not in_stocks(calendar[k]):
            k += 1
            continue
        r = reading(h, c, k)
        if not (r and r['signal']):
            k += 1
            continue
        L = r['line']
        a, m = L['fromDate'], L['slope']
        j, weeks, back, to = k, 0, None, dest(k)
        while True:
            days[calendar[j]] = to
            j += 1
            if j >= n:
                break
            if j in ends:
                weeks += 1
                if c[j] > (h[a] + m * (j - a)) * (1 + BREAK) or weeks >= MAX_WEEKS:
                    back = j
                    break
        log.append(dict(date=calendar[k], to=to, line=L['at'], touches=L['touches'], back=calendar[back] if back is not None else None))
        k = (back if back is not None else n) + 1
    return days, log


def apply_resist(modes, why, half, days, calendar):
    """New (modes, why, half, held): the rule's holding ({day: 'TLT' | 'CASH'}) and no whipsaw half on its days where
    the plan holds stocks,
    with the switch reasons 'resist' (out) and 'resist-end' (back to what the plan holds)."""
    m, w, hf = dict(modes), dict(why), dict(half or {})
    held, prev = set(), None
    for d in calendar:
        if d not in modes and d not in days:
            continue
        if d in days and m.get(d, 'boost') == 'boost':
            if prev != 'resist':
                w[d] = 'resist'
            m[d] = days[d]
            hf.pop(d, None)
            held.add(d)
            prev = 'resist'
        else:
            if prev == 'resist':
                w[d] = 'resist-end'
            prev = 'plan'
    return m, w, hf, held


def state(bars, calendar, k, held, log, n=6):
    """For the scanner: tonight's reading, whether the rule holds cash for the next session, and its recent stretches."""
    h, c = _series(bars, calendar)
    r = reading(h, c, k) or {}
    if r.get('line'):
        L = dict(r['line'])
        L['fromDate'], L['viaDate'] = calendar[L['fromDate']], calendar[L['viaDate']]
        L['slope'] = round(L['slope'], 3)
        r = dict(r, line=L)
    return dict(r, active=calendar[k] in held, log=list(log)[::-1][:n], touches=TOUCHES, near=NEAR, drop=DROP,
                maxWeeks=MAX_WEEKS, since=START)

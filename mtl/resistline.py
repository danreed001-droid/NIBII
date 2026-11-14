"""The resistance-line exit (rule 22 of the default plan, from the close of Nov 13, 2026, on probation; reworked Nov 14, 2026
from the owner's chart reading): when SPY, near its high and just after a sharp down day, comes back up to a clearly falling
line through its recent lower highs and is turned back there, the plan steps out of stocks until the line breaks: into TLT if
TLT is rising, else cash.

On SPY's daily bars (dividend-adjusted, as the plan reads them):
- swing highs: a session whose high is the highest of the W (3) sessions either side of it (known W sessions later);
- a falling line runs through two swing highs within the LOOK (120) sessions, the first higher than the second and at least
  MIN_SPAN (15) sessions before the test, falling at least MIN_SLOPE (0.03%) of its first top a session (not a flat line),
  and no close since the first one is more than TOL (0.6%) above the line;
- the line counts TOUCHES (4) or more: the swing highs since its start within TOL of it, plus the test day;
- the test, at the close of a week's last session: the high is within TOL of the line (or above it) and the close is under
  it, SPY closes within NEAR (10%) of its highest close of the last 252 sessions, and one of the last DROP_DAYS (10) sessions
  closed DROP (2%) or more down.
The test arms the exit. The exit is the first red candle (a close under its open and under the close before) that is still
under the line, from the test day on, within RED_WAIT (5) sessions; a close more than TOL over the line first calls it off.
Then, where the plan would hold stocks, it holds TLT if TLT is up over the last 3 months (63 sessions) at the exit close,
else cash (nothing bought), from that decision until the first daily close BREAK (0.3%) or more above the line, or after
MAX_WEEKS (2) weeks at the latest. While it is out a new signal can't start. Applied after the no-T-bills swap (so the cash
stays cash) and before the price-break rule and the Fed-day hold. Decided at the close, traded at the next close.

Why: the owner's idea from SPY's chart on Nov 13, 2026 (a falling line from the Oct 6 high touched 4-5 times, the -4.4% day
on Nov 5, SPY back up to the line and a red Friday) and the human-review lesson "act early in a pullback near the highs, not
deep in a bear market"; the clearly falling line, the red candle and the way back on a break are the owner's reading of the
past signals (Nov 14, 2026). Strict test (S&P 500 members as of each date, 0.15% a side): AUDIT below. It fired 4 times since
2000 with the plan in stocks (Mar 2000, Dec 2007, Nov and Dec 2011); the flat Sep 2024 line no longer counts. Tested abroad
(9 markets, the foreign plan): about even (+0.01 / -0.25 points a year on the 6- / 12-month plans) where the first version
lost -0.23 / -0.58; a lower-low condition and re-tests helped the US but lost abroad and were left out. Very few cases:
on probation.

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
BREAK = 0.003
MAX_WEEKS = 2
MIN_SLOPE = 0.0003    # the line falls at least 0.03% of its first top a session (since Nov 14, 2026)
RED_WAIT = 5          # sessions from the test to wait for the red candle (since Nov 14, 2026)
HIGH = 252
START = '2026-11-13'
AUDIT = ('61.5% a year from 2000 vs 60.4% without it, 63.3% vs 61.9% from 2010, 82.0% from 2016 and 122.5% from 2020 '
         '(the same as without it), worst drop -25% both, ahead in 3 years and behind in none (t-stat 1.6); the first '
         'version (Nov 13): 61.7%, behind in 2024')


def _series(bars, calendar, opens=False):
    """(highs, closes) aligned to the calendar, carried over a missing session; with opens=True (highs, closes, opens)."""
    by = {b[0][:10]: b for b in bars}
    h, c, o, lh, lc, lo = [], [], [], None, None, None
    for d in calendar:
        if d in by:
            lh, lc, lo = by[d][2], by[d][4], by[d][1]
        h.append(lh)
        c.append(lc)
        o.append(lo)
    return (h, c, o) if opens else (h, c)


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
    ls = [x for x in lines_at(h, c, k) if x[0] >= touches and -x[3] / h[x[1]] >= MIN_SLOPE]
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
    h, c, o = _series(bars, calendar, opens=True)
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
        # the test arms the exit: out on the first red candle (close under its open and under the close before) still under
        # the line within RED_WAIT sessions; a close more than TOL over the line first calls it off
        fired, open_ = None, False
        for j0 in range(k, min(n, k + RED_WAIT + 1)):
            ln = h[a] + m * (j0 - a)
            if c[j0] is None or o[j0] is None:
                continue
            if c[j0] > ln * (1 + TOL):
                break
            if c[j0] < o[j0] and c[j0] < c[j0 - 1] and c[j0] < ln:
                fired = j0
                break
        else:
            open_ = k + RED_WAIT >= n - 1          # still waiting at the end of the data
        if fired is None:
            if open_:
                log.append(dict(date=calendar[k], armed=True, line=L['at'], touches=L['touches'], back=None))
                break
            k += 1
            continue
        tested, k = k, fired
        j, weeks, back, to = k, 0, None, dest(k)
        while True:
            days[calendar[j]] = to
            j += 1
            if j >= n:
                break
            if c[j] > (h[a] + m * (j - a)) * (1 + BREAK):          # a daily close BREAK over the line: back to the plan
                back = j
                break
            if j in ends:
                weeks += 1
                if weeks >= MAX_WEEKS:
                    back = j
                    break
        log.append(dict(date=calendar[k], test=calendar[tested], to=to, line=L['at'], touches=L['touches'], back=calendar[back] if back is not None else None))
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
    armed = next((x for x in list(log)[::-1] if x.get('armed')), None)
    return dict(r, active=calendar[k] in held, armed=armed['date'] if armed else None, redWait=RED_WAIT,
                log=[x for x in list(log)[::-1] if not x.get('armed')][:n], touches=TOUCHES, near=NEAR, drop=DROP,
                maxWeeks=MAX_WEEKS, since=START, minSlope=MIN_SLOPE, brk=BREAK)

"""The break re-entry rule of Boost + rotation (the default plan, since Oct 27, 2026, on probation): back into stocks when
SPY's downtrend breaks on both time scales after the selling has dried up.

After SPY has been RE_DROP (10%) or more under its highest close of the last RE_HIGH (252) sessions at some close in
the last RE_RECENT (63), two breaks are watched for, each the first close above SPY's latest swing high while that
high is lower than the swing high before it (a downtrend):

1. the weekly break: swing highs of the week closes (RE_WSWING (2) weeks either side, known once the second week
   after has closed);
2. the daily break with fading volume: swing highs of the daily closes (RE_DSWING (3) sessions either side, known
   three sessions later), and SPY's average volume over the RE_FAST (10) sessions before the break under RE_FADE
   (0.8) times its average over the RE_SLOW (50) sessions before those: the selling had dried up.

When both have happened within RE_WIN (21) sessions of each other, the plan holds the Boost list from that decision
day through RE_HOLD - 1 (20) sessions later, whatever the rotation, the lower-high exit, the whipsaw switch, the
narrow-market cash week or no-T-bills would hold (the price-break rule, applied after it, can still send it to the
haven). A new signal needs more than RE_WIN sessions without one. Decided at the close, traded at the next close,
like the rest of the plan.

Backtests (Oct 25, 2026, S&P 500 members at each date, 0.15% per side): 45.8% a year from 2000 vs 44.5% without it,
48.3% vs 47.1% from 2010, 57.6% vs 54.6% from 2016, 88.9% vs 83.2% from 2020, worst drop the same from every start
(-29%, -24%, -23%, -23%). It fired 7 times since 2000 (Jun 2000, Jan 2002, Aug 2010, May 2018, Feb 2019, May 2020,
Jul 2022), so a few trades make the gain. Windows of 10 or 42 sessions and a 0.9 fading cut-off gave about the same.
Abroad (10 markets plus China, the local index in SPY's place, volume = the median of the stocks' own ratios) it was
+0.25 points a year on average, ahead in 6 markets and behind in 3, but Japan's worst drop went from -47% to -62%.
The daily break alone (with fading volume) bought back in on Aug 28, 2008, two weeks before Lehman, and cost 12
points of worst drop; the weekly break kept that out. It was designed after looking at that failure on the same
history, from many re-entry signals tried: treat it as on probation."""
from datetime import date

RE_DROP = 0.10      # SPY this far under its RE_HIGH-session high close ...
RE_HIGH = 252
RE_RECENT = 63      # ... at some close in the last RE_RECENT sessions
RE_DSWING = 3       # daily swing highs: closes this many sessions either side
RE_WSWING = 2       # weekly swing highs: week closes this many weeks either side
RE_FAST = 10        # fading volume: the RE_FAST sessions before the break ...
RE_SLOW = 50        # ... against the RE_SLOW sessions before those
RE_FADE = 0.8
RE_WIN = 21         # the two breaks within this many sessions
RE_HOLD = 21        # decision days in stocks from the signal on (the signal day included)


def _week_ends(calendar, last_is_end=True):
    """Indices of each ISO week's last session; the calendar's last day counts only with last_is_end."""
    out = []
    for k in range(len(calendar)):
        if k + 1 == len(calendar):
            if last_is_end:
                out.append(k)
        elif date.fromisoformat(calendar[k + 1]).isocalendar()[:2] != date.fromisoformat(calendar[k]).isocalendar()[:2]:
            out.append(k)
    return out


def _breaks(c, deep, sw):
    """Indices k of the first close above the latest swing high when that high is below the one before.
    sw = [(index the swing is known from, price)], in order."""
    out, j, used = [], 0, None
    for k in range(1, len(c)):
        while j < len(sw) and sw[j][0] <= k:
            j += 1
        if j < 2 or c[k] is None or c[k - 1] is None:
            continue
        h1, h2 = sw[j - 2][1], sw[j - 1][1]
        if h2 < h1 and c[k] > h2 and c[k - 1] <= h2 and deep[k] and used != j - 1:
            out.append(k)
            used = j - 1
    return out


def _avg(v, a, b):
    xs = [x for x in v[max(0, a):b] if x]
    return sum(xs) / len(xs) if xs else None


def readings(closes, volumes, calendar, last_is_end=True):
    """dict(weekly=[indices], daily=[indices with fading volume], dailyAll=[all daily breaks], fade=[ratio or None
    per index], deep=[bool per index]) from SPY's {date: close} and {date: volume} on `calendar`. last_is_end: whether
    the calendar's last day closes a week (False on a live run before Friday's close)."""
    K = len(calendar)
    c, last = [], None
    for d in calendar:
        last = closes.get(d) or last
        c.append(last)
    v = [volumes.get(d) for d in calendar]
    hi, deep = [], []
    for k in range(K):
        w = [x for x in c[max(0, k - RE_HIGH + 1):k + 1] if x]
        hi.append(max(w) if w else None)
    dd = [c[k] / hi[k] - 1 if c[k] and hi[k] else 0.0 for k in range(K)]
    deep = [min(dd[max(0, k - RE_RECENT + 1):k + 1]) <= -RE_DROP for k in range(K)]
    n = RE_DSWING
    dsw = [(i + n, c[i]) for i in range(n, K - n) if c[i] is not None and None not in c[i - n:i + n + 1]
           and c[i] == max(c[i - n:i + n + 1])]
    wk = _week_ends(calendar, last_is_end)
    wc = [c[k] for k in wk]
    m = RE_WSWING
    wsw = [(wk[j + m], wc[j]) for j in range(m, len(wk) - m) if None not in wc[j - m:j + m + 1] and wc[j] == max(wc[j - m:j + m + 1])]
    fade = []
    for k in range(K):
        a, b = _avg(v, k - RE_FAST, k), _avg(v, k - RE_FAST - RE_SLOW, k - RE_FAST)
        fade.append(a / b if a is not None and b else None)
    dall = _breaks(c, deep, dsw)
    return dict(weekly=_breaks(c, deep, wsw), dailyAll=dall,
                daily=[k for k in dall if k >= RE_FAST + RE_SLOW and fade[k] is not None and fade[k] < RE_FADE],
                fade=fade, deep=deep)


def signals(r):
    """Signal indices: the later of a weekly break and a fading-volume daily break within RE_WIN sessions of each
    other, at most one per RE_WIN sessions."""
    dk, wk = set(r['daily']), set(r['weekly'])
    out, last = [], -10 ** 9
    for k in range(len(r['deep'])):
        hit = (k in dk and any(k - RE_WIN < i <= k for i in wk)) or (k in wk and any(k - RE_WIN < i <= k for i in dk))
        if not hit:
            continue
        if k - last > RE_WIN:
            out.append(k)
        last = k
    return out


def reentry_days(closes, volumes, calendar, start, last_is_end=True):
    """(days, signal dates): the decision days from `start` on which the rule holds stocks."""
    r = readings(closes, volumes, calendar, last_is_end)
    days, sig, until = set(), [], -1
    for k in signals(r):
        if calendar[k] < start:
            continue
        sig.append(calendar[k])
        until = max(until, k + RE_HOLD - 1)
        days.update(calendar[j] for j in range(k, min(len(calendar), k + RE_HOLD)))
    return days, sig


def apply_reentry(modes, why, half, days, calendar):
    """New (modes, why, half, held): the Boost list (and no whipsaw half) on the rule's days, with the switch reasons
    'reentry' (into stocks) and 'reentry-end' (back to what the plan holds); held = the days it changed the holding."""
    m, w, h = dict(modes), dict(why), dict(half or {})
    held, prev = set(), None
    for d in calendar:
        if d not in modes and d not in days:
            continue
        if d in days:
            if m.get(d, 'boost') != 'boost' or d in h:
                if prev != 'reentry':
                    w[d] = 'reentry'
                m[d] = 'boost'
                h.pop(d, None)
                held.add(d)
                prev = 'reentry'
            else:
                prev = 'plan'
        else:
            if prev == 'reentry' and m.get(d, 'boost') != 'boost':
                w[d] = 'reentry-end'
            prev = 'plan'
    return m, w, h, held


def reentry_state(closes, volumes, calendar, k, held, sig, last_is_end=True, n=6):
    """For the scanner: tonight's reading (the drop, the latest weekly / daily breaks and fading ratio), whether the
    rule holds stocks for the next session and how many sessions it has left, and the recent signals (newest first)."""
    r = readings(closes, volumes, calendar, last_is_end)
    ks = signals(r)
    on_next = until = None
    for s in ks:
        if s <= k < s + RE_HOLD:
            until = s + RE_HOLD - 1 - k   # decision days after tonight still covered
    lw = [i for i in r['weekly'] if i <= k]
    ld = [i for i in r['daily'] if i <= k]
    la = [i for i in r['dailyAll'] if i <= k]
    on_next = until is not None and until >= 1
    return dict(deep=bool(r['deep'][k]), fade=None if r['fade'][k] is None else round(r['fade'][k], 3),
                weekly=calendar[lw[-1]] if lw else None, daily=calendar[ld[-1]] if ld else None,
                dailyAny=calendar[la[-1]] if la else None, onNext=on_next, left=until,
                active=calendar[k] in held, log=list(sig)[::-1][:n], n=len(sig),
                drop=RE_DROP, win=RE_WIN, hold=RE_HOLD, fadeTh=RE_FADE)

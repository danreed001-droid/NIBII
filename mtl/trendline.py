"""SPY trendline watch (information only, not traded).

A rising support line on SPY's weekly chart, drawn the way a chartist would:

1. Through two weekly swing lows (each the lowest of the TL_SWING = 4 weeks either side), the later one among
   the last two swing lows and higher than the first, at least TL_SPAN = 26 weeks (6 months) apart.
2. No weekly low under the line between them (0.5% slack).
3. Touched 3 or 4 times about evenly: a touch is a week whose low is the lowest of the 2 weeks either side and
   sits within 1% above the line (0.5% under), at least 3 weeks after the previous touch. The touches start at
   the line's first point and reach its second, span 6 months or more, and the shortest gap between them is at
   least half the longest.

The newest line that qualifies (looking back TL_LOOK = 1100 sessions, about 4.5 years) is the one watched; the
warning fires on the first close under it and stays on for TL_DAYS = 10 sessions. A line breaks once.

Audit (Oct 13, 2026, as a two-week step out of stocks on top of the plan, into the stronger of gold / bonds or
cash, then back to whatever the plan holds): the line fired 5 times since 2000 (Sep 2000, Oct 2014, Oct 2018, Jun 2021, Feb 2025) and made 36.7% a
year from 2000 against 37.0% for the plan (36.2% vs 36.5% once the cash week read its full history, Oct 14; 37.4% vs 37.8% with the rebound rule), 38.1% vs
38.0% from 2010 (39.3% vs 39.2%), 45.8% vs 47.0% from 2016 (46.1% vs 47.3%) and 67.3% vs 67.6% from 2020 (worst
drops the same, except -25% vs -23% from 2016). It caught October 2014 (that year +11.5%
instead of -3.6%) but cost 2000 and 2018; stepping out again when SPY broke the same line a second time did
worse (35.8% from 2000). Allowing 4 even touches as well as 3 gave the same 5 breaks; 4 touches with no spacing
rule fired 9 times and made 35.8%. Near-parallel two-line channels broke only 2-4 times since 2000 and did no
better. Too few breaks to trust either way, so it is a heads-up, not a trade.

Pure and network-free: bars are [(date, open, high, low, close, ...)] oldest first (dividend-adjusted).
"""
import math
from itertools import combinations

from mtl.rotation import weekly
from mtl.structure import find_swings

TL_SPAN = 26          # weeks between the line's two points, and covered by the touches
TL_TOUCHES = (3, 4)   # touches needed (either count, about evenly spaced)
TL_EVEN = 0.5         # shortest gap between touches at least this share of the longest
TL_SWING = 4          # weeks either side of a swing low (the line's points)
TL_TOUCH_SWING = 2    # weeks either side of a touch
TL_TOL = 0.01         # a touch sits within 1% above the line
TL_SLACK = 0.005      # ... or 0.5% under it; no weekly low further under between the two points
TL_GAP = 3            # weeks between touches
TL_LOOK = 1100        # daily bars the weekly chart is read from
TL_DAYS = 10          # sessions the warning stays on after a break


def _line(a, b):
    sl = (math.log(b['price']) - math.log(a['price'])) / (b['i'] - a['i'])
    return lambda i: math.exp(math.log(a['price']) + sl * (i - a['i']))


def _even(hits, k, first, last, span=TL_SPAN, even=TL_EVEN):
    """k touches starting at `first`, reaching `last`, spanning `span`+ weeks, gaps about equal; or None."""
    for c in combinations(hits, k):
        if c[0] != first or c[-1] < last or c[-1] - c[0] < span:
            continue
        g = [c[j + 1] - c[j] for j in range(k - 1)]
        if min(g) >= even * max(g):
            return list(c)
    return None


def find_line(wk):
    """The newest qualifying rising line on weekly bars wk, or None:
    dict(a=(date, price), b=(date, price), touches=[(date, low), ...], level=line at the last week)."""
    lows = [s for s in find_swings(wk, n=TL_SWING) if s['type'] == 'low']
    now = len(wk) - 1
    n2 = TL_TOUCH_SWING
    loc = [q for q in range(len(wk) - 1) if wk[q][3] <= min(b[3] for b in wk[max(0, q - n2):q + n2 + 1])]
    for b in reversed(lows[-2:]):
        for a in reversed(lows[:lows.index(b)]):
            if b['i'] - a['i'] < TL_SPAN or a['price'] >= b['price']:
                continue
            f = _line(a, b)
            if not all(wk[q][3] >= f(q) * (1 - TL_SLACK) for q in range(a['i'] + 1, b['i'])):
                continue
            hits, prev = [], -99
            for q in loc:
                if a['i'] <= q < now and f(q) * (1 - TL_SLACK) <= wk[q][3] <= f(q) * (1 + TL_TOL) and q - prev >= TL_GAP:
                    hits.append(q)
                    prev = q
            pick = None
            for k in TL_TOUCHES:
                pick = pick or _even(hits, k, a['i'], b['i'])
            if pick:
                return dict(a=(a['ts'][:10], a['price']), b=(b['ts'][:10], b['price']),
                            touches=[(wk[q][0][:10], wk[q][3]) for q in pick], level=f(now))
    return None


def line_at(daily, k):
    """The line read at session k's close (daily bars up to and including k), or None."""
    return find_line(weekly(daily[max(0, k + 1 - TL_LOOK):k + 1]))


def breaks(daily, start=0):
    """[(session index, line)] for each first close under a line, scanning sessions start..end."""
    out, seen = [], set()
    for k in range(start, len(daily)):
        ln = line_at(daily, k)
        if ln and daily[k][4] < ln['level'] and (ln['a'][0], ln['b'][0]) not in seen:
            seen.add((ln['a'][0], ln['b'][0]))
            out.append((k, ln))
    return out


def trendline_state(daily, k=None):
    """The dashboard reading at session k (default the last): the line watched now, the last break and whether
    the warning is on (a break within the last TL_DAYS sessions). Scans back TL_LOOK sessions so a line that
    already broke is not counted again."""
    k = len(daily) - 1 if k is None else k
    rd = lambda p: [p[0], round(p[1], 2)]
    br = breaks(daily[:k + 1], start=max(0, k + 1 - TL_LOOK))
    ln = line_at(daily, k)
    close = daily[k][4]
    out = dict(on=False, close=round(close, 2), span=TL_SPAN, touchesNeeded=list(TL_TOUCHES), days=TL_DAYS,
               line=None, last=None, log=[[daily[i][0][:10], rd(l_['a']), rd(l_['b']), round(l_['level'], 2)] for i, l_ in br[-6:]][::-1])
    if ln:
        out['line'] = dict(a=rd(ln['a']), b=rd(ln['b']), touches=[rd(t) for t in ln['touches']], level=round(ln['level'], 2),
                           gap=round(close / ln['level'] - 1, 4))
    if br:
        i, l_ = br[-1]
        out['last'] = dict(date=daily[i][0][:10], a=rd(l_['a']), b=rd(l_['b']), touches=[rd(t) for t in l_['touches']],
                           level=round(l_['level'], 2), close=round(daily[i][4], 2), ago=k - i)
        out['on'] = k - i < TL_DAYS
    return out

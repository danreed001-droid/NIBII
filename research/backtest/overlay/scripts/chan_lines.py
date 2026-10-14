"""Rising channel on weekly bars: a support line through two swing lows and a resistance line through two swing
highs, each spanning at least `span` weeks, of similar length (the shorter at least `ratio` of the longer), over
mostly the same weeks, with the resistance line above the support line. Used by the harness and the chart page."""
import math
import os
import sys
sys.path.insert(0, os.environ.get('NIBII_REPO', '/home/user/NIBII'))
from mtl.structure import find_swings


def _line(a, b):
    sl = (math.log(b['price']) - math.log(a['price'])) / (b['i'] - a['i'])
    return lambda i: math.exp(math.log(a['price']) + sl * (i - a['i']))


def _pairs(sw, bs, span, kind, slack):
    """Rising lines through two swings of `kind` ('low' / 'high') at least `span` weeks apart, the later one among the
    last two swings, with no weekly low under (or high over) the line between them; most recent first."""
    pts = [x for x in sw if x['type'] == kind]
    out = []
    for b in reversed(pts[-2:]):
        for a in reversed(pts[:pts.index(b)]):
            if b['i'] - a['i'] < span or a['price'] >= b['price']:
                continue
            f = _line(a, b)
            if kind == 'low':
                ok = all(bs[q][3] >= f(q) * (1 - slack) for q in range(a['i'] + 1, b['i']))
            else:
                ok = all(bs[q][2] <= f(q) * (1 + slack) for q in range(a['i'] + 1, b['i']))
            if ok:
                out.append((a, b, f))
    return out


def find_channel(bs, span, n=4, ratio=0.66, slack=0.005, overlap=0.5, par=0.0, ovl=0.0, touches=0, even=0.5, tol=0.01):
    """The most recent rising channel in weekly bars bs [(date, open, high, low, close)], or None:
    dict(lower=(a, b), upper=(a, b), low_now, high_now) with the lines projected to the last bar."""
    sw = find_swings(bs, n=n)
    now = len(bs) - 1
    loc = None
    ups = _pairs(sw, bs, span, 'high', slack)
    if not ups:
        return None
    for la, lb, fl in _pairs(sw, bs, span, 'low', slack):
        sl_ = lb['i'] - la['i']
        for ha, hb, fh in ups:
            su = hb['i'] - ha['i']
            if min(sl_, su) < ratio * max(sl_, su):
                continue
            ov = min(lb['i'], hb['i']) - max(la['i'], ha['i'])
            if ov < overlap * min(sl_, su) or ov < ovl * max(sl_, su):
                continue
            mid = (max(la['i'], ha['i']) + min(lb['i'], hb['i'])) / 2
            if fh(mid) <= fl(mid) or fh(now) <= fl(now):
                continue
            if par:
                # roughly parallel: the flatter line's slope (log price a week) at least `par` of the steeper one's
                s_l = math.log(lb['price'] / la['price']) / sl_
                s_u = math.log(hb['price'] / ha['price']) / su
                if min(s_l, s_u) < par * max(s_l, s_u):
                    continue
            pick = None
            if touches:
                loc = loc if loc is not None else _local_lows(bs)
                pick = _even(_touches(bs, fl, la['i'], loc, tol, slack), touches, even, span, la['i'], lb['i'])
                if not pick:
                    continue
            return dict(lower=(la, lb), upper=(ha, hb), low_now=fl(now), high_now=fh(now), touches=pick)
    return None



def _local_lows(bs, tn=2):
    """Weeks whose low is the lowest of the tn weeks either side (the last week left out)."""
    return [q for q in range(len(bs) - 1) if bs[q][3] <= min(b_[3] for b_ in bs[max(0, q - tn):q + tn + 1])]


def _touches(bs, f, start, loc, tol=0.01, slack=0.005, gapw=3):
    """Local lows from `start` to last week sitting within tol above the line f (slack under), gapw+ weeks apart."""
    hits, last = [], -99
    for q in loc:
        if q < start or q >= len(bs) - 1:
            continue
        if f(q) * (1 - slack) <= bs[q][3] <= f(q) * (1 + tol) and q - last >= gapw:
            hits.append(q)
            last = q
    return hits


def _even(hits, k, even, span, first=None, last=None):
    """k of the touches spanning `span`+ weeks with the gaps between them close to equal (shortest gap at least
    `even` of the longest), starting at the line's first point and reaching its second; returns the weeks or None."""
    from itertools import combinations
    for c in combinations(hits, k):
        if c[-1] - c[0] < span or (first is not None and c[0] != first) or (last is not None and c[-1] < last):
            continue
        g = [c[j + 1] - c[j] for j in range(k - 1)]
        if min(g) >= even * max(g):
            return list(c)
    return None


def find_touchline(bs, span, touches=3, even=0.5, n=4, tn=2, tol=0.01, slack=0.005, gapw=3):
    """The most recent rising support line through two weekly swing lows at least `span` weeks apart (the later one
    among the last two swing lows), no weekly low under it between them (slack), touched `touches`+ times about evenly
    (see _even) from the first point to last week. dict(lower=(a, b), low_now, touches) or None."""
    sw = find_swings(bs, n=n)
    lows = [x for x in sw if x['type'] == 'low']
    now = len(bs) - 1
    loc = _local_lows(bs, tn)
    for b in reversed(lows[-2:]):
        for a in reversed(lows[:lows.index(b)]):
            if b['i'] - a['i'] < span or a['price'] >= b['price']:
                continue
            f = _line(a, b)
            if not all(bs[q][3] >= f(q) * (1 - slack) for q in range(a['i'] + 1, b['i'])):
                continue
            hits = _touches(bs, f, a['i'], loc, tol, slack, gapw)
            pick = None
            for k in (touches if isinstance(touches, (tuple, list)) else (touches,)):
                pick = pick or _even(hits, k, even, span, a['i'], b['i'])
            if pick:
                return dict(lower=(a, b), low_now=f(now), touches=pick)
    return None

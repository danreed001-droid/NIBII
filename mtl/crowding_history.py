"""What followed speculator crowding, market by market (information only, for the crowding gauge; mtl/crowding.py).

Four reads, each from every weekly CFTC report since 2000 (when the futures price histories start), measured from the
close of the publication Friday (the Tuesday report + 3 days) over the next 1, 3 and 6 months (21, 63, 126 sessions):
  long / short          while crowded: each crowded spell (weeks in the top / bottom 10% of the 3-year range less than
                        9 weeks apart) counted once, its weeks' moves averaged
  exitLong / exitShort  after a long spell ends: the second straight week back out of the zone (known that week) after
                        a spell spanning 8+ weeks (a single week out doesn't end a spell); exits counted once
Each read gives how many episodes beat the market's normal (median) move over the same horizon, the typical (median)
episode move, and a sign test: the chance of that many beating the median, or fewer, by luck if each were a coin flip.

Research (Oct 27, 2026): counted this way, only crowded SHORT spells showed a pattern beyond luck: Nasdaq-100 futures
(10 of 11 beat normal at 3 months) and 30-year Treasuries (10 of 11 at 3 and 6 months). Crowded long was not a reliable
sell warning, and no exit read passed. A strict plan test of holding bonds as the haven while Treasuries are crowded
short gave 45.6% a year from 2000 (30-year) against the plan's 45.8%, so it stays information.

Pure and network-free: positions and prices in, a dict for data/crowding_history.json out."""
from bisect import bisect_left
from datetime import date, timedelta
from math import comb

from mtl.crowding import CROWDED, MARKETS, WINDOW

H = (('1', 21), ('3', 63), ('6', 126))
SINCE = '2000-01-01'
SPAN = 8            # weeks: a "long spell" for the exit reads
GAP_DAYS = 63       # crowded weeks less than 9 weeks apart are one spell; exits closer than that count once


def pcts(series, window=WINDOW):
    """[(week, place in its 3-year range)] for every week with a full window, as the gauge reads it."""
    ds = sorted(series)
    nets = [series[d][0] for d in ds]
    out = []
    for i in range(window, len(ds)):
        w = nets[i - window:i + 1]
        lo, hi = min(w), max(w)
        out.append((ds[i], (nets[i] - lo) / (hi - lo) if hi > lo else 0.5))
    return out


def forward(prices, week):
    """{'1': move, '3': ..., '6': ...} from the close of the session on or after the publication Friday; None when
    the price history doesn't reach that far back, a horizon left out until it has passed."""
    cal = prices['cal']
    k = bisect_left(cal, (date.fromisoformat(week) + timedelta(days=3)).isoformat())
    if k == 0 or k >= len(cal):
        return None
    px = prices['px']
    return {lab: px[k + h] / px[k] - 1 for lab, h in H if k + h < len(cal)}


def sign_p(k, n):
    """Two-sided sign test: the chance of k or more (or as few) of n beating a coin flip's 50%."""
    if not n:
        return 1.0
    lo = min(k, n - k)
    return min(1.0, 2 * sum(comb(n, i) for i in range(lo + 1)) / 2 ** n)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2) if n else None


def spells(rows, side, crowded=CROWDED):
    """Crowded weeks grouped into spells: [[week, ...], ...]."""
    inz = [w for w, p in rows if w >= SINCE and ((p >= crowded) if side == 'long' else (p <= 1 - crowded))]
    out, last = [], None
    for w in inz:
        d = date.fromisoformat(w)
        if last is None or (d - last).days > GAP_DAYS:
            out.append([w])
        else:
            out[-1].append(w)
        last = d
    return out


def exits(rows, side, span=SPAN, crowded=CROWDED):
    """[week]: the second straight week out of the zone after a spell spanning `span`+ weeks (one week out doesn't end
    a spell), known that week; exits closer than GAP_DAYS to the last counted one are skipped."""
    out, first, lastin, outrun, last = [], None, None, 0, None
    for i, (w, p) in enumerate(rows):
        if (p >= crowded) if side == 'long' else (p <= 1 - crowded):
            first = i if first is None else first
            lastin, outrun = i, 0
        elif first is not None:
            outrun += 1
            if outrun == 2:
                if lastin - first + 1 >= span and w >= SINCE:
                    d = date.fromisoformat(w)
                    if last is None or (d - last).days > GAP_DAYS:
                        out.append(w)
                        last = d
                first, outrun = None, 0
    return out


def _read(groups, prices, normal):
    """One read: per horizon, episodes that beat the normal move, the typical episode move and the sign test."""
    moves = []
    for g in groups:
        fs = [f for f in (forward(prices, w) for w in g) if f]
        moves.append({lab: sum(f[lab] for f in fs if lab in f) / n for lab, _ in H
                      if (n := sum(1 for f in fs if lab in f))})
    out = dict(n=len(groups))
    for lab, _ in H:
        xs = [m[lab] for m in moves if lab in m]
        if not xs or normal.get(lab) is None:
            out[lab] = None
            continue
        k = sum(x > normal[lab] for x in xs)
        out[lab] = dict(n=len(xs), beat=k, typ=round(_median(xs), 4), p=round(sign_p(k, len(xs)), 3))
    return out


def market(series, prices):
    """All four reads for one market, with its normal (median) moves and where it stands now."""
    rows = pcts(series)
    alls = [f for f in (forward(prices, w) for w, _ in rows if w >= SINCE) if f]
    normal = {lab: (round(m, 4) if (m := _median([f[lab] for f in alls if lab in f])) is not None else None) for lab, _ in H}
    out = dict(normal=normal, weeks=len(alls))
    for side in ('long', 'short'):
        out[side] = _read(spells(rows, side), prices, normal)
        out['exit' + side.capitalize()] = _read([[w] for w in exits(rows, side)], prices, normal)
    return out


def build(positions, prices, asof=None):
    """{asOf, since, span, markets: {name: market()}} for the markets with positions and prices. positions: the merged
    CFTC history (mtl/crowding.merge); prices: {name: {date: close}}."""
    out = {}
    for name in MARKETS.values():
        s, p = positions.get(name), prices.get(name)
        if s and p and len(s) > WINDOW:
            cal = sorted(p)
            out[name] = market(s, dict(cal=cal, px=[p[d] for d in cal]))
    return dict(asOf=asof, since=SINCE, span=SPAN, markets=out)

"""Market stress card (information only): sharp moves across asset classes, the drop study's warning signs.

Sharp moves: how many of 12 asset classes (the S&P 500, long and medium Treasuries, gold, oil, copper, the dollar index
and five major currencies) made a sharp 5-day move: more than twice its normal size, judged by its daily swings over
the 63 sessions before. Since 2004, 3 or more moved sharply on 6.9% of days (6 or more on 1.1%). After those days a
further 5% fall in the S&P 500 within a month came 23% of the time (38% after 6 or more) against 16% for all days,
but the month ahead also averaged +1.2% (+2.9%) against +0.8%: big swings both ways, and on a third of those days
(nearly two thirds at 6 or more) the index was already 10%+ under its high. Tested as a rule (Oct 25, 2026): cash
for 5-21 days when 3 to 6 of them moved sharply lost money from every start year in all 24 versions.

The two warning sets come from the study of all 99 drops of 5% or more in the S&P 500 since 2000 (Oct 26, 2026):
- calm market (the index within 3% of its 52-week high): small caps, the equal-weight index and copper (against
  gold) each in the weakest fifth of their 3-month showing against the index. Since 2013 a 5% fall followed within a
  month after 0.7% of calm days with none on, 5.1% with one, 18.1% with two and 22.3% with all three (9.7% of all
  calm days). Thresholds were set on 2000-2012.
- in a drop (5%+ under the high of the last 63 sessions): the index under its 200-day average, junk bonds 2%+ behind
  Treasuries over a month, and a fall of 5% within 5 sessions of the high. With 0-1 of them on, 13 of 58 drops
  went on to 10%; with 2-3, 22 of 41.
Both were tested as rules on the plan and lost money (Strategy Test Log, ideas 71-74).

Pure and network-free: series are {date: close}."""
import math
from bisect import bisect_right

DOMINOES = [('SPY', 'S&P 500'), ('TLT', 'Long Treasuries'), ('IEF', '7-10 yr Treasuries'), ('GLD', 'Gold'),
            ('CL=F', 'Oil'), ('HG=F', 'Copper'), ('DX-Y.NYB', 'Dollar index'), ('EURUSD=X', 'Euro'),
            ('JPY=X', 'Yen'), ('CHF=X', 'Swiss franc'), ('GBPUSD=X', 'Pound'), ('AUDUSD=X', 'Australian dollar')]
INVERT = {'JPY=X', 'CHF=X'}   # quoted per dollar: flip so up = the currency stronger
SHARP = 2.0                   # a 5-day move over twice the normal 5-day swing
NORM = 63                     # sessions the normal swing is read from, before the 5-day window
NARROW = dict(small=-0.0135, ew=-0.0007, cg=-0.0427)   # weakest fifth over 2000-2012 (63-session relative moves)
NARROW_ODDS = {0: 0.007, 1: 0.051, 2: 0.181, 3: 0.223}  # 5% fall within a month, calm days since 2013
NARROW_BASE = 0.097
DEEP_ODDS = ((13, 58), (22, 41))                         # drops reaching 10%: 0-1 signs, 2-3 signs
DROP_FAMILIES = {   # trigger family -> (drops since 2000, median depth, median sessions back to the old high)
    'Banks & credit': (17, -0.114, 184), 'Fed & inflation': (19, -0.075, 37), 'Economy & earnings': (20, -0.072, 14),
    'Shocks abroad': (15, -0.081, 25), 'Pandemic & disaster': (9, -0.075, 26), 'War & terror': (8, -0.091, 66),
    'Tariffs & politics': (8, -0.075, 51), 'Oil': (3, -0.133, 80)}
EVENT_FAMILY = {   # event type on the events list -> trigger family
    'Fed hike / hawkish': 'Fed & inflation', 'Inflation / yields': 'Fed & inflation', 'Inflation tops 4%': 'Fed & inflation',
    'Bank / credit failure': 'Banks & credit', 'Credit cracking': 'Banks & credit',
    'Recession signal': 'Economy & earnings', 'Yield curve inverts': 'Economy & earnings',
    'War / terror': 'War & terror', 'Trade war / China': 'Tariffs & politics', 'Debt crisis / shutdown': 'Tariffs & politics',
    'Pandemic / disaster': 'Pandemic & disaster', 'Oil shock': 'Oil', 'Oil up 50% in a year': 'Oil'}


def page_tickers():
    """The extra price series the Market stress page needs: the 12 sharp-move assets, the crowding charts' prices,
    small caps and gold futures, less those the scan already reads with the benchmark and haven prices. Kept here,
    not as a scanner setting, so a page change never alters the paper record's rule fingerprint (mtl/paper.py)."""
    from mtl import crowding
    return sorted(({t for t, _ in DOMINOES} | set(crowding.PRICE.values()) | {'IWM', 'GC=F'})
                  - {'SPY', 'TLT', 'IEF', 'GLD', 'QQQ'})


def _upto(px, d):
    """(dates, closes) of a {date: close} series up to and including d."""
    ds = sorted(px)
    j = bisect_right(ds, d)
    return ds[:j], [px[x] for x in ds[:j]]


def z5(closes):
    """The last 5-session log move over its normal 5-session swing, or None with too little history."""
    if len(closes) < NORM + 6:
        return None
    w = closes[-(NORM + 6):]
    if min(w) <= 0:   # oil futures settled below zero in April 2020
        return None
    r = [math.log(w[i] / w[i - 1]) for i in range(1, NORM + 1)]
    m = sum(r) / len(r)
    sd = (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5
    return math.log(w[-1] / w[-6]) / (sd * 5 ** 0.5) if sd > 0 else None


def dominoes(series, d, sharp=SHARP):
    """dict(n=sharp count, of=assets read, moves=[[name, z, % move over 5 sessions]...] for the sharp ones, biggest first)."""
    moves, read = [], 0
    for t, name in DOMINOES:
        px = series.get(t)
        if not px:
            continue
        _, c = _upto(px, d)
        z = z5(c)
        if z is None:
            continue
        read += 1
        if t in INVERT:
            z = -z
        if abs(z) >= sharp:
            mv = c[-1] / c[-6] - 1
            moves.append([name, round(z, 2), round(1 / (1 + mv) - 1 if t in INVERT else mv, 4)])
    moves.sort(key=lambda m: -abs(m[1]))
    return dict(n=len(moves), of=read, moves=moves)


def _rel(a, b, n):
    """a's n-session move minus b's, on their shared last n+1 closes, or None."""
    if len(a) <= n or len(b) <= n:
        return None
    return (a[-1] / a[-1 - n] - 1) - (b[-1] / b[-1 - n] - 1)


def warnings(spy, d, rsp=None, iwm=None, copper=None, gold=None, hyg=None, ief=None):
    """The drop study's readings at d: where the index is against its highs, then either the calm-market signs or the
    in-a-drop signs. Every input is {date: close}; missing ones read as off."""
    ds, c = _upto(spy, d)
    if len(c) < 253:
        return None
    hi52, now = max(c[-252:]), c[-1]
    w63 = c[-63:]
    k_hi = len(c) - 63 + max(range(63), key=lambda i: w63[i])
    drop = now / c[k_hi] - 1
    out = dict(date=ds[-1], offHigh=round(now / hi52 - 1, 4), drop=round(drop, 4), peak=ds[k_hi])
    c_ = lambda s: _upto(s, d)[1] if s else []
    if drop <= -0.05:
        first = next(k for k in range(k_hi, len(c)) if c[k] / c[k_hi] - 1 <= -0.05)
        below200 = now < sum(c[-200:]) / 200
        cr = _rel(c_(hyg), c_(ief), 21)
        signs = dict(below200=below200, credit=cr is not None and cr <= -0.02, fast=first - k_hi <= 5)
        n = sum(signs.values())
        hit, of = DEEP_ODDS[1 if n >= 2 else 0]
        out.update(mode='drop', signs=signs, n=n, odds=[hit, of], credit=None if cr is None else round(cr, 4))
    else:
        calm = now >= hi52 * 0.97
        small, ew = _rel(c_(iwm), c, 63), _rel(c_(rsp), c, 63)
        cp, gp = c_(copper), c_(gold)
        cg = (cp[-1] / gp[-1]) / (cp[-64] / gp[-64]) - 1 if len(cp) > 63 and len(gp) > 63 else None
        vals = dict(small=small, ew=ew, cg=cg)
        signs = {k: v is not None and v <= NARROW[k] for k, v in vals.items()}
        n = sum(signs.values())
        out.update(mode='calm' if calm else 'between', signs=signs, n=n, odds=NARROW_ODDS[n] if calm else None,
                   base=NARROW_BASE, vals={k: None if v is None else round(v, 4) for k, v in vals.items()})
    return out


def news_context(events, today, days=21):
    """Trigger families named by events in the last `days` (newest first) with how deep past drops they set off went:
    [[family, [event texts], drops, median depth, median sessions back]]."""
    from datetime import date, timedelta
    cut = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    fam = {}
    for e in sorted(events, key=lambda e: e['d'], reverse=True):
        f = EVENT_FAMILY.get(e.get('type'))
        if f and cut < e['d'] <= today:
            fam.setdefault(f, []).append(f"{e['what']} ({e['d']})")
    return [[f, ev[:3], *DROP_FAMILIES[f]] for f, ev in fam.items()]

"""The market chronograph for the scanner page (information only, not a rule): where the S&P 500, gold, long bonds and
crude oil each sit in their cycle on three time scales, and the market's mood.

- Cycle position: the 14-day RSI (Wilder; on daily closes its 3-day average) for the level and its change (over 5 sessions /
  3 weeks / 2 months) for the direction, as an angle: right = rising, up = strong. Going round clockwise from the lower
  right: turning up (weak, rising) -> rallying (strong, rising) -> rolling over (strong, falling) -> falling (weak, falling).
  Weekly and monthly closes are each week's / month's last session; on a day inside a week or month that day's close stands
  in for the period's.
- Mood: the 20-session returns of the S&P 500 and crude oil minus gold and long bonds, each as a z-score against its last
  252 sessions, averaged (up = stocks and oil rising while gold and bonds fall: good sentiment; down = the fear trade), and
  its change over 5 sessions. The dial's angle: up = good, down = fear, right = improving, left = worsening.

Before the funds existed the series are spliced from proxies (splice): gold futures before GLD (Nov 2004), the Vanguard
long-term Treasury fund before TLT (Jul 2002); the clock reads only percentage moves, so a proxy joined at a common date
changes nothing after it. History from Aug 2000 (gold and crude futures); the monthly hand from about late 2001.

Pure: closes {key: {date: close}} for 'SPY', 'GLD', 'TLT', 'OIL', and a session calendar."""
from datetime import date
from math import atan2, degrees, sqrt

ASSETS = (('SPY', 'S&P 500'), ('GLD', 'Gold'), ('TLT', 'Long bonds'), ('OIL', 'Crude oil'))
PERIOD = 14
DAYS = None        # every session (from the first one with prices)
MOOD_LOOK = 20
MOOD_Z = 252


def _carry(px, cal):
    out, last = [], None
    for d in cal:
        v = px.get(d)
        last = v if v else last
        out.append(last)
    return out


def rsi(closes, p=PERIOD):
    """Wilder RSI per point (None for the first p)."""
    out = [None] * len(closes)
    if len(closes) <= p:
        return out
    g = l = 0.0
    for i in range(1, p + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    g, l = g / p, l / p
    out[p] = 100 - 100 / (1 + g / l) if l else 100.0
    for i in range(p + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (p - 1) + max(d, 0)) / p
        l = (l * (p - 1) + max(-d, 0)) / p
        out[i] = 100 - 100 / (1 + g / l) if l else 100.0
    return out


def angle(level, chg):
    """Cycle position in degrees (0-360, counterclockwise from 'rising'): right = rising, up = strong."""
    x = max(-1.3, min(1.3, chg / 25))
    y = max(-1.3, min(1.3, (level - 50) / 30))
    return round(degrees(atan2(y, x)) % 360, 1)


def phase(a):
    return 'rallying' if a < 90 else 'rolling over' if a < 180 else 'falling' if a < 270 else 'turning up'


def splice(primary, proxy):
    """primary's closes, with proxy's (rescaled at the first date both have) before primary starts."""
    primary, proxy = primary or {}, proxy or {}
    if not primary:
        return dict(proxy)
    first = min(primary)
    common = min((d for d in primary if d in proxy), default=None)
    if common is None:
        return dict(primary)
    k = primary[common] / proxy[common]
    out = {d: v * k for d, v in proxy.items() if d < first}
    out.update(primary)
    return out


def _period_key(d, kind):
    y, m, dd = (int(x) for x in d.split('-'))
    if kind == 'w':
        iy, iw, _ = date(y, m, dd).isocalendar()
        return (iy, iw)
    return (y, m)


def _scale_angles(c, cal, idx, kind, back, p=PERIOD):
    """(angles, rsis): the weekly ('w') or monthly ('m') cycle angle and RSI at each session index in idx: the RSI of the
    closed periods' closes with that day's close standing in for its own period, against the RSI `back` closed periods
    earlier."""
    keys = [_period_key(d, kind) for d in cal]
    ends = [i for i in range(len(cal)) if c[i] and (i + 1 == len(cal) or keys[i + 1] != keys[i])]
    C = [c[i] for i in ends]
    n = len(C)
    ag, al, rc = [None] * n, [None] * n, [None] * n      # Wilder averages and RSI after each closed period
    if n > p:
        g = sum(max(C[i] - C[i - 1], 0) for i in range(1, p + 1)) / p
        l_ = sum(max(C[i - 1] - C[i], 0) for i in range(1, p + 1)) / p
        ag[p], al[p] = g, l_
        rc[p] = 100 - 100 / (1 + g / l_) if l_ else 100.0
        for j in range(p + 1, n):
            d = C[j] - C[j - 1]
            g = (g * (p - 1) + max(d, 0)) / p
            l_ = (l_ * (p - 1) + max(-d, 0)) / p
            ag[j], al[j] = g, l_
            rc[j] = 100 - 100 / (1 + g / l_) if l_ else 100.0
    out, lev, j_ptr = [], [], 0
    for k in idx:
        while j_ptr < n and ends[j_ptr] < k:
            j_ptr += 1
        m = j_ptr - (1 if j_ptr > 0 and keys[ends[j_ptr - 1]] == keys[k] else 0)   # closed periods before k's own
        if not c[k] or m - 1 < p or m - back < p or ag[m - 1] is None:
            out.append(None)
            lev.append(None)
            continue
        d = c[k] - C[m - 1]
        g = (ag[m - 1] * (p - 1) + max(d, 0)) / p
        l_ = (al[m - 1] * (p - 1) + max(-d, 0)) / p
        now = 100 - 100 / (1 + g / l_) if l_ else 100.0
        prev = rc[m - back] if m - back < n else None
        out.append(None if prev is None else angle(now, now - prev))
        lev.append(None if prev is None else now)
    return out, lev


def build(closes, calendar, days=DAYS):
    """dict(dates, assets=[dict(key, name, d, w, m, dr, wr, mr)], mood, dmood, mang): cycle angles in whole degrees and the
    RSI behind each (dr: the daily 3-day average; None where there is too little history), from the first session every
    series has a price (or the last `days` sessions)."""
    cal = list(calendar)
    n = len(cal)
    have = [k for k, _ in ASSETS if closes.get(k)] or ['']
    start = next((i for i, d in enumerate(cal) if all((closes.get(k) or {}).get(d) for k in have)), n) if days is None else max(0, n - days)
    idx = list(range(start, n))
    assets = []
    for key, name in ASSETS:
        c = _carry(closes.get(key) or {}, cal)
        if sum(1 for x in c if x) < 400:
            continue
        r = rsi([x or 0.0 for x in c])
        r3 = [None if i < 2 or None in r[i - 2:i + 1] else sum(r[i - 2:i + 1]) / 3 for i in range(n)]
        d_ = [None if r3[k] is None or k < 5 or r3[k - 5] is None else angle(r3[k], r3[k] - r3[k - 5]) for k in idx]
        rd = lambda xs: [None if x is None else int(round(x)) % 360 for x in xs]
        ri = lambda xs: [None if x is None else int(round(x)) for x in xs]
        w_, wr = _scale_angles(c, cal, idx, 'w', 3)
        m_, mr = _scale_angles(c, cal, idx, 'm', 2)
        assets.append(dict(key=key, name=name, d=rd(d_), w=rd(w_), m=rd(m_),
                           dr=ri([None if a is None else r3[k] for a, k in zip(d_, idx)]), wr=ri(wr), mr=ri(mr)))
    mood, dmood, mang = [None] * len(idx), [None] * len(idx), [None] * len(idx)
    if len(assets) == len(ASSETS):
        cs = {a['key']: _carry(closes.get(a['key']) or {}, cal) for a in assets}
        ret = {k: [None if i < MOOD_LOOK or not v[i] or not v[i - MOOD_LOOK] else v[i] / v[i - MOOD_LOOK] - 1 for i in range(n)]
               for k, v in cs.items()}

        zz = {}
        for k_, r_ in ret.items():
            zs, sm, sq, win = [None] * n, 0.0, 0.0, []
            for i in range(n):
                x = r_[i]
                if x is not None:
                    win.append(x); sm += x; sq += x * x
                    if len(win) > MOOD_Z:
                        y = win.pop(0); sm -= y; sq -= y * y
                if x is not None and len(win) >= 120:
                    mu = sm / len(win)
                    var = max(sq / len(win) - mu * mu, 0) * len(win) / (len(win) - 1)
                    zs[i] = (x - mu) / sqrt(var) if var > 0 else 0.0
            zz[k_] = zs
        s_all = {}
        for i in range(n):
            v = [zz[k_][i] for k_ in ('SPY', 'OIL', 'GLD', 'TLT')]
            if None not in v:
                s_all[i] = (v[0] + v[1] - v[2] - v[3]) / 4
        for j, k in enumerate(idx):
            if k in s_all and k - 5 in s_all:
                s, ds = s_all[k], s_all[k] - s_all[k - 5]
                mood[j], dmood[j] = round(s, 2), round(ds, 2)
                mang[j] = int(round(degrees(atan2(max(-2, min(2, s)), max(-2, min(2, ds * 2)))))) % 360
    return dict(dates=[cal[k] for k in idx], assets=assets, mood=mood, dmood=dmood, mang=mang)

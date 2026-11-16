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

Pure: closes {key: {date: close}} for 'SPY', 'GLD', 'TLT', 'OIL', and a session calendar."""
from datetime import date
from math import atan2, degrees, sqrt

ASSETS = (('SPY', 'S&P 500'), ('GLD', 'Gold'), ('TLT', 'Long bonds'), ('OIL', 'Crude oil'))
PERIOD = 14
DAYS = 252
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


def _period_key(d, kind):
    y, m, dd = (int(x) for x in d.split('-'))
    if kind == 'w':
        iy, iw, _ = date(y, m, dd).isocalendar()
        return (iy, iw)
    return (y, m)


def _scale_angles(c, cal, idx, kind, back):
    """The weekly ('w') or monthly ('m') cycle angle at each session index in idx."""
    keys = [_period_key(d, kind) for d in cal]
    ends = [i for i in range(len(cal)) if c[i] and (i + 1 == len(cal) or keys[i + 1] != keys[i])]
    out = []
    for k in idx:
        pts = [c[i] for i in ends if i < k and keys[i] != keys[k]] + [c[k]]   # closed periods, then today's close
        r = rsi(pts)
        if len(r) <= PERIOD + back or r[-1] is None or r[-1 - back] is None:
            out.append(None)
        else:
            out.append(angle(r[-1], r[-1] - r[-1 - back]))
    return out


def build(closes, calendar, days=DAYS):
    """dict(dates, assets=[dict(key, name, d, w, m, rsi)], mood, dmood, mang) for the last `days` sessions."""
    cal = list(calendar)
    n = len(cal)
    idx = list(range(max(0, n - days), n))
    assets = []
    for key, name in ASSETS:
        c = _carry(closes.get(key) or {}, cal)
        if sum(1 for x in c if x) < 400:
            continue
        r = rsi([x or 0.0 for x in c])
        r3 = [None if i < 2 or None in r[i - 2:i + 1] else sum(r[i - 2:i + 1]) / 3 for i in range(n)]
        d_ = [None if r3[k] is None or k < 5 or r3[k - 5] is None else angle(r3[k], r3[k] - r3[k - 5]) for k in idx]
        assets.append(dict(key=key, name=name, d=d_, w=_scale_angles(c, cal, idx, 'w', 3), m=_scale_angles(c, cal, idx, 'm', 2),
                           rsi=[None if r3[k] is None else round(r3[k], 1) for k in idx]))
    mood, dmood, mang = [None] * len(idx), [None] * len(idx), [None] * len(idx)
    if len(assets) == len(ASSETS):
        cs = {a['key']: _carry(closes.get(a['key']) or {}, cal) for a in assets}
        ret = {k: [None if i < MOOD_LOOK or not v[i] or not v[i - MOOD_LOOK] else v[i] / v[i - MOOD_LOOK] - 1 for i in range(n)]
               for k, v in cs.items()}

        def z(k, i):
            w = [x for x in ret[k][max(0, i - MOOD_Z + 1):i + 1] if x is not None]
            if len(w) < 120 or ret[k][i] is None:
                return None
            mu = sum(w) / len(w)
            sd = sqrt(sum((x - mu) ** 2 for x in w) / (len(w) - 1))
            return (ret[k][i] - mu) / sd if sd else 0.0
        s_all = {}
        for i in range(max(0, idx[0] - 10) if idx else 0, n):
            zs = [z(k, i) for k in ('SPY', 'OIL', 'GLD', 'TLT')]
            if None not in zs:
                s_all[i] = (zs[0] + zs[1] - zs[2] - zs[3]) / 4
        for j, k in enumerate(idx):
            if k in s_all and k - 5 in s_all:
                s, ds = s_all[k], s_all[k] - s_all[k - 5]
                mood[j], dmood[j] = round(s, 3), round(ds, 3)
                mang[j] = round(degrees(atan2(max(-2, min(2, s)), max(-2, min(2, ds * 2)))) % 360, 1)
    return dict(dates=[cal[k] for k in idx], assets=assets, mood=mood, dmood=dmood, mang=mang)

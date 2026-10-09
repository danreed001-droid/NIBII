"""Boost + rotation: the Boost 100% stock list, moved out of stocks into long Treasuries
(TLT) or gold (GLD) when the chart says so. Decided at any session's close, traded at
the next session's close.

Two parts, both read from swing structure (mtl.structure: 3-bar swings on daily bars,
2-bar swings on weekly bars, the last two labeled swings for the trend):

1. Rotation. While SPY's daily structure is a downtrend (lower highs and lower lows),
   look for TLT or GLD in a daily uptrend (higher highs and higher lows) whose
   gradient is positive: the line through its last two higher lows, per session,
   divided by its daily volatility (so bonds, gold and stocks compare fairly). The
   steepest one is the candidate. After it has led for CONFIRM sessions (counted on
   days SPY's daily trend is down), switch into it. Leave it, back to the Boost list,
   the day it is no longer in a daily uptrend.

2. Downtrend exit. Out of stocks when SPY's weekly structure is a downtrend whose last
   lower high sits below the 150-day average, SPY closes below the average too, and
   the line through SPY's last two weekly lower lows falls slowly (|slope| / daily
   volatility < SLOW: a grinding bear market, not a crash). While out, hold the
   steepest of TLT / GLD in a daily uptrend (T-bills if neither). Back into the Boost
   list when SPY closes above its 150-day average, or SPY's daily structure turns up
   with higher lows steeper than TLT's and GLD's.

Tested 2000-2026 (stocks in the S&P 500 at the time, 0.15% slippage, 37%/20% tax;
TLT / GLD spliced onto a Treasury fund / gold futures before they existed): 31.0% a year
before tax (20.2% after), worst drop -46%, vs 27.4% (18.1%) and -60% for Boost 100%.
The thresholds were picked on that same history.

Pure and network-free: bars are {ticker: [(date, open, high, low, close), ...]} oldest
first (dividend-adjusted), calendar is the trading days.
"""
import math
from bisect import bisect_right
from datetime import date

from mtl.structure import find_swings, label_structure, trend_state

ROT_ASSETS = ('TLT', 'GLD')
CONFIRM = 15          # sessions a candidate must lead before the switch
SLOW = 0.12           # downtrend exit only when SPY's weekly lower lows fall slower than this
MA = 150              # SPY's average for the downtrend exit and the way back
VOL_LOOK = 63         # sessions of daily returns for the volatility scaling
SWITCH_COST = 0.001   # one full switch (sell everything, buy the other), like run_momentum's 0.05% a side


def weekly(daily):
    """ISO-week bars dated by the week's LAST session (so a swing's date is a real close)."""
    out, key = [], None
    for b in daily:
        k = date.fromisoformat(b[0][:10]).isocalendar()[:2]
        if k != key:
            key = k
            out.append([b[0], b[1], b[2], b[3], b[4]])
        else:
            w = out[-1]
            w[0], w[2], w[3], w[4] = b[0], max(w[2], b[2]), min(w[3], b[3]), b[4]
    return [tuple(w) for w in out]


def _sessions(a, b):
    """Calendar days between two dates, in trading sessions (252 a year)."""
    return max(1.0, (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days * 252 / 365)


def _vol(closes):
    rr = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - VOL_LOOK, len(closes))]
    m = sum(rr) / len(rr)
    return (sum((x - m) ** 2 for x in rr) / (len(rr) - 1)) ** 0.5


class Reader:
    """Structure reads as of a date, cached: daily / weekly labeled swings, trend and gradient."""

    def __init__(self, bars):
        self.bars = {t: [tuple(b) for b in bs] for t, bs in bars.items()}
        self.days = {t: [b[0] for b in bs] for t, bs in self.bars.items()}
        self._lab, self._leg = {}, {}

    def _daily(self, t, d, n):
        j = bisect_right(self.days[t], d)
        return self.bars[t][max(0, j - n):j]

    def labels(self, t, d, tf='d'):
        if (t, d, tf) not in self._lab:
            daily = self._daily(t, d, 900 if tf == 'w' else 320)
            bs = weekly(daily) if tf == 'w' else daily
            self._lab[(t, d, tf)] = label_structure(find_swings(bs, n=2 if tf == 'w' else 3))
        return self._lab[(t, d, tf)]

    def leg(self, t, d, tf='d'):
        """(trend, gradient): gradient = log slope through the last two higher lows (uptrend)
        or lower highs (downtrend), per session, / daily volatility. None when unreadable."""
        if (t, d, tf) not in self._leg:
            daily = self._daily(t, d, 900 if tf == 'w' else 320)
            out = (None, None)
            if len(daily) > 60:
                lab = self.labels(t, d, tf)
                st = trend_state(lab, lookback=2)
                piv = [x for x in lab if x['type'] == ('low' if st == 'uptrend' else 'high')]
                if st in ('uptrend', 'downtrend') and len(piv) >= 2:
                    p0, p1 = piv[-2], piv[-1]
                    g = math.log(p1['price'] / p0['price']) / _sessions(p0['ts'], p1['ts'])
                    sd = _vol([b[4] for b in daily])
                    out = (st, g / sd if sd > 0 else 0.0)
                else:
                    out = (st, None)
            self._leg[(t, d, tf)] = out
        return self._leg[(t, d, tf)]

    def steepest(self, d, assets=ROT_ASSETS, above=None):
        """The asset in a daily uptrend with the steepest positive gradient (> above), or None."""
        best, bv = None, None
        for t in assets:
            st, g = self.leg(t, d)
            if st != 'uptrend' or g is None or g <= 0 or (above is not None and g <= above):
                continue
            if bv is None or g > bv:
                best, bv = t, g
        return best


def rotation_modes(bars, calendar, start, confirm=CONFIRM, slow=SLOW, ma=MA, assets=ROT_ASSETS):
    """(modes, why, reader, state): modes = {decision date: 'boost' | asset | 'BIL'} for
    every session from `start` (decided at that close, traded at the next session's close);
    why = {date: 'rotate' | 'rotate-end' | 'exit' | 'switch' | 'above' | 'steeper'} for the
    days the holding changed; state = the last session's {rot, streak, cand, out}."""
    R = Reader(bars)
    spy = {b[0]: b[4] for b in bars['SPY']}
    closes = [spy.get(d) for d in calendar]
    kidx = {d: i for i, d in enumerate(calendar)}

    def avg(k):
        w = [x for x in closes[max(0, k - ma + 1):k + 1] if x]
        return sum(w) / ma if len(w) == ma else None

    # 1. rotation
    rot, mode, streak, cand_prev = {}, 'boost', 0, None
    for k in range(1, len(calendar)):
        d = calendar[k]
        if d < start:
            continue
        if mode == 'boost':
            sst, sg = R.leg('SPY', d)
            if sst == 'downtrend':
                best = R.steepest(d, assets, above=sg)
                streak = streak + 1 if best and best == cand_prev else (1 if best else 0)
                cand_prev = best
                if best and streak > confirm:
                    mode, streak = best, 0
        elif R.leg(mode, d)[0] != 'uptrend':
            mode = 'boost'
        rot[d] = mode

    # 2. downtrend exit on top
    modes, why, on, prev = {}, {}, False, 'boost'
    for k in range(1, len(calendar)):
        d = calendar[k]
        if d < start:
            continue
        a = avg(k)
        below = a is not None and closes[k] < a
        reason = None
        if not on:
            if below and R.leg('SPY', d, 'w')[0] == 'downtrend':
                lab = R.labels('SPY', d, 'w')
                his = [x for x in lab if x['type'] == 'high']
                kh = kidx.get(his[-1]['ts'][:10]) if his else None
                ah = avg(kh) if kh else None
                if ah is not None and his[-1]['price'] < ah:
                    los = [x for x in lab if x['type'] == 'low']
                    if len(los) >= 2:
                        sl = math.log(los[-1]['price'] / los[-2]['price']) / _sessions(los[-2]['ts'], los[-1]['ts'])
                        sd = _vol([x for x in closes[max(0, k - VOL_LOOK):k + 1] if x])
                        on = sd > 0 and abs(sl / sd) < slow
                        if on:
                            reason = 'exit'
        else:
            if not below:
                on, reason = False, 'above'
            else:
                sst, sg = R.leg('SPY', d)
                if sst == 'uptrend' and sg is not None and sg > 0:
                    others = [R.leg(t, d)[1] for t in assets if R.leg(t, d)[0] == 'uptrend']
                    if all(o is None or sg > o for o in others):
                        on, reason = False, 'steeper'
        m = (R.steepest(d, assets) or 'BIL') if on else rot[d]
        modes[d] = m
        if m != prev:
            why[d] = reason or ('switch' if on else 'rotate' if m != 'boost' else 'rotate-end')
        prev = m
    return modes, why, R, dict(rot=mode, streak=streak, cand=cand_prev, out=on)


def rotation_curve(boost_curve, asset_px, calendar, modes, cost=SWITCH_COST):
    """[[date, value]] from 1.0: the Boost curve while the mode is 'boost', else the asset
    (asset_px: {asset: {date: close}}, filled). The mode decided at a close is traded at
    the next session's close; a switch costs `cost` of the account."""
    bv = dict(boost_curve)
    idx = {d: i for i, d in enumerate(calendar)}
    out, val, held, prev = [], 1.0, 'boost', None
    for d, _ in boost_curve:
        if prev is not None:
            if held == 'boost':
                val *= bv[d] / bv[prev]
            else:
                p0, p1 = asset_px[held].get(prev), asset_px[held].get(d)
                if p0 and p1:
                    val *= p1 / p0
        k = idx[d]
        nxt = modes.get(calendar[k - 1], 'boost') if k > 0 else 'boost'   # decided yesterday, traded at today's close
        if nxt != held:
            val *= 1 - cost
            held = nxt
        out.append([d, val])
        prev = d
    return out


def switch_log(modes, why, n=12):
    """The last n holding changes, newest first: [decision date, from, to, why]."""
    out, prev = [], 'boost'
    for d in sorted(modes):
        if modes[d] != prev:
            out.append([d, prev, modes[d], why.get(d)])
        prev = modes[d]
    return out[::-1][:n]

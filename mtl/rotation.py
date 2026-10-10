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
With the surge exit added to the Boost 100% list (mtl.momentum.surge_exit, the dashboard
default from Oct 10, 2026): 32.8% (21.3%), worst drop -44%, vs 28.7% (18.8%) and -59%.
With the whipsaw half-switch on top (the default from Oct 10, 2026; see whipsaw() below):
33.4% (21.7%), worst drop -41%; from 2010 28.8% vs 28.5%, from 2020 55.8% vs 55.9% with
the worst drop -31% vs -39%. The thresholds were picked on that same history.

3. Whipsaw half-switch. Checked at each week's last close: of the stocks the Boost 100%
   list sold in the last WHIP_LOOK sessions (at least WHIP_MIN sales), if WHIP_LOSS or more
   were sold below their buy price, momentum is whipsawing. Until the next weekly check
   finds otherwise, while the plan would hold the Boost list, half stays in the Boost list
   and half goes into whichever of TLT, GLD and SPY is up most over the last WHIP_PCT
   sessions, skipping any whose weekly structure is a downtrend (T-bills if none is up).
   It was on about 5% of the time (late 2008, late 2011, late 2015, late 2018, 2022).

4. Rate/gold regime. When the 10-year Treasury yield and gold are both higher than
   REGIME_LOOK sessions ago (an inflationary boom), the whipsaw half-switch is skipped and
   the plan stays fully in the Boost list: bonds tend to lose in that regime, so moving half
   into them was a drag. Default from Oct 10, 2026: 33.7% a year before tax (21.9% after)
   vs 33.4% (21.7%), worst drop -41% for both; from 2010 29.1% vs 28.8%, from 2016 38.1%
   vs 37.5%, from 2020 57.2% vs 55.8%. Also held with a 6-month look (33.7%, 29.1%, 56.9%); faded with a 1-month look.
   A small gain from one more rule, so it is on probation until live results back it.

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
WHIP_LOOK = 126       # sessions of Boost-list sales the whipsaw check looks back over
WHIP_MIN = 6          # sales needed in that window before it can switch on
WHIP_LOSS = 0.65      # share of those sales below their buy price that switches it on
WHIP_PCT = 63         # sessions of % change used to pick the half-switch asset
WHIP_ASSETS = ('TLT', 'GLD', 'SPY')
REGIME_LOOK = 63      # sessions over which the 10-year yield and gold must both be up to skip the half-switch


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


def warnings(R, bars, calendar, start, ma=MA, assets=ROT_ASSETS):
    """Information only, not traded: the days SPY's daily structure is a downtrend while it
    closes below its `ma`-day average and TLT or GLD is in a rising daily structure.
    Returns {date: steepest rising asset} for those days from `start`. Tested as an automatic
    switch (straight into that asset, no wait) it fixed late-2018 but cost about 2 points a
    year over 2000-2026, so it is shown as a warning for the viewer to judge."""
    spy = {b[0]: b[4] for b in bars['SPY']}
    closes = [spy.get(d) for d in calendar]
    out = {}
    for k, d in enumerate(calendar):
        if d < start or k < ma - 1:
            continue
        w = [x for x in closes[k - ma + 1:k + 1] if x]
        if len(w) < ma or closes[k] is None or closes[k] >= sum(w) / ma:
            continue
        if R.leg('SPY', d)[0] != 'downtrend':
            continue
        a = R.steepest(d, assets)
        if a:
            out[d] = a
    return out


def warning_log(warn, calendar, n=8):
    """The last n warning stretches, newest first: [first day, last day, asset on the first day]."""
    out, cur = [], None
    for d in calendar:
        if d in warn:
            if cur is None:
                cur = [d, d, warn[d]]
            else:
                cur[1] = d
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out[::-1][:n]


def sales(picks, prices):
    """Every sale of a picks schedule [(date, [tickers])]: [(date, ticker, buy close, sell close)],
    both closes on the schedule dates the name came in and went out."""
    out, held = [], {}
    for d, names in picks:
        now = set(names)
        for t in [t for t in held if t not in now]:
            out.append((d, t, held.pop(t), (prices.get(t) or {}).get(d)))
        for t in names:
            if t not in held:
                held[t] = (prices.get(t) or {}).get(d)
    return out


def whipsaw(picks, prices, calendar, start, look=WHIP_LOOK, need=WHIP_MIN, loss=WHIP_LOSS):
    """{date: on} for every session from `start`: decided at each week's last close from the
    Boost list's sales in the last `look` sessions (on when at least `need` sales and a
    `loss` share or more of them below their buy close), carried until the next week's check."""
    kidx = {d: i for i, d in enumerate(calendar)}
    by_k = {}
    for d, t, a, b in sales(picks, prices):
        if d in kidx:
            by_k.setdefault(kidx[d], []).append(bool(a and b and b < a))
    out, on = {}, False
    for k, d in enumerate(calendar):
        last = k + 1 == len(calendar) or date.fromisoformat(calendar[k + 1]).isocalendar()[:2] != date.fromisoformat(d).isocalendar()[:2]
        if last and k >= look:
            ex = [x for i in range(k - look + 1, k + 1) for x in by_k.get(i, ())]
            on = len(ex) >= need and sum(ex) / len(ex) >= loss
        if d >= start:
            out[d] = on
    return out


def whip_pick(R, closes, calendar, k, assets=WHIP_ASSETS, look=WHIP_PCT):
    """(asset, {asset: % change}): the asset up most over `look` sessions to calendar[k],
    skipping any in a weekly downtrend; 'BIL' when none is up. closes: {asset: {date: close}}."""
    d = calendar[k]
    chg, best, bv = {}, 'BIL', 0.0
    for t in assets:
        a, b = (closes.get(t) or {}).get(calendar[k - look]) if k >= look else None, (closes.get(t) or {}).get(d)
        chg[t] = b / a - 1 if a and b else None
        if R.leg(t, d, 'w')[0] == 'downtrend' or chg[t] is None:
            continue
        if chg[t] > bv:
            best, bv = t, chg[t]
    return best, chg


def reflation(rate, gold, calendar, look=REGIME_LOOK):
    """{date: True/False/None}: the 10-year yield (rate: {date: yield}) and gold ({date: close})
    both higher than `look` sessions earlier, each carried forward over missing days; None
    while either reading is missing."""
    out, r, g, hr, hg = {}, None, None, [], []
    for d in calendar:
        r, g = rate.get(d, r), gold.get(d, g)
        hr.append(r)
        hg.append(g)
    for k, d in enumerate(calendar):
        if k < look or None in (hr[k], hr[k - look], hg[k], hg[k - look]):
            out[d] = None
        else:
            out[d] = hr[k] > hr[k - look] and hg[k] > hg[k - look]
    return out


def whip_halves(modes, whip, R, closes, calendar, assets=WHIP_ASSETS, look=WHIP_PCT, skip=None):
    """{date: asset} for the days the plan is in the Boost list and the whipsaw check is on:
    half the account goes into that asset (see whip_pick). skip: {date: True} for days the
    half-switch stands aside (the reflation regime) and the plan stays fully in the Boost list."""
    kidx, skip = {d: i for i, d in enumerate(calendar)}, skip or {}
    return {d: whip_pick(R, closes, calendar, kidx[d], assets, look)[0]
            for d, m in modes.items() if m == 'boost' and whip.get(d) and not skip.get(d)}


def whip_log(whip, half, calendar, n=8):
    """The last n whipsaw stretches, newest first: [first day, last day, asset on the first day]."""
    out, cur = [], None
    for d in calendar:
        if whip.get(d):
            if cur is None:
                cur = [d, d, half.get(d)]
            else:
                cur[1] = d
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out[::-1][:n]


def rotation_curve(boost_curve, asset_px, calendar, modes, cost=SWITCH_COST, half=None):
    """[[date, value]] from 1.0: the Boost curve while the mode is 'boost', else the asset
    (asset_px: {asset: {date: close}}, filled). The mode decided at a close is traded at
    the next session's close; a switch costs `cost` of the account. half: {date: asset}
    for the days half the account sits in that asset instead (the whipsaw half-switch),
    kept at 50/50 each session; moving the half costs half of `cost`."""
    bv = dict(boost_curve)
    idx = {d: i for i, d in enumerate(calendar)}
    half = half or {}

    def ret(h, a, b):
        if h == 'boost':
            return bv[b] / bv[a]
        p0, p1 = asset_px[h].get(a), asset_px[h].get(b)
        return p1 / p0 if p0 and p1 else 1.0
    out, val, held, hh, prev = [], 1.0, 'boost', None, None
    for d, _ in boost_curve:
        if prev is not None:
            val *= ret(held, prev, d) if hh is None else 0.5 * ret('boost', prev, d) + 0.5 * ret(hh, prev, d)
        k = idx[d]
        y = calendar[k - 1] if k > 0 else None   # decided yesterday, traded at today's close
        nxt = modes.get(y, 'boost') if y else 'boost'
        nh = half.get(y) if y and nxt == 'boost' else None
        if nxt != held:
            val *= 1 - cost
        elif nh != hh:
            val *= 1 - cost / 2
        held, hh = nxt, nh
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

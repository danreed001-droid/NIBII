"""Ignition flags: the price/volume signatures that started the big 2021-2026
winners (see documents/winners_research.html), computed on daily OHLCV.

All inputs are wide pandas DataFrames (index = session dates, columns =
tickers) of split/dividend-adjusted Open, High, Low, Close and Volume. Every
rule uses only data up to and including the session being flagged, so the
same code both scans today and replays history for the hit-rate table.

Flags (each needs an up day closing in the top 40% of its range, a price of
at least MIN_PRICE and MIN_DOLLAR_VOL average daily dollar volume):

- ignition    - gap up >= 8% on >= 3x the 50-day average volume, in an
                uptrend (trend template below).
- turnaround  - gap up >= 15% on >= 5x volume while NOT in an uptrend, with
                3-month relative strength in the top 30% (Palantir, AppLovin,
                Carvana ignited 20-70% below their highs).
- breakout    - close at a new 252-session closing high on >= 1.5x volume, in
                an uptrend, relative strength in the top 20%.
- pocket      - pocket pivot: up-day volume above every down day's volume in
                the prior 10 sessions, in an uptrend, relative strength in the
                top 20%, no gap needed - quieter accumulation.

Trend template (Minervini / Weinstein stage 2): close > SMA50 > SMA150 >
SMA200, SMA200 higher than 21 sessions ago, close within 25% of the 52-week
high and at least 25% above the 52-week low.

Relative strength = 0.4 * 3-month return + 0.2 * each of the three earlier
quarters (an IBD-style approximation), ranked across the scanned universe
each day as a 1-99 percentile.

Breakout and pocket flags are skipped on mechanical-volume days (monthly
options expiry, the Russell reconstitution) - index funds trade size there,
not conviction. A one-day move beyond +200% / -80% is treated as a data
glitch and never flags.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 10e6          # 50-day average close x volume
VOL_LOOK = 50
CLV_MIN = 0.6
IGN_GAP, IGN_VOL = 0.08, 3.0
TURN_GAP, TURN_VOL, TURN_RS = 0.15, 5.0, 70
BRK_VOL, BRK_RS = 1.5, 80
POCKET_LOOK, POCKET_RS = 10, 80
REPEAT_LOOK = 252
KINDS = ('ignition', 'turnaround', 'breakout', 'pocket')
POINTS = {'ignition': 3.0, 'turnaround': 2.0, 'breakout': 2.0, 'pocket': 1.0}
HORIZONS = (20, 60, 120)


def third_friday(y, m):
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def mechanical_days(index):
    """Sessions whose volume is mostly index/options plumbing: the monthly
    options expiry (third Friday, or the session before when it's a holiday)
    and the Russell reconstitution (last Friday of June)."""
    sessions = [pd.Timestamp(d).date() for d in index]
    have = set(sessions)
    out = set()
    for y in sorted({d.year for d in sessions}):
        for m in range(1, 13):
            f = third_friday(y, m)
            while f not in have and f >= date(y, m, 12):
                f -= timedelta(days=1)
            out.add(f)
        d = date(y, 6, 30)
        while d.weekday() != 4:
            d -= timedelta(days=1)
        while d not in have and d >= date(y, 6, 20):
            d -= timedelta(days=1)
        out.add(d)
    return pd.Series([d in out for d in sessions], index=index)


def rs_score(C):
    r = lambda a, b: C.shift(a) / C.shift(b) - 1
    return 0.4 * (C / C.shift(63) - 1) + 0.2 * r(63, 126) + 0.2 * r(126, 189) + 0.2 * r(189, 252)


def pct_rank(df):
    """Row-wise 1-99 percentile rank (NaN stays NaN)."""
    return (df.rank(axis=1, pct=True) * 98 + 1).round()


def compute(O, H, L, C, V):
    """Every per-session indicator and flag. Returns a dict of DataFrames."""
    pc = C.shift(1)
    v50 = V.shift(1).rolling(VOL_LOOK, min_periods=VOL_LOOK).mean()
    vr = V / v50
    dv50 = (C * V).shift(1).rolling(VOL_LOOK, min_periods=VOL_LOOK).mean()
    rng = H - L
    clv = ((C - L) / rng.where(rng > 0)).fillna(1.0)
    gap = O / pc - 1
    chg = C / pc - 1
    sma = {n: C.rolling(n, min_periods=n).mean() for n in (50, 150, 200)}
    hi52 = C.shift(1).rolling(252, min_periods=252).max()
    lo52 = C.rolling(252, min_periods=252).min()
    trend = ((C > sma[50]) & (sma[50] > sma[150]) & (sma[150] > sma[200])
             & (sma[200] > sma[200].shift(21)) & (C >= 0.75 * hi52) & (C >= 1.25 * lo52))
    rs = pct_rank(rs_score(C))
    rs3 = pct_rank(C / C.shift(63) - 1)
    liquid = (C >= MIN_PRICE) & (dv50 >= MIN_DOLLAR_VOL)
    sane = (chg < 2.0) & (chg > -0.8)
    upq = (chg > 0) & (clv >= CLV_MIN) & liquid & sane
    mech = mechanical_days(C.index)
    calm = pd.DataFrame(np.repeat(~mech.values[:, None], C.shape[1], axis=1), index=C.index, columns=C.columns)
    down_vol = V.where(C < pc)
    max_down = down_vol.shift(1).rolling(POCKET_LOOK, min_periods=1).max().fillna(0)

    ign = upq & trend & (gap >= IGN_GAP) & (vr >= IGN_VOL)
    turn = upq & ~trend & (gap >= TURN_GAP) & (vr >= TURN_VOL) & (rs3 >= TURN_RS)
    brk = upq & trend & calm & (C > hi52) & (vr >= BRK_VOL) & (rs >= BRK_RS) & ~ign
    pocket = upq & trend & calm & (V > max_down) & (max_down > 0) & (rs >= POCKET_RS) & ~ign & ~brk
    flags = {'ignition': ign.fillna(False), 'turnaround': turn.fillna(False),
             'breakout': brk.fillna(False), 'pocket': pocket.fillna(False)}
    gaps = (flags['ignition'] | flags['turnaround']).astype(int)
    repeats = gaps.rolling(REPEAT_LOOK, min_periods=1).sum()
    return dict(flags=flags, vr=vr, gap=gap, chg=chg, rs=rs, rs3=rs3, hi52=hi52, trend=trend,
                repeats=repeats, mech=mech, liquid=liquid)


def score(kind, rs, repeats, off_high, group=False):
    """Composite rank for today's list: setup first, then relative strength,
    repeat gaps, closeness to the high and a sympathy move in the industry."""
    s = POINTS[kind] + (rs or 0) / 50.0 + 1.0 * max(0, (repeats or 1) - 1)
    if off_high is not None:
        s += max(0.0, 1.0 + off_high / 0.25)   # 0 at 25% below the high, 1 at the high
    return round(s + (1.0 if group else 0.0), 2)


def events(flags, start_row=0):
    """[(row, ticker, kind)] for every flag at or after start_row."""
    out = []
    for kind in KINDS:
        f = flags[kind].iloc[start_row:]
        rows, cols = np.nonzero(f.values)
        out += [(start_row + int(r), f.columns[c], kind) for r, c in zip(rows, cols)]
    return sorted(out)


def forward(C, spy, row, t, n):
    """(return, return minus SPY's) from row's close to n sessions later, or None."""
    if row + n >= len(C):
        return None
    a, b = C[t].iat[row], C[t].iat[row + n]
    sa, sb = spy.iat[row], spy.iat[row + n]
    if not (a > 0 and b > 0 and sa > 0 and sb > 0):
        return None
    r = b / a - 1
    return r, r - (sb / sa - 1)


def hit_stats(C, spy, evs):
    """Per kind: how the flags did afterwards - the scanner's own base rates.
    Median return and median excess over SPY at each horizon, % that beat SPY
    over 60 sessions, % that reached +50% at any close within 120 sessions,
    and the median worst drawdown from the entry close within 60 sessions."""
    out = {}
    for kind in KINDS:
        ks = [(r, t) for r, t, k in evs if k == kind]
        st = {'n': len(ks)}
        for n in HORIZONS:
            f = [forward(C, spy, r, t, n) for r, t in ks]
            f = [x for x in f if x]
            st[f'n{n}'] = len(f)
            st[f'ret{n}'] = float(np.median([x[0] for x in f])) if f else None
            st[f'ex{n}'] = float(np.median([x[1] for x in f])) if f else None
            if n == 60:
                st['beat60'] = float(np.mean([x[1] > 0 for x in f])) if f else None
        big, dd = [], []
        for r, t in ks:
            a = C[t].iat[r]
            if r + 120 < len(C):
                big.append(C[t].iloc[r + 1:r + 121].max() / a - 1 >= 0.5)
            if r + 60 < len(C):
                dd.append(C[t].iloc[r + 1:r + 61].min() / a - 1)
        st['up50'] = float(np.mean(big)) if big else None
        st['mae60'] = float(np.median(dd)) if dd else None
        out[kind] = st
    return out

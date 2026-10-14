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


def baseline(C, spy, liquid, start_row):
    """The same numbers for every liquid stock on every session since start_row
    - what a random pick did, so the flags' rows can be judged against it."""
    sr = lambda n: spy.shift(-n) / spy - 1
    rows = slice(start_row, None)
    st = {'n': int(liquid.iloc[rows].values.sum())}
    for n in HORIZONS:
        r = (C.shift(-n) / C - 1).where(liquid).iloc[rows]
        ex = r.sub(sr(n).iloc[rows], axis=0)
        v, e = r.values[np.isfinite(r.values)], ex.values[np.isfinite(ex.values)]
        st[f'n{n}'] = int(v.size)
        st[f'ret{n}'] = float(np.median(v)) if v.size else None
        st[f'ex{n}'] = float(np.median(e)) if e.size else None
        if n == 60:
            st['beat60'] = float(np.mean(e > 0)) if e.size else None
    fmax = C.iloc[::-1].rolling(120, min_periods=120).max().iloc[::-1].shift(-1)
    fmin = C.iloc[::-1].rolling(60, min_periods=60).min().iloc[::-1].shift(-1)
    up = (fmax / C - 1).where(liquid).iloc[rows].values
    dd = (fmin / C - 1).where(liquid).iloc[rows].values
    up, dd = up[np.isfinite(up)], dd[np.isfinite(dd)]
    st['up50'] = float(np.mean(up >= 0.5)) if up.size else None
    st['mae60'] = float(np.median(dd)) if dd.size else None
    return st


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


PROFIT_AT = 0.20        # take part of the gain off here (the swing playbook in the research)
TRAIL_AFTER = 5         # sessions before the 20-day-average trail applies
ACT_KINDS = ('ignition', 'turnaround')
ORDER = {'new': 0, 'exit': 1, 'trail': 2, 'profit': 3, 'hold': 4}


def _pc(x, d=1):
    return f'{x * 100:+.{d}f}%'


def market_note(m):
    """(tone, text) on how big new positions should be, from SPY's trend."""
    if not m or not m.get('spy') or not m.get('sma200'):
        return 'ok', 'Market trend unknown: use normal size.'
    if m['spy'] < m['sma200']:
        return 'bad', ('SPY is below its 200-day average. Momentum signals fail most in falling and panic-rebound markets: '
                       'halve new position sizes, or wait.')
    if m.get('sma50') and m['spy'] < m['sma50']:
        return 'warn', 'SPY is above its 200-day but below its 50-day average: take only the best setups, at normal or smaller size.'
    return 'ok', 'SPY is above its 50- and 200-day averages: normal size for new positions.'


def plan(scan):
    """What to do with each ignition / turnaround from the last few weeks plus
    today's breakouts, from the swing playbook: new flag -> check the news, buy
    near the close with the flag-day low as the stop; up 20%+ -> take part off
    and trail on the 20-day average; closed under the 20-day average after a
    gain -> sell the rest; closed under the flag-day low -> stop hit, exit.
    [{t, n, kind, act, text, close, stop}] - newest flags first in each group."""
    out, seen = [], set()
    today = {r['t']: r for r in scan.get('today') or []}
    for r in scan.get('recent') or []:          # newest first
        t = r['t']
        if t in seen or (r['kind'] not in ACT_KINDS and not (r['kind'] == 'breakout' and r.get('days') == 0)):
            continue
        seen.add(t)
        close, low, sma20, since = r.get('close'), r.get('low'), r.get('sma20'), r.get('since') or 0.0
        if close is None or low is None:
            continue
        risk = close / low - 1 if low else None
        reps = (today.get(t) or r).get('repeats') or 0
        if r.get('days') == 0:
            act = 'new'
            lead = (f'Repeat gap (#{reps} in 12 months) - the stronger signal; add if you already own it. ' if reps >= 2
                    and r['kind'] in ACT_KINDS else '')
            text = (lead + 'Check the news first: a guidance raise, big contract or first profit fits the winners\' pattern; '
                    f'a buyout or one-off does not. If it fits, buy near the close or in tomorrow\'s first 30 minutes '
                    f'with a stop at the flag-day low {low:.2f}' + (f' ({_pc(-risk)} away).' if risk else '.'))
            if r['kind'] == 'breakout':
                text = 'Breakout to a new high on volume - watchlist; ' + text[0].lower() + text[1:]
        elif close < low:
            act, text = 'exit', (f'If you hold it, exit - stop hit: closed {close:.2f}, below the flag-day low {low:.2f}. Exit; put it back on '
                                 'the list if it gaps up on volume again.')
        elif since > 0 and sma20 and close < sma20 and r.get('days', 0) >= TRAIL_AFTER:
            act, text = 'trail', (f'Up {_pc(since)} since the flag but closed under its 20-day average ({sma20:.2f}): '
                                  'if you hold it, sell what\'s left or tighten the stop to the latest low.')
        elif since >= PROFIT_AT:
            act, text = 'profit', (f'Up {_pc(since)} since the flag: if you hold it, take a third to a half off, trail the rest on the '
                                   f'20-day average ({sma20:.2f}).' if sma20 else f'Up {_pc(since)}: take a third to a half off.')
        else:
            act, text = 'hold', (f'{_pc(since)} since the flag {r.get("days")} session{"s" if r.get("days") != 1 else ""} ago. Hold; stop stays at the '
                                 f'flag-day low {low:.2f}' + (f' ({_pc(-risk)} away).' if risk else '.'))
        out.append(dict(t=t, n=r.get('n', ''), kind=r['kind'], d=r.get('d'), act=act, text=text, close=close, stop=low,
                        why=_why(act, r, scan, risk)))
    out.sort(key=lambda x: (ORDER[x['act']], 0 if x['kind'] in ACT_KINDS else 1))
    return out


def _flagged(r, rules):
    """What made the stock flag, in words, from the scan's own thresholds."""
    k, ru = r['kind'], rules or {}
    if k == 'ignition':
        what = f"a gap up of {ru.get('ignGap', 0.08) * 100:.0f}%+ on {ru.get('ignVol', 3):.0f}x its usual volume (an ignition)"
    elif k == 'turnaround':
        what = f"a gap up of {ru.get('turnGap', 0.15) * 100:.0f}%+ on {ru.get('turnVol', 5):.0f}x its usual volume after a slide (a turnaround)"
    elif k == 'breakout':
        what = f"a close at a new high on {ru.get('brkVol', 1.5):g}x its usual volume (a breakout)"
    else:
        what = 'a volume signal'
    rep = r.get('repeats') or 0
    return f"Flagged {r.get('d')}: {what}" + (f"; its #{rep} gap in 12 months, and repeat gaps were the stronger signal." if rep >= 2 else '.')


def _why(act, r, scan, risk):
    """The reasons behind an action, as short bullets: what flagged, and why the playbook acts now."""
    st = (scan.get('stats') or {}).get(r['kind']) or {}
    since_y = (scan.get('statsFrom') or '')[:4]
    up50, ret60, mae = st.get('up50'), st.get('ret60'), st.get('mae60')
    odds = (f"since {since_y} about {up50 * 100:.0f}% of {r['kind']}s went on to gain 50%+ within 6 months, while the typical one was "
            f"{_pc(ret60, 0)} three months later" if up50 is not None and ret60 is not None else '')
    since, low, sma20 = r.get('since') or 0.0, r.get('low'), r.get('sma20')
    out = [_flagged(r, scan.get('rules'))]
    if act == 'new':
        out.append('Why buy: ' + (odds + ', so ' if odds else '') + 'the plan is many small bets: the stop at the flag-day low caps each '
                   'loss' + (f' ({_pc(-risk)} away, sized to risk 1% of the account)' if risk else '') + ' and the few big winners pay for the rest.')
        tone, _ = market_note(scan.get('market'))
        if tone == 'bad':
            out.append('SPY is below its 200-day average, when these signals fail most: half size, or wait.')
    elif act == 'exit':
        out.append(f'Why exit: closing under the flag-day low ({low:.2f}) means the buyers behind the gap have given it all back; '
                   'cutting it here keeps the loss to the planned 1% of the account' +
                   (f' (a typical flag dipped {_pc(mae, 0)} at its worst within 3 months).' if mae is not None else '.'))
    elif act == 'trail':
        out.append(f'Why sell: after a gain, a close under the 20-day average ({sma20:.2f}) is the playbook\'s sign the move is fading; '
                   f'selling now keeps most of the {_pc(since)} instead of riding it back down.')
    elif act == 'profit':
        out.append(f'Why take profit: up {_pc(since)}, past the 20% mark where the playbook banks part of the gain' +
                   (f'; only about {up50 * 100:.0f}% of these keep running to +50%' if up50 is not None else '') +
                   ', so taking some off locks in the win while the rest rides a trailing stop.')
    else:
        out.append(f'Why hold: still above the flag-day low ({low:.2f}), so the setup has not failed; nothing to do until it hits the '
                   f'stop, gains {PROFIT_AT * 100:.0f}%, or (in profit, {TRAIL_AFTER}+ sessions in) closes under its 20-day average'
                   + (f' ({sma20:.2f})' if sma20 else '') + '.')
    return out


THEME_MIN = 8            # liquid stocks an industry needs to be ranked
THEME_LOOK = 20          # sessions of flags / trend change
EMERGING_DELTA = 0.15    # uptrend share up 15+ points in THEME_LOOK sessions


def themes(C, res, industry, flagged, spy, look=THEME_LOOK):
    """Which industries are heating up, whatever they are: for every industry
    with THEME_MIN+ liquid stocks - how many of its stocks flagged recently,
    what share are in an uptrend now vs `look` sessions ago, and the median
    3-month return vs SPY. heat = average of the three cross-industry
    percentile ranks (flag rate, uptrend share, 3-month return), 0-100.
    flagged: {ticker} that flagged (not pocket pivots) in the last `look` sessions.
    Returns rows sorted hottest first."""
    last = len(C) - 1
    liq = res['liquid'].iloc[last]
    tr_now, tr_then = res['trend'].iloc[last], res['trend'].iloc[last - look]
    r63 = C.iloc[last] / C.iloc[last - 63] - 1 - (spy.iat[last] / spy.iat[last - 63] - 1)
    rs = res['rs'].iloc[last]
    groups = {}
    for t in C.columns:
        g = industry.get(t)
        if g and bool(liq.get(t)):
            groups.setdefault(g, []).append(t)
    rows = []
    for g, ts in groups.items():
        if len(ts) < THEME_MIN:
            continue
        fl = [t for t in ts if t in flagged]
        up_now = float(np.mean([bool(tr_now[t]) for t in ts]))
        up_then = float(np.mean([bool(tr_then[t]) for t in ts]))
        ret = r63[ts].dropna()
        leaders = sorted((t for t in ts if rs[t] == rs[t]), key=lambda t: -rs[t])[:4]
        rows.append(dict(ind=g, n=len(ts), flags=len(fl), flagged=sorted(fl, key=lambda t: -(rs[t] if rs[t] == rs[t] else 0))[:6],
                         up=round(up_now, 3), dUp=round(up_now - up_then, 3),
                         r63=None if ret.empty else round(float(ret.median()), 4), leaders=leaders))
    if not rows:
        return []
    df = pd.DataFrame(rows)
    rank = lambda s: s.rank(pct=True).fillna(0)
    df['heat'] = ((rank(df['flags'] / df['n']) + rank(df['up']) + rank(df['r63'].astype(float))) / 3 * 100).round()
    df = df.sort_values(['heat', 'flags'], ascending=False)
    df['emerging'] = (df['dUp'] >= EMERGING_DELTA) & (df['heat'] >= df['heat'].quantile(0.75))
    return [{**r, 'heat': int(r['heat']), 'emerging': bool(r['emerging'])} for r in df.to_dict('records')]


def new_leaders(top_now, history, top=10, back=5):
    """Industries in today's top `top` that weren't in it `back` runs ago
    (or the oldest run on record). history: [[date, [industry, ...]], ...]."""
    if not history:
        return []
    then = set(history[-back][1][:top]) if len(history) >= back else set(history[0][1][:top])
    return [g for g in top_now[:top] if g not in then]

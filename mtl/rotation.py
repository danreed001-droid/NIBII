"""Bond / gold rotation: an info-only overlay on Boost + cushion.

When SPY is in a confirmed daily downtrend (a lower high and a lower low, until
it makes a higher high) and TLT or GLD is in a confirmed daily uptrend (a higher
high and a higher low, until it makes a lower low), compare how steep each
trend is: the slope through the last two swing lows (the asset's higher lows)
or highs (SPY's lower highs), per session, divided by the market's normal
daily swing (average high-low range over SWING_LEN sessions as a share of the
close). If the asset's trend is steeper than SPY's for WAIT sessions in a row,
move 100% into it; come back when it closes below its latest confirmed swing
low (a lower low). Decided at a close, traded at the next session's close.

Swings are N-bar fractals (mtl.structure.find_swings) and count only from the
bar that confirms them (i + n), so no read uses a bar not yet printed.

Pure and network-free; bars are [(date, open, high, low, close)] oldest first.
"""
from mtl.structure import find_swings, label_structure

ASSETS = ('TLT', 'GLD')
SWING_N = 3       # bars each side, the same daily read as the dashboard's cards
SWING_LEN = 20    # sessions in the "normal daily swing"
WAIT = 15         # sessions the setup must hold before the switch


def _reads(bars, n=SWING_N, swing_len=SWING_LEN):
    """{date: dict(up, down, slope_lo, slope_hi, swing_low)} from each date's
    confirmed swings: up = confirmed by a higher high and a higher low and holding
    until a lower low; down = confirmed by a lower high and a lower low and holding
    until a higher high;
    slope_lo / slope_hi = per-session % slope through the last two swing lows /
    highs divided by the normal daily swing; swing_low = latest swing low."""
    swings = label_structure(find_swings(bars, n=n))
    out, si, up, down = {}, 0, False, False
    last = {'high': [], 'low': []}
    rng = [(h - l) / c if c else 0.0 for _, _, h, l, c in bars]
    for t, b in enumerate(bars):
        while si < len(swings) and swings[si]['i'] + n <= t:
            s = swings[si]
            last[s['type']] = (last[s['type']] + [s])[-2:]
            si += 1
            if s['label'] == 'LL':
                up = False
            if s['label'] == 'HH':
                down = False
            hi_, lo_ = last['high'], last['low']
            if hi_ and lo_ and hi_[-1]['label'] == 'HH' and lo_[-1]['label'] == 'HL':
                up = True
            if hi_ and lo_ and hi_[-1]['label'] == 'LH' and lo_[-1]['label'] == 'LL':
                down = True
        hi, lo = last['high'], last['low']
        if len(hi) < 2 or len(lo) < 2 or t + 1 < swing_len:
            out[b[0]] = None
            continue
        swing = sum(rng[t + 1 - swing_len:t + 1]) / swing_len
        if swing <= 0:
            out[b[0]] = None
            continue

        def slope(a, z):
            return (z['price'] / a['price'] - 1) / max(1, z['i'] - a['i']) / swing
        out[b[0]] = dict(up=up, down=down,
                         slope_lo=slope(*lo), slope_hi=slope(*hi), swing_low=lo[-1]['price'])
    return out


def rotation_signal(market, assets, calendar, wait=WAIT, n=SWING_N, swing_len=SWING_LEN):
    """Replays the rule over calendar. market: SPY bars; assets: {ticker: bars}.

    Returns dict(
      held={date: ticker or None} - what the rule holds after that date's close
          decision (traded at the next session's close),
      streak={date: {ticker: sessions in a row the setup has held}},
      switches=[[decision date, ticker, exit decision date or None], ...],
      reads={ticker: {date: read}} for the market ('SPY') and each asset)."""
    reads = {'SPY': _reads(market, n, swing_len)}
    closes = {}
    for t, bs in assets.items():
        reads[t] = _reads(bs, n, swing_len)
        closes[t] = {b[0]: b[4] for b in bs}
    streak = {t: 0 for t in assets}
    broken = set()    # exited on a lower low: no re-entry until its uptrend reads as broken
    held, out_held, out_streak, switches = None, {}, {}, []
    for d in calendar:
        m = reads['SPY'].get(d)
        if held is not None:
            r = reads[held].get(d)
            c = closes[held].get(d)
            if r and c is not None and c < r['swing_low']:
                switches[-1][2] = d
                broken.add(held)
                held = None
                streak = {t: 0 for t in assets}   # the setup starts over after an exit
        for t in assets:
            r = reads[t].get(d)
            if t in broken and r and not r['up']:
                broken.discard(t)
            ok = (t not in broken and m and r and m['down'] and r['up']
                  and r['slope_lo'] > 0 and r['slope_lo'] > abs(m['slope_hi']))
            streak[t] = streak[t] + 1 if ok else 0
        if held is None:
            ready = [t for t in assets if streak[t] >= wait]
            if ready:
                held = max(ready, key=lambda t: reads[t][d]['slope_lo'])
                switches.append([d, held, None])
        out_held[d] = held
        out_streak[d] = dict(streak)
    return dict(held=out_held, streak=out_streak, switches=switches, reads=reads)


def rotation_curve(base, asset_closes, calendar, held):
    """[[date, value]] from 1.0: `base` ([[date, value]], e.g. Boost + cushion) except
    while the rule holds an asset. held[d] (the decision at d's close) takes effect
    from the next session's close, like the dashboard's other plans."""
    base_v = dict(base)
    idx = {d: i for i, d in enumerate(calendar)}
    out, nav, prev, pos = [], 1.0, None, None
    for d, v in base:
        if prev is not None:
            src = base_v if pos is None else asset_closes.get(pos, {})
            a, b = src.get(prev), src.get(d)
            if a and b:
                nav *= b / a
        out.append([d, nav])
        # today's close: trade into whatever yesterday's close decided
        k = idx.get(d)
        pos = held.get(calendar[k - 1]) if k else None
        prev = d
    return out

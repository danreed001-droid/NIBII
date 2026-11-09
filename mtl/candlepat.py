"""Classic candlestick patterns and a candle-noise reading for the scanner's stock charts. Information only: nothing
here changes the plan.

patterns(bars) marks, for each daily candle (date, open, high, low, close), the patterns that complete on it:
- 'BE' bullish engulfing: a red candle, then a green one whose body covers it;     'SE' bearish engulfing: the reverse;
- 'HM' hammer: a small body at the top of the day's range, a lower wick at least twice the body, after a 5-day fall;
- 'SS' shooting star: the mirror image after a 5-day rise;
- 'DJ' doji: a body under a tenth of the day's range (the day's range at least half the 20-day average);
- 'MS' morning star: a long red day, a small-bodied day, then a green day closing past the middle of the first;
- 'ES' evening star: the reverse;
- 'WS' three white soldiers: three green days, each opening inside the last body and closing at a new high;
- 'BC' three black crows: the reverse;
- 'RE' re-entry: two red days making a fresh 20-day low, then a close above both of their opens (the shape of the
  plan's candle re-entry rule, here on the stock's own chart).

noise(bars) reads the last n candles: the share of days whose move reverses the day before (flips), the share of each
day's range that is wick rather than body (wick), and the net move over the sum of daily moves (efficiency)."""

BULL = ('BE', 'HM', 'MS', 'WS', 'RE')
BEAR = ('SE', 'SS', 'ES', 'BC')
NAMES = {'BE': 'Bullish engulfing', 'SE': 'Bearish engulfing', 'HM': 'Hammer', 'SS': 'Shooting star', 'DJ': 'Doji',
         'MS': 'Morning star', 'ES': 'Evening star', 'WS': 'Three white soldiers', 'BC': 'Three black crows',
         'RE': 'Re-entry (two red lows, then a close above both opens)'}


def _ok(b):
    return all(x is not None and x == x for x in b[1:5]) and b[2] >= b[3] > 0


def patterns(bars):
    """[[date, code], ...] for every pattern completing on a candle, oldest first."""
    out = []
    for i in range(len(bars)):
        b = bars[i]
        if not _ok(b):
            continue
        d, o, h, l, c = b[0], b[1], b[2], b[3], b[4]
        rng, body = h - l, abs(c - o)
        avg = None
        if i >= 20 and all(_ok(x) for x in bars[i - 20:i]):
            avg = sum(x[2] - x[3] for x in bars[i - 20:i]) / 20
        p = bars[i - 1] if i >= 1 and _ok(bars[i - 1]) else None
        if p:
            po, pc = p[1], p[4]
            if pc < po and c > o and o <= pc and c >= po and body > abs(pc - po):
                out.append([d, 'BE'])
            if pc > po and c < o and o >= pc and c <= po and body > abs(pc - po):
                out.append([d, 'SE'])
        if i >= 5 and _ok(bars[i - 5]) and rng > 0 and body > 0:
            up_w, lo_w = h - max(o, c), min(o, c) - l
            if lo_w >= 2 * body and up_w <= body and c < bars[i - 5][4]:
                out.append([d, 'HM'])
            if up_w >= 2 * body and lo_w <= body and c > bars[i - 5][4]:
                out.append([d, 'SS'])
        if avg and rng >= 0.5 * avg and body <= 0.1 * rng:
            out.append([d, 'DJ'])
        if i >= 2 and _ok(bars[i - 2]) and p:
            a = bars[i - 2]
            ab, mb = abs(a[4] - a[1]), abs(p[4] - p[1])
            if avg and ab >= 0.6 * avg and mb <= 0.3 * ab:
                if a[4] < a[1] and c > o and c > (a[1] + a[4]) / 2:
                    out.append([d, 'MS'])
                if a[4] > a[1] and c < o and c < (a[1] + a[4]) / 2:
                    out.append([d, 'ES'])
            three = [a, p, b]
            if all(x[4] > x[1] for x in three) and three[1][4] > a[4] and c > p[4] \
                    and a[1] <= p[1] <= a[4] and p[1] <= o <= p[4]:
                out.append([d, 'WS'])
            if all(x[4] < x[1] for x in three) and three[1][4] < a[4] and c < p[4] \
                    and a[4] <= p[1] <= a[1] and p[4] <= o <= p[1]:
                out.append([d, 'BC'])
            if i >= 22 and a[4] < a[1] and p[4] < p[1] and all(_ok(x) for x in bars[i - 22:i]):
                low20 = min(x[3] for x in bars[i - 22:i - 2])
                if min(a[3], p[3]) < low20 and c > max(a[1], p[1]):
                    out.append([d, 'RE'])
    return out


def noise(bars, n=21):
    """dict(flips, wick, eff) over the last n candles, or None with too few."""
    w = [b for b in bars[-(n + 1):] if _ok(b)]
    if len(w) < n + 1:
        return None
    cl = [b[4] for b in w]
    mv = [b - a for a, b in zip(cl, cl[1:])]
    flips = sum(1 for a, b in zip(mv, mv[1:]) if (a > 0) != (b > 0)) / (len(mv) - 1)
    ws = [(b[2] - b[3] - abs(b[4] - b[1])) / (b[2] - b[3]) for b in w[1:] if b[2] > b[3]]
    tot = sum(abs(x) for x in mv)
    return dict(flips=round(flips, 3), wick=round(sum(ws) / len(ws), 3) if ws else None,
                eff=round(abs(cl[-1] - cl[0]) / tot, 3) if tot else None)

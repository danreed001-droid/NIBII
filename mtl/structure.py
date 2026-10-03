"""Market structure: swing highs/lows and HH/HL/LH/LL trend labeling.

Deterministic, given the same OHLC bars this always produces the same
labeled swings and trend classification - same spirit as the rest of this
package. Uses an N-bar fractal: a bar is a swing high if its high is the
max within N bars on either side, a swing low if its low is the min within
N bars on either side. Each new swing high is labeled HH (higher high) or
LH (lower high) relative to the previous swing high; each new swing low is
labeled HL or LL relative to the previous swing low - the same "higher
highs and higher lows" / "lower highs and lower lows" read a trader does by
eye on a candlestick chart, made mechanical.

The 1-day horizon reads structure from hourly bars (a day-ahead call has no
business caring about a swing three weeks old); the 5- and 10-day horizons
read it from weekly bars (hourly noise is irrelevant at that range). Both
paths go through the same find_swings/label_structure/trend_state
functions - only the bar series differs.
"""
from collections import defaultdict
from datetime import date

MIN_BARS_NOTE = "too few bars for a swing read at this n"

# Shared by prepare_daily.py (the board's read, through S) and live_read.py
# (the latest read, through now) so the two can never disagree on method.
HOURLY_SWING_N = 3    # bars each side, for the 1D horizon's intraday read
WEEKLY_SWING_N = 2    # bars each side, for the 5D/10D horizons' weekly read
STRUCTURE_LOOKBACK = 4  # most recent labeled swings considered for the trend call


def find_swings(bars, n=3):
    """bars: [(ts, o, h, l, c), ...] oldest first, requires at least 2n+1.

    Returns swings in chronological order:
    [{'i': index, 'ts': ts, 'type': 'high'|'low', 'price': float}, ...]
    A bar can be both a swing high and a swing low (rare, a big-range bar).
    """
    swings = []
    for i in range(n, len(bars) - n):
        window = bars[i - n: i + n + 1]
        h, l = bars[i][2], bars[i][3]
        if h == max(b[2] for b in window):
            swings.append(dict(i=i, ts=bars[i][0], type='high', price=h))
        if l == min(b[3] for b in window):
            swings.append(dict(i=i, ts=bars[i][0], type='low', price=l))
    return swings


def label_structure(swings):
    """Labels each swing HH/LH (a high) or HL/LL (a low) relative to the
    previous swing of the SAME type. The first high and first low in the
    series have nothing to compare against and get label=None - and so
    does an exact tie (label=None rather than arbitrarily calling it
    "lower"; a repeat print is neither a higher high nor a lower one)."""
    last = {'high': None, 'low': None}
    labeled = []
    for s in swings:
        prev = last[s['type']]
        if prev is None or s['price'] == prev:
            label = None
        elif s['type'] == 'high':
            label = 'HH' if s['price'] > prev else 'LH'
        else:
            label = 'HL' if s['price'] > prev else 'LL'
        labeled.append(dict(s, label=label))
        last[s['type']] = s['price']
    return labeled


def trend_state(labeled_swings, lookback=4):
    """Classifies the most recent `lookback` labeled swings (label is not
    None): 'uptrend' if every one is HH/HL, 'downtrend' if every one is
    LH/LL, 'choppy' if it's a mix. None if fewer than 2 labeled swings
    exist yet - not enough to call a structure."""
    recent = [s for s in labeled_swings if s['label']][-lookback:]
    if len(recent) < 2:
        return None
    labels = {s['label'] for s in recent}
    if labels <= {'HH', 'HL'}:
        return 'uptrend'
    if labels <= {'LH', 'LL'}:
        return 'downtrend'
    return 'choppy'


def last_break(labeled_swings, lookback=4):
    """The most recent labeled swing whose label contradicts the trend the
    `lookback` swings just before it established - e.g. a fresh LL right
    after a run of HH/HL, the textbook 'break of structure' signal. Uses
    only the recent window, not the entire history, so an old regime
    doesn't mask a real recent reversal. None if the latest swing doesn't
    contradict that recent trend, or too few swings exist."""
    recent = [s for s in labeled_swings if s['label']]
    if len(recent) < 3:
        return None
    latest = recent[-1]
    prior_state = trend_state(recent[:-1], lookback=lookback)
    if prior_state == 'uptrend' and latest['label'] in ('LH', 'LL'):
        return latest
    if prior_state == 'downtrend' and latest['label'] in ('HH', 'HL'):
        return latest
    return None


def weekly_from_daily(daily_bars):
    """Resamples already-blindness-safe daily OHLC bars (oldest first) into
    weekly bars (ISO week, Monday-Sunday), computed locally rather than via
    a second live Yahoo weekly-interval request - one less thing to trust,
    and it can never leak data past S since it only ever sees bars the
    caller already filtered through S. The most recent bucket is a partial
    week when S falls mid-week; that's correct under the blindness rule,
    not a bug - a Wednesday read should not pretend the week is finished.
    """
    weeks = {}
    order = []
    for ts, o, h, l, c in daily_bars:
        d = date.fromisoformat(ts[:10])
        key = d.isocalendar()[:2]  # (iso_year, iso_week)
        if key not in weeks:
            weeks[key] = [ts, o, h, l, c]
            order.append(key)
        else:
            wk = weeks[key]
            wk[2] = max(wk[2], h)
            wk[3] = min(wk[3], l)
            wk[4] = c  # last close seen so far this week
    return [tuple(weeks[k]) for k in order]


def structure_signal(bars, n=3, lookback=4):
    """One call: OHLC bars -> the full computed read.

    {'state': 'uptrend'|'downtrend'|'choppy'|None, 'swings': [...],
     'lastBreak': {...}|None, 'n': n, 'lookback': lookback, 'bars': len(bars),
     'note': str|None}
    """
    min_bars = 2 * n + 1
    if len(bars) < min_bars:
        return dict(state=None, swings=[], lastBreak=None, n=n, lookback=lookback,
                    bars=len(bars), note=f"{MIN_BARS_NOTE} (need {min_bars}, have {len(bars)})")
    labeled = label_structure(find_swings(bars, n=n))
    return dict(state=trend_state(labeled, lookback=lookback), swings=labeled,
                lastBreak=last_break(labeled, lookback=lookback), n=n, lookback=lookback,
                bars=len(bars), note=None)


CATEGORY_NAME = "Market structure (HH/HL)"

_STATE_SIDE = {'uptrend': 'bull', 'downtrend': 'bear', 'choppy': 'neu'}


def vote_from_signal(sig, timeframe_label):
    """The mechanical vote for the Market structure category: this reports
    a computed fact, not a judgment call, so it is never left for a model
    to write. uptrend always votes bull, downtrend always votes bear,
    choppy or an unreadable series (too few bars) always votes neu - there
    is no discretion here by design."""
    state = sig.get('state') if sig else None
    side = _STATE_SIDE.get(state, 'neu')

    if state is None:
        reason = f"{timeframe_label} structure: {(sig or {}).get('note') or 'no read available'}."
    elif state == 'choppy':
        reason = f"{timeframe_label} structure is choppy - no consistent run of higher or lower swings."
    else:
        recent = [s for s in sig['swings'] if s['label']][-sig['lookback']:]
        labels = '/'.join(s['label'] for s in recent) or state
        brk = ''
        if sig.get('lastBreak'):
            brk = f" (a break of structure just printed: {sig['lastBreak']['label']})"
        reason = f"{timeframe_label} structure is {state} - last labeled swings: {labels}{brk}."

    return [side, reason]


def structure_breaks(bars, n=3, break_on='close', lookback=STRUCTURE_LOOKBACK):
    """Price-level breaks of structure, oldest first - see
    docs/market-structure-spec.md section 3. Unlike last_break (a label
    read, kept as-is for the golden board), this fires on the bar whose
    close (or wick, break_on='wick') crosses the most recent CONFIRMED
    swing level - a swing at i only counts from bar i+n, so nothing here
    uses a bar the caller couldn't have seen yet.

    Each event is classified against the trend in force before it: the
    previous break's direction if there is one, else trend_state of the
    swings confirmed so far. With the trend -> 'BOS' (continuation),
    against it -> 'CHoCH' (change of character), no trend -> 'break'.
    Each swing level can be broken only once.

    [{'i', 'ts', 'kind', 'direction': 'bull'|'bear', 'level', 'ref_swing_i',
      'close', 'protected'}, ...] - 'protected' is the latest confirmed swing
    on the other side (the low under a bullish break, the high over a
    bearish one): the level whose loss would undo the break, or None.
    """
    swings = label_structure(find_swings(bars, n=n))
    events = []
    confirmed = []
    unbroken = {'high': None, 'low': None}
    latest = {'high': None, 'low': None}
    prev_dir = None
    si = 0
    for t, (ts, o, h, l, c) in enumerate(bars):
        while si < len(swings) and swings[si]['i'] + n <= t:
            s = swings[si]
            confirmed.append(s)
            unbroken[s['type']] = latest[s['type']] = s
            si += 1
        up_px = c if break_on == 'close' else h
        dn_px = c if break_on == 'close' else l
        for direction, side, other, hit in (
                ('bull', 'high', 'low', unbroken['high'] and up_px > unbroken['high']['price']),
                ('bear', 'low', 'high', unbroken['low'] and dn_px < unbroken['low']['price'])):
            if not hit:
                continue
            if prev_dir is not None:
                kind = 'BOS' if direction == prev_dir else 'CHoCH'
            else:
                state = trend_state(confirmed, lookback=lookback)
                with_trend = {'uptrend': 'bull', 'downtrend': 'bear'}.get(state)
                kind = 'break' if with_trend is None else ('BOS' if direction == with_trend else 'CHoCH')
            ref = unbroken[side]
            events.append(dict(i=t, ts=ts, kind=kind, direction=direction, level=ref['price'],
                               ref_swing_i=ref['i'], close=c,
                               protected=latest[other]['price'] if latest[other] else None))
            unbroken[side] = None
            prev_dir = direction
    return events

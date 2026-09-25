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

"""Multi-timeframe buy/sell scanner: weekly / daily / 1h / 15m structure.

Each timeframe gets the same read mtl.structure already makes for the
board - swing highs/lows labeled HH/HL/LH/LL, classified uptrend /
downtrend / choppy - plus the price-level break read (structure_breaks)
to spot the moment a timeframe flips direction.

Two setups, one per trading timeframe, each mirrored for longs and shorts:

- 'daily'  trade: weekly + daily in an uptrend (HH/HL), and the 1h chart
               just printed a bullish CHoCH (closed above its last swing
               high after a bearish run) -> BUY. Mirror: weekly + daily in
               a downtrend (LH/LL), 1h just printed a bearish CHoCH -> SELL.
- 'hourly' trade: the same with weekly + daily + 1h as context and the
               15m chart as the trigger.

"Just" = within the trigger timeframe's last `recent_bars` bars, and price
still on the far side of the broken level (a CHoCH that's already been
given back is not a live signal). Verdicts: BUY / SELL (context aligned +
fresh flip), WATCH (context aligned, no flip yet), NO (the higher
timeframes aren't all up or all down).

Everything except fetch_series()/scan() is pure and network-free, so the
logic is testable on synthetic bars.
"""
from datetime import datetime, timedelta, timezone

from mtl.structure import (STRUCTURE_LOOKBACK, structure_breaks, structure_signal,
                           weekly_from_daily)

TIMEFRAMES = ('weekly', 'daily', '1h', '15m')

SWING_N = {'weekly': 2, 'daily': 3, '1h': 3, '15m': 3}

SETUPS = {
    'daily': dict(context=('weekly', 'daily'), trigger='1h', recent_bars=7),
    'hourly': dict(context=('weekly', 'daily', '1h'), trigger='15m', recent_bars=8),
}

# Yahoo interval + history period per fetched series (15m is capped at ~60d,
# 60m at ~730d by Yahoo). Weekly is resampled locally from the daily series.
_FETCH = {'daily': ('1d', '5y', timedelta(days=1)),
          '1h': ('60m', '180d', timedelta(hours=1)),
          '15m': ('15m', '30d', timedelta(minutes=15))}


def _fresh_choch(bars, last, direction, recent_bars):
    if not (recent_bars and last and last['kind'] == 'CHoCH' and last['direction'] == direction):
        return False
    if len(bars) - 1 - last['i'] >= recent_bars:
        return False
    close = bars[-1][4]
    return close > last['level'] if direction == 'bull' else close < last['level']


def tf_read(bars, n, recent_bars=None, lookback=STRUCTURE_LOOKBACK):
    """One timeframe's read: trend state, latest break, and whether it has
    freshly flipped bullish / bearish (a CHoCH that way within the last
    `recent_bars` bars, with the close still beyond the broken level)."""
    sig = structure_signal(bars, n=n, lookback=lookback)
    breaks = structure_breaks(bars, n=n, lookback=lookback) if bars else []
    last = breaks[-1] if breaks else None
    labels = [s['label'] for s in sig['swings'] if s['label']][-lookback:]
    return dict(state=sig['state'], labels=labels, lastBreak=last,
                flippedBull=_fresh_choch(bars, last, 'bull', recent_bars),
                flippedBear=_fresh_choch(bars, last, 'bear', recent_bars),
                close=bars[-1][4] if bars else None,
                barsAgo=(len(bars) - 1 - last['i']) if last else None,
                bars=len(bars), note=sig['note'])


_SIDES = {
    'uptrend': dict(side='buy', verdict='BUY', direction='bull', word='bullish',
                    flag='flippedBull', past='above'),
    'downtrend': dict(side='sell', verdict='SELL', direction='bear', word='bearish',
                      flag='flippedBear', past='below'),
}


def evaluate_setup(reads, setup):
    """reads: {timeframe: tf_read(...)}; setup: an entry of SETUPS.
    Returns {'verdict': 'BUY'|'SELL'|'WATCH'|'NO', 'side': 'buy'|'sell'|None,
    'reason': str, 'entry': float|None, 'stop': float|None}. The context
    timeframes must all be uptrend (buy side) or all downtrend (sell side);
    the stop is the swing on the far side of the trigger break (the low
    under a bullish CHoCH, the high over a bearish one)."""
    states = {reads[tf]['state'] for tf in setup['context']}
    sd = _SIDES.get(states.pop()) if len(states) == 1 else None
    if sd is None:
        why = ', '.join(f"{tf} {reads[tf]['state'] or 'unreadable'}" for tf in setup['context'])
        return dict(verdict='NO', side=None, reason=f"higher timeframes not aligned: {why}",
                    entry=None, stop=None)
    ctx = f"{'+'.join(setup['context'])} {'uptrend' if sd['side'] == 'buy' else 'downtrend'}"
    tg = setup['trigger']
    trig = reads[tg]
    b = trig['lastBreak']
    if trig[sd['flag']]:
        return dict(verdict=sd['verdict'], side=sd['side'],
                    reason=(f"{ctx}; {tg} flipped {sd['word']} {trig['barsAgo']} bar(s) ago "
                            f"(closed {sd['past']} {b['level']:.4g})"),
                    entry=trig['close'], stop=b['protected'])
    if b and b['direction'] == sd['direction']:
        tail = f"last {tg} break was a {sd['word']} {b['kind']} {trig['barsAgo']} bar(s) ago - not a fresh flip"
    else:
        tail = f"waiting for {tg} to flip {sd['word']} ({trig['state'] or 'unreadable'} now)"
    return dict(verdict='WATCH', side=sd['side'], reason=f"{ctx}; {tail}", entry=None, stop=None)


def drop_forming(bars, bar_len, now):
    """Drops the last bar if it hasn't closed yet (its start + bar_len is
    after `now`) - a forming bar's close can still change, and a break
    called on it can repaint."""
    if bars and datetime.fromisoformat(bars[-1][0]) + bar_len > now:
        return bars[:-1]
    return bars


def reads_from_bars(series, lookback=STRUCTURE_LOOKBACK):
    """series: {'daily': bars, '1h': bars, '15m': bars} -> {timeframe: tf_read}.
    lookback = how many recent labeled swings must all agree for an
    up/downtrend (4 = the board's strict read; 2 = just the latest pair)."""
    series = dict(series, weekly=weekly_from_daily(series['daily']))
    recent = {s['trigger']: s['recent_bars'] for s in SETUPS.values()}
    return {tf: tf_read(series[tf], SWING_N[tf], recent.get(tf), lookback) for tf in TIMEFRAMES}


def scan_bars(series, lookback=STRUCTURE_LOOKBACK):
    reads = reads_from_bars(series, lookback)
    return dict(timeframes=reads,
                setups={name: evaluate_setup(reads, s) for name, s in SETUPS.items()})


def fetch_series(ticker, now=None, include_forming=False):
    from mtl.fetch import fetch_ohlc
    now = now or datetime.now(timezone.utc)
    out = {}
    for tf, (interval, period, bar_len) in _FETCH.items():
        bars = fetch_ohlc(ticker, interval=interval, period=period)
        out[tf] = bars if include_forming else drop_forming(bars, bar_len, now)
    return out


def scan(ticker, now=None, include_forming=False, lookback=STRUCTURE_LOOKBACK):
    return dict(ticker=ticker, **scan_bars(fetch_series(ticker, now, include_forming), lookback))

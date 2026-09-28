"""The "latest read": the mechanical half of an asset's trend note, recomputed
on every refresh run from whatever bars exist right now.

A published board's notes are frozen at write time on purpose - they are
the basis the call is graded against (the blindness rule), so nothing here
ever touches documents/<date>.json. This is a display overlay alongside
them, like live.json's prices: the same moving averages, RSI and swing
structure prepare_daily.py computes for the board, but through the latest
bar (including today's still-forming one) instead of through S. Unscored.

Pure - takes bars, returns a dict - so it's testable without Yahoo; the
fetching lives in scripts/fetch_live.py.
"""
from mtl.fetch import rsi14, sma
from mtl.structure import (HOURLY_SWING_N, STRUCTURE_LOOKBACK, WEEKLY_SWING_N,
                           structure_signal, vote_from_signal, weekly_from_daily)

CHART_CANDLES = 400  # hourly candles kept for the report page's chart


def _compact(sig):
    """structure_signal() output trimmed to what the page shows - the full
    swing list is ~60 days of hourly swings per asset, far more than
    live.json needs to carry. vote_from_signal/structure_badge only ever
    look at the last `lookback` labeled swings, state and lastBreak."""
    labeled = [s for s in sig['swings'] if s['label']][-sig['lookback']:]
    return dict(state=sig['state'], lastBreak=sig['lastBreak'], lookback=sig['lookback'],
                note=sig['note'], bars=sig['bars'],
                swings=[dict(ts=s['ts'], type=s['type'], price=s['price'], label=s['label'])
                        for s in labeled])


def latest_read(ticker, hourly_bars, daily_bars):
    """hourly_bars / daily_bars: fetch_ohlc() rows, oldest first, through
    whatever the latest bar is. Returns None when there's no daily history."""
    if not daily_bars:
        return None
    closes = [b[4] for b in daily_bars]
    hourly = structure_signal(hourly_bars, n=HOURLY_SWING_N, lookback=STRUCTURE_LOOKBACK)
    weekly = structure_signal(weekly_from_daily(daily_bars), n=WEEKLY_SWING_N,
                              lookback=STRUCTURE_LOOKBACK)
    last_ts = (hourly_bars[-1][0] if hourly_bars else daily_bars[-1][0])
    return dict(ticker=ticker, price=closes[-1], barTs=last_ts,
                ma50=sma(closes, 50), ma200=sma(closes, 200), rsi14=rsi14(closes),
                hourly=_compact(hourly), weekly=_compact(weekly),
                # [ts, o, h, l, c] - the last one can still be forming
                bars=[[b[0]] + [round(x, 4) for x in b[1:5]]
                      for b in hourly_bars[-CHART_CANDLES:]])


def _vs(price, ma, label):
    if ma is None:
        return None
    return f"{'above' if price > ma else 'below' if price < ma else 'at'} its {label} of {ma:,.2f}"


def latest_note(read):
    """One-paragraph plain-text version of the read, in the same shape as
    the board's Trend structure note."""
    if not read:
        return None
    parts = [p for p in (_vs(read['price'], read.get('ma50'), '50-day average'),
                         _vs(read['price'], read.get('ma200'), '200-day')) if p]
    head = f"{read['ticker']} at {read['price']:,.2f}"
    if parts:
        head += ", " + " and ".join(parts)
    if read.get('rsi14') is not None:
        head += f", with RSI(14) at {read['rsi14']:.2f}"
    return " ".join([head + ".",
                     vote_from_signal(read.get('hourly'), '1H')[1],
                     vote_from_signal(read.get('weekly'), 'Weekly')[1]])

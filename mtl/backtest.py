"""Backtest of the multi-timeframe structure setups in mtl/mtf.py.

Rules, per ticker, per setup, run separately for longs and shorts:

- Long entry: the trigger timeframe prints a bullish CHoCH (structure_breaks)
  while every context timeframe is in an uptrend. Fill at that bar's close.
- Long exit: the trigger timeframe's next bearish break (after a bullish
  CHoCH the next bearish break is, by definition, a bearish CHoCH - "the
  smaller timeframe changed to bearish"). Fill at that bar's close.
- Shorts mirror both: downtrend context + bearish CHoCH in, next bullish
  break out. Return = (entry - exit) / entry.

No look-ahead anywhere: a context timeframe's state at time E is computed
only from its bars that had closed by E, using only swings already
confirmed (a fractal swing at i only exists from bar i+n). structure_breaks
is itself point-in-time. Every bar carries an explicit end time to make
that comparison exact.

Pure and network-free; scripts/backtest.py fetches the bars.
"""
from bisect import bisect_right
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from mtl.structure import find_swings, label_structure, structure_breaks, trend_state

ET = ZoneInfo('America/New_York')
SESSION_CLOSE = time(16, 0)

SWING_N = {'weekly': 2, 'daily': 3, '1h': 3, '15m': 3}

SETUPS = {
    # The live scanner's two setups (mtl/mtf.py SETUPS), exact.
    'daily': dict(context=('weekly', 'daily'), trigger='1h',
                  label='Daily trade: W+D context, 1h trigger/exit'),
    'hourly': dict(context=('weekly', 'daily', '1h'), trigger='15m',
                   label='Hourly trade: W+D+1h context, 15m trigger/exit'),
}


def daily_end(ts):
    """A daily bar's close time: 4pm ET on its date."""
    return datetime.combine(datetime.fromisoformat(ts[:10]).date(), SESSION_CLOSE, ET)


def with_ends(bars, bar_len=None):
    """[(bar, end_datetime)]-style parallel list of end times. Daily bars
    end at 4pm ET on their date; intraday bars at start + bar_len."""
    if bar_len is None:
        return [daily_end(b[0]) for b in bars]
    out = []
    for b in bars:
        start = datetime.fromisoformat(b[0])
        if start.tzinfo is None:
            start = start.replace(tzinfo=ET)
        # the session's last hourly bar starts 3:30pm but closes at 4pm, not 4:30
        close = datetime.combine(start.astimezone(ET).date(), SESSION_CLOSE, ET)
        end = start + bar_len
        out.append(close if start < close < end else end)
    return out


def resample(daily_bars, period):
    """Daily bars -> weekly ('W', ISO week) or monthly ('M') bars, plus each
    bucket's end time (the close of its last daily bar). Only used
    point-in-time via those end times, so a bucket is never read before
    it has finished."""
    buckets, order = {}, []
    for ts, o, h, l, c in daily_bars:
        d = datetime.fromisoformat(ts[:10]).date()
        key = d.isocalendar()[:2] if period == 'W' else (d.year, d.month)
        if key not in buckets:
            buckets[key] = [ts, o, h, l, c, ts]
            order.append(key)
        else:
            b = buckets[key]
            b[2], b[3], b[4], b[5] = max(b[2], h), min(b[3], l), c, ts
    bars = [tuple(buckets[k][:5]) for k in order]
    ends = [daily_end(buckets[k][5]) for k in order]
    return bars, ends


def state_series(bars, n, lookback):
    """states[k] = the trend state a reader would have seen with bars[0..k]:
    trend_state over swings confirmed by k (swing index + n <= k). Same
    answer as structure_signal(bars[:k+1]) for every k, in one pass."""
    swings = label_structure(find_swings(bars, n=n))
    states, labeled, si = [], [], 0
    for k in range(len(bars)):
        while si < len(swings) and swings[si]['i'] + n <= k:
            if swings[si]['label']:
                labeled.append(swings[si])
            si += 1
        states.append(trend_state(labeled[-lookback:], lookback=lookback))
    return states


class Context:
    """A context timeframe's point-in-time trend state lookup."""

    def __init__(self, bars, ends, n, lookback):
        self.ends = ends
        self.states = state_series(bars, n, lookback)

    def at(self, when):
        k = bisect_right(self.ends, when) - 1
        return self.states[k] if k >= 0 else None


def simulate(series, setup, lookback, start, ticker='', stake=100.0):
    """series: {tf: (bars, ends)} for every timeframe the setup uses.
    Returns a list of trade dicts (closed and still-open)."""
    trig = setup['trigger']
    bars, ends = series[trig]
    if not bars:
        return []
    ctx = {tf: Context(*series[tf], SWING_N[tf], lookback) for tf in setup['context']}
    pos = {'long': None, 'short': None}
    trades = []

    def close(side, b_i, reason):
        p = pos[side]
        px = bars[b_i][4]
        ret = (px - p['entry']) / p['entry'] if side == 'long' else (p['entry'] - px) / p['entry']
        trades.append(dict(p, exitTime=ends[b_i].isoformat(), exit=px, ret=ret, pnl=stake * ret,
                           bars=b_i - p['_i'], open=reason == 'open'))
        pos[side] = None

    for b in structure_breaks(bars, n=SWING_N[trig], lookback=lookback):
        i, d = b['i'], b['direction']
        if pos['long'] and d == 'bear':
            close('long', i, 'flip')
        if pos['short'] and d == 'bull':
            close('short', i, 'flip')
        if b['kind'] != 'CHoCH' or ends[i] < start:
            continue
        side, want = ('long', 'uptrend') if d == 'bull' else ('short', 'downtrend')
        if pos[side]:
            continue
        states = {tf: c.at(ends[i]) for tf, c in ctx.items()}
        if all(s == want for s in states.values()):
            pos[side] = dict(ticker=ticker, side=side, entryTime=ends[i].isoformat(),
                             entry=bars[i][4], _i=i)
    for side in ('long', 'short'):
        if pos[side]:
            close(side, len(bars) - 1, 'open')
    for t in trades:
        t.pop('_i', None)
    return trades


def summarize(trades):
    """Aggregate stats over closed trades: count, win rate, average /
    median % return, total P&L on the stake, best / worst, average bars
    held, and a compounded-growth figure for one stake rolled trade to
    trade in time order (a rough "what would $100 have become")."""
    closed = sorted((t for t in trades if not t['open']), key=lambda t: t['exitTime'])
    if not closed:
        return dict(trades=0)
    rets = sorted(t['ret'] for t in closed)
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    mid = len(rets) // 2
    median = rets[mid] if len(rets) % 2 else (rets[mid - 1] + rets[mid]) / 2
    gross_win, gross_loss = sum(wins), -sum(losses)
    return dict(
        trades=len(closed), winRate=len(wins) / len(closed),
        avgRet=sum(rets) / len(rets), medianRet=median,
        avgWin=gross_win / len(wins) if wins else 0.0,
        avgLoss=-gross_loss / len(losses) if losses else 0.0,
        profitFactor=gross_win / gross_loss if gross_loss else None,
        totalPnl=sum(t['pnl'] for t in closed),
        best=rets[-1], worst=rets[0],
        avgBars=sum(t['bars'] for t in closed) / len(closed),
        stillOpen=sum(t['open'] for t in trades),
    )


def portfolio_index(trades, daily_closes, calendar, start_value=100.0):
    """Growth of `start_value` for one account that splits itself equally
    across every trade open on a given day (in cash when none are open),
    so the strategy can sit on the same chart as buying and holding an
    index. Each trade is marked at the daily close of every session it
    spans: entry price -> that day's close -> ... -> exit price on its exit
    day. A short's daily return is the negative of the price change.

    trades: closed trade dicts from simulate(); daily_closes: {ticker:
    {'YYYY-MM-DD': close}} on the same (split-adjusted) basis as the
    trade prices; calendar: sorted session dates to report.
    Returns [[date, value, open_positions], ...]."""
    sums, counts = {}, {}
    for t in trades:
        if t['open']:
            continue
        closes = daily_closes.get(t['ticker'], {})
        d0, d1 = t['entryTime'][:10], t['exitTime'][:10]
        path = [(d, closes[d]) for d in calendar if d0 <= d < d1 and d in closes]
        path.append((d1, t['exit']))
        prev = t['entry']
        sign = 1.0 if t['side'] == 'long' else -1.0
        for d, px in path:
            r = sign * (px / prev - 1.0)
            sums[d] = sums.get(d, 0.0) + r
            counts[d] = counts.get(d, 0) + 1
            prev = px
    value, out = start_value, []
    for d in calendar:
        if counts.get(d):
            value *= 1.0 + sums[d] / counts[d]
        out.append([d, value, counts.get(d, 0)])
    return out


def growth(points, start_value=100.0):
    """[[date, close], ...] -> [[date, value]] for start_value bought at
    the first close and held."""
    if not points:
        return []
    base = points[0][1]
    return [[d, start_value * c / base] for d, c in points]


def curve_stats(values, sessions_per_year=252):
    """Total return, annualized return and max drawdown of a value series."""
    if len(values) < 2:
        return dict(total=None, annual=None, maxDD=None)
    total = values[-1] / values[0] - 1.0
    years = (len(values) - 1) / sessions_per_year
    annual = (1.0 + total) ** (1.0 / years) - 1.0 if years >= 0.5 and total > -1 else None
    peak, dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1.0)
    return dict(total=total, annual=annual, maxDD=dd)


def consistent(trade, daily_ranges, tol=0.02):
    """False when the trade's entry or exit price sits outside that day's
    daily low-high range (with `tol` slack) - the intraday and daily
    series disagree about what the ticker even is. Real case: Yahoo's
    hourly "BNY" history before Bank of New York Mellon took that symbol
    in 2024 is a ~$10 fund, while its daily "BNY" history is the ~$55
    bank; marking one against the other invents +400% days. Trades on a
    day with no daily bar are kept."""
    ranges = daily_ranges.get(trade['ticker'], {})
    for when, px in ((trade['entryTime'], trade['entry']), (trade['exitTime'], trade['exit'])):
        r = ranges.get(when[:10])
        if r and not (r[0] * (1 - tol) <= px <= r[1] * (1 + tol)):
            return False
    return True

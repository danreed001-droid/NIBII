"""The rebound rule of Boost + rotation (the default plan): stay in stocks after a deep drop that has started to turn.

While all three hold at a close, the plan holds the Boost list whatever its other rules say (the rotation, the
downtrend and lower-high exits, the whipsaw half-switch, the narrow-market cash week):

1. SPY closes REB_DROP (12%) or more under its highest close of the last REB_LOOK (63) sessions;
2. gold or bonds (the better of GLD / TLT) is up REB_HAVEN (2%) or more since the day of that high: money has
   run to safety, the kind of drop that has rebounded hard (2001, 2002, 2009, 2011, 2016, 2020);
3. SPY's daily chart (swings REB_SWING days either side) has made a higher low since that high: its last
   swing low is above the one before it, so the selling has started to dry up.

Decided at the close, traded at the next close, like the rest of the plan. Without the third check the rule
stayed in stocks through the October 2008 collapse (worst drop -40% instead of -33%).

Audit (research/backtest, point-in-time S&P 500, 0.15% slippage): 37.8% a year from 2000 vs 36.5% without
it, 39.2% vs 38.0% from 2010, 47.3% vs 47.0% from 2016, 69.7% vs 67.6% from 2020; worst drop -33% either way
(-33.4% in 2001-02, about 2 points deeper than before because of two days in stocks in October 2001). It
overrode the other rules on 70 sessions since 2000 (Oct 2001, Aug-Sep 2002, late 2008 to Jan 2009, Aug-Sep 2011,
Feb 2016, May 2020), most of the gain in late 2008 and early 2009; 1.0 point a year, t-stat 0.8 on monthly
returns. On the index alone (Oct 14, 2026): the S&P 500 in 1962-1999 was higher 3 months after all 6 signals;
abroad (US bonds and gold as the havens) the signal beat other deep drops in the UK, Germany and Japan but not
Canada, and as a re-entry on a 150-day timing rule it deepened the worst drop in Japan, Germany and Hong Kong; in
1928-1961, with no haven prices, the drop and higher low alone failed in the 1930s. So treat it as on probation:
one more crash that bottoms differently could undo it."""
from bisect import bisect_right

from mtl.structure import find_swings

REB_DROP = 0.12      # SPY this far under its highest close of the last REB_LOOK sessions
REB_LOOK = 63        # sessions (3 months)
REB_HAVEN = 0.02     # the better of GLD / TLT up at least this much since the day of that high
REB_SWING = 3        # daily swings: days either side
REB_DAILY = 320      # daily bars the swings are read from
REB_ASSETS = ('TLT', 'GLD')


def reading(spy_bars, havens, calendar, k, closes=None, bdays=None):
    """The rule's reading at calendar[k]: dict(drop, high=[date, close], haven={asset: change since the high},
    best, lows=[[date, low], [date, low]] (the last two daily swing lows), hl, on). spy_bars: [(date, o, h,
    l, c)] adjusted; havens: {asset: {date: close}} (filled); closes / bdays: SPY {date: close} and the bars'
    dates (built if None)."""
    if k < REB_LOOK - 1:
        return None
    if closes is None:
        closes = {b[0]: b[4] for b in spy_bars}
    win = [closes.get(d) for d in calendar[k - REB_LOOK + 1:k + 1]]
    if None in win:
        return None
    hi = max(win)
    hd = calendar[k - REB_LOOK + 1 + win.index(hi)]
    d = calendar[k]
    drop = 1 - win[-1] / hi
    hv = {t: havens[t][d] / havens[t][hd] - 1 for t in REB_ASSETS
          if havens.get(t) and havens[t].get(d) and havens[t].get(hd)}
    best = max(hv.values()) if hv else None
    j = bisect_right(bdays if bdays is not None else [b[0] for b in spy_bars], d)
    lows = [x for x in find_swings([tuple(b) for b in spy_bars[max(0, j - REB_DAILY):j]], n=REB_SWING) if x['type'] == 'low']
    last2 = [[x['ts'][:10], round(x['price'], 2)] for x in lows[-2:]]
    hl = len(lows) >= 2 and lows[-1]['price'] > lows[-2]['price'] and lows[-1]['ts'][:10] >= hd
    on = drop >= REB_DROP and best is not None and best >= REB_HAVEN and hl
    return dict(drop=round(drop, 4), high=[hd, round(hi, 2)], haven={t: round(v, 4) for t, v in hv.items()},
                best=None if best is None else round(best, 4), lows=last2, hl=bool(hl), on=bool(on))


def rebound_days(spy_bars, havens, calendar, start):
    """The decision days from `start` on which the rule holds stocks."""
    closes, bdays = {b[0]: b[4] for b in spy_bars}, [b[0] for b in spy_bars]
    out = set()
    for k, d in enumerate(calendar):
        if d < start:
            continue
        r = reading(spy_bars, havens, calendar, k, closes, bdays)
        if r and r['on']:
            out.add(d)
    return out


def apply_rebound(modes, why, half, days, calendar):
    """New (modes, why, half, held): the Boost list on the rule's days whatever the plan would hold (and no
    whipsaw half), with the switch reasons 'rebound' (into stocks) and 'rebound-end' (back to what the plan
    holds); held = the days the rule changed the holding."""
    m, w, h = dict(modes), dict(why), dict(half or {})
    held, prev = set(), None
    for d in calendar:
        if d not in modes and d not in days:
            continue
        if d in days:
            if m.get(d, 'boost') != 'boost' or d in h:
                if prev != 'rebound':
                    w[d] = 'rebound'
                m[d] = 'boost'
                h.pop(d, None)
                held.add(d)
                prev = 'rebound'
            else:
                prev = 'plan'      # the plan holds stocks anyway: nothing to override
        else:
            if prev == 'rebound' and m.get(d, 'boost') != 'boost':
                w[d] = 'rebound-end'
            prev = 'plan'
    return m, w, h, held


def rebound_state(spy_bars, havens, calendar, k, held, n=6):
    """For the scanner: today's reading, whether the rule is holding stocks over another rule today (active),
    and the last n stretches it did ([first, last] decision days; held from apply_rebound)."""
    r = reading(spy_bars, havens, calendar, k) or dict(on=False)
    runs = []
    for d in sorted(held):
        i = calendar.index(d)
        if runs and calendar.index(runs[-1][1]) == i - 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    return dict(r, active=calendar[k] in held, log=runs[::-1][:n], n=len(runs),
                drop_th=REB_DROP, look=REB_LOOK, haven_th=REB_HAVEN, swing=REB_SWING)

"""Two-scale (fractal) buy rules of Boost + rotation (the default plan, since Oct 26, 2026, on probation).

The same chart pattern has to show on two time scales before a rule acts: SPY's weekly swings and its daily swings
(mtl.rotation.Reader: 2-bar weekly swings, 3-bar daily swings).

1. Buy freeze. At a week's last close, SPY is within FZ_NEAR (1%) of its latest weekly swing high, that high is lower
   than the weekly swing high before it, and SPY's daily chart also shows a lower high (its last daily swing high
   below the one before). For the next FZ_DAYS (10) sessions the plan buys no new stocks: holdings are kept, and a slot
   left empty at a trade inside the freeze holds the haven pick (the better of TLT / GLD over 3 months if it is up,
   else DBMF managed futures, else cash) until the next trade.
2. Green light. At a week's last close, SPY's weekly swing lows are rising (the last above the one before), SPY is
   within GL_NEAR (3%) above that last weekly low, and its daily chart also shows a higher low. For the next GL_DAYS
   (10) sessions the narrow-market cash week is skipped and the buy filters (the fading-energy filter and the buy
   freeze) stand aside, so empty slots fill at once.

Both are decided at a close and act from the next close, like the rest of the plan.

Backtests (Oct 24, 2026). On today's S&P 500 members (0.05% per side) the two made 47.8% a year from 2000 vs 45.9%
without them, 55.1% vs 52.6% from 2010, 68.4% vs 66.4% from 2016 and 93.2% vs 90.5% from 2020, worst drop -28% either
way. On the members at each date, including companies that later left the index (the track-record engine, 0.15% per
side), they were about level: 44.5% vs 44.8% from 2000, 47.1% vs 46.8% from 2010, 54.6% vs 55.0% from 2016, 83.2% vs
81.8% from 2020, worst drop -29% either way. Abroad (10 markets plus China) the freeze alone was about level (+0.07
points a year, ahead in 6 and behind in 5). Weekly lower highs alone, without the daily confirmation, froze buys 294
times and lost 1-14 points a year. A third rule tested with them, no new buy of a stock whose own weekly and daily
charts both show a lower high, was live for no sessions: it cost 1-3 points a year on the members at each date and
was dropped before Oct 26. Picked after many tests on the same history and no better than level on the stricter
test: treat it as on probation."""
from datetime import date

from mtl.calendar_nyse import week_ended
from mtl.rotation import Reader

FZ_NEAR = 0.01     # buy freeze: SPY within this of its latest (lower) weekly swing high
FZ_DAYS = 10       # sessions without new buys after a freeze signal
GL_NEAR = 0.03     # green light: SPY within this above its latest (higher) weekly swing low
GL_DAYS = 10       # sessions the green light lasts


def _week_end(calendar, k):
    if k + 1 < len(calendar):
        return date.fromisoformat(calendar[k + 1]).isocalendar()[:2] != date.fromisoformat(calendar[k]).isocalendar()[:2]
    return week_ended(calendar[k])


def _swings(R, t, d, tf, kind):
    return [x for x in R.labels(t, d, tf) if x['type'] == kind]


def spy_reading(R, d, close):
    """SPY's two-scale reading at close d: the last two weekly / daily swing highs and lows and whether the freeze and
    green-light patterns show."""
    wh, dh = _swings(R, 'SPY', d, 'w', 'high'), _swings(R, 'SPY', d, 'd', 'high')
    wl, dl = _swings(R, 'SPY', d, 'w', 'low'), _swings(R, 'SPY', d, 'd', 'low')
    freeze = (len(wh) >= 2 and wh[-1]['price'] < wh[-2]['price'] and close >= wh[-1]['price'] * (1 - FZ_NEAR)
              and len(dh) >= 2 and dh[-1]['price'] < dh[-2]['price'])
    green = (len(wl) >= 2 and wl[-1]['price'] > wl[-2]['price'] and close <= wl[-1]['price'] * (1 + GL_NEAR)
             and len(dl) >= 2 and dl[-1]['price'] > dl[-2]['price'])
    pair = lambda s: [[x['ts'][:10], round(x['price'], 2)] for x in s[-2:]]
    return dict(close=round(close, 2), freeze=bool(freeze), green=bool(green), wHigh=pair(wh), dHigh=pair(dh),
                wLow=pair(wl), dLow=pair(dl))


def spy_windows(spy_bars, calendar, start):
    """(frozen, green, log): calendar indices with no new buys / with the green light (each signal covers the next
    FZ_DAYS / GL_DAYS sessions, which may run past the end of `calendar`), and the signals ([date, 'freeze' |
    'green'], oldest first). Read at each week's last close from `start` on."""
    R = Reader({'SPY': [tuple(b) for b in spy_bars]})
    px = {b[0]: b[4] for b in spy_bars}
    frozen, green, log = set(), set(), []
    for k in range(1, len(calendar)):
        d = calendar[k]
        if d < start or d not in px or not _week_end(calendar, k):
            continue
        r = spy_reading(R, d, px[d])
        if r['freeze']:
            frozen.update(range(k + 1, k + 1 + FZ_DAYS))
            log.append([d, 'freeze'])
        if r['green']:
            green.update(range(k + 1, k + 1 + GL_DAYS))
            log.append([d, 'green'])
    return frozen, green, log


def buy_rule(base, frozen, green):
    """run_momentum's buy_when for the plan: the green light, or the base filter (fading energy) outside a buy freeze."""
    def ok(t, k):
        return k in green or ((base(t, k) if base else True) and k not in frozen)
    return ok


def slot_haven(stock_curve, picks, frozen, closes, calendar, start, pick, top_n=5, cost=0.0015):
    """The stock-list curve with each slot left empty at a trade inside a buy freeze held in pick(k) (the haven pick
    read at the close before the trade, or 'CASH'/None) until the next trade. stock_curve [[date, value]], picks
    [[date, holdings]] (trade days), closes {asset: {date: close}}. Costs `cost` on each change of that share."""
    fill = slot_fill(picks, frozen, calendar, start, pick, top_n)
    if not fill or not stock_curve:
        return [list(x) for x in stock_curve]
    out = [list(stock_curve[0])]
    for i in range(1, len(stock_curve)):
        d0, d1 = stock_curve[i - 1][0], stock_curve[i][0]
        a, f = fill.get(d0, (None, 0.0))
        r = stock_curve[i][1] / stock_curve[i - 1][1]
        if f:
            p0, p1 = (closes.get(a) or {}).get(d0), (closes.get(a) or {}).get(d1)
            if p0 and p1:
                r += f * (p1 / p0 - 1)
        f_prev = fill.get(stock_curve[i - 2][0], (None, 0.0))[1] if i >= 2 else 0.0
        out.append([d1, out[-1][1] * r * (1 - cost * abs(f - f_prev))])
    return out


def slot_fill(picks, frozen, calendar, start, pick, top_n=5):
    """{date: (asset, share)}: the empty-slot share held in the haven pick from that close to the next (see
    slot_haven)."""
    ix = {d: i for i, d in enumerate(calendar)}
    pk = sorted((d, len(h)) for d, h in picks)
    fill = {}
    for i, (d, n) in enumerate(pk):
        if d < start or ix.get(d) not in frozen:
            continue
        f = max(0.0, 1 - n / top_n)
        a = pick(ix[d] - 1) if f > 1e-6 else None
        if a in (None, 'CASH'):
            continue
        nxt = pk[i + 1][0] if i + 1 < len(pk) else None
        j = ix[d]
        while j < len(calendar) - 1 and (nxt is None or calendar[j] < nxt):
            fill[calendar[j]] = (a, f)
            j += 1
    return fill


def state(spy_bars, calendar, k, frozen, green, log, n=8):
    """For the scanner: today's SPY reading, whether a freeze / green light covers the next session (the one tonight's
    decision trades at) and until when, and the recent signals (newest first)."""
    R = Reader({'SPY': [tuple(b) for b in spy_bars]})
    px = {b[0]: b[4] for b in spy_bars}
    d = calendar[k]
    r = spy_reading(R, d, px[d]) if d in px else {}

    def until(win):
        if k + 1 not in win:
            return None
        j = k + 1
        while j + 1 in win:
            j += 1
        return j - k   # sessions from tonight's close
    return dict(r, weekEnd=_week_end(calendar, k), frozen=k + 1 in frozen, green=k + 1 in green,
                frozenFor=until(frozen), greenFor=until(green), log=log[::-1][:n], n=len(log),
                fzNear=FZ_NEAR, fzDays=FZ_DAYS, glNear=GL_NEAR, glDays=GL_DAYS)

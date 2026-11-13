"""The crash-call watch list for the scanner page (information only; nothing here changes the plan).

From the option study of Nov 13, 2026 (research, idea 253 and on): buying a 90-day at-the-money call on an S&P 500
stock whose 14-day RSI is at or below 30 while SPY is at least 20% under its highest close of the last year, and
selling it about two months later, paid +41% per $1 of premium on 2000-2012 and +103% on 2013-2026. The study priced
calls from each stock's realized volatility + 10 points (no historical option prices exist), so real prices, which jump in
a crash, can cut that a lot. The lower the RSI the better (no sweet spot in between); waiting for SPY to turn back above its
50-day average made it worse; it fired in about 97 weeks over 7 falls (2001-03, 2008-09, 2020, 2022), and 2008 lost
in every version (-34% at these settings).

watch(prices, calendar, eligible, k) -> {on, spy, spyHigh, dd, rows: [{t, rsi, off, vol, r21}], near: [...]}:
- on: SPY at least DROP under its 252-session high at session k;
- rows (while on): the eligible stocks with 14-day RSI <= RSI_MAX, lowest RSI first;
- near (always): the lowest RSIs tonight, so the page shows what the list would hold."""
import math

from mtl.rsi_line import rsi as rsi14

DROP = 0.20
RSI_MAX = 30.0
HOLD = 42          # sessions: sell about two months in
MAX_ROWS = 25


def _closes(px, calendar, k, n):
    out, last = [], None
    for d in calendar[max(0, k - n + 1):k + 1]:
        v = px.get(d)
        last = v if v else last
        out.append(last)
    return out


def watch(prices, calendar, eligible, k=None):
    k = len(calendar) - 1 if k is None else k
    d = calendar[k]
    spy = _closes(prices['SPY'], calendar, k, 252)
    spy = [v for v in spy if v]
    hi = max(spy) if spy else None
    dd = spy[-1] / hi - 1 if hi else None
    rows = []
    for t, px in prices.items():
        if t == 'SPY' or not eligible(t, d):
            continue
        c = _closes(px, calendar, k, 252)
        if len(c) < 70 or any(v is None for v in c[-64:]) or not c[-1]:
            continue
        r = rsi14(c[-64:])[-1]
        if r is None:
            continue
        lr = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 63, len(c))]
        m = sum(lr) / len(lr)
        vol = math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1)) * math.sqrt(252)
        hi_t = max(v for v in c if v)
        rows.append(dict(t=t, rsi=round(r, 1), off=round(c[-1] / hi_t - 1, 4), vol=round(vol, 3),
                         r21=round(c[-1] / c[-22] - 1, 4) if c[-22] else None))
    rows.sort(key=lambda x: x['rsi'])
    on = dd is not None and dd <= -DROP
    hits = [x for x in rows if x['rsi'] <= RSI_MAX]
    return dict(asOf=d, on=on, spy=round(spy[-1], 2) if spy else None, spyHigh=round(hi, 2) if hi else None,
                dd=round(dd, 4) if dd is not None else None, drop=DROP, rsiMax=RSI_MAX, hold=HOLD,
                count=len(hits), rows=hits[:MAX_ROWS] if on else [], near=rows[:8])

#!/usr/bin/env python3
"""Bitcoin, Oct 2015 - Oct 2016: what the year looked like, and which other
12-month stretches since then looked like it (and what came next).

1. The year itself: monthly returns, the legs up and pullbacks (swings of 15%+),
   distance from the 200-day average, volatility, where it sat in the 4-year
   halving cycle (halving 2016-07-09).
2. Shape match: every 365-day window since Oct 2016 is compared with the
   2015-16 path (log price, scaled to start at 0) - correlation of the two
   shapes; the best non-overlapping matches are listed with the next 6 and 12
   months after each.
3. Cycle match: the same position relative to a halving (2020-05-11, 2024-04-20).
4. The last 12 months compared with 2015-16.

Daily BTC-USD closes from Yahoo (from Sep 2014).

Usage:
    python scripts/study_btc_2015.py
"""
import math
from datetime import date, timedelta

import numpy as np

A, B = '2015-10-01', '2016-10-01'
HALVINGS = ['2012-11-28', '2016-07-09', '2020-05-11', '2024-04-20']


def load():
    import yfinance as yf
    h = yf.Ticker('BTC-USD').history(start='2014-09-01', auto_adjust=False)['Close']
    return [d.strftime('%Y-%m-%d') for d in h.index], np.array(h.values, float)


def swings(px, dates, th=0.15):
    """Alternating highs / lows where price reversed by `th` or more."""
    out, mode, ext, ei = [], None, px[0], 0
    for i, p in enumerate(px):
        if mode in (None, 'up'):
            if p > ext:
                ext, ei = p, i
            elif p < ext * (1 - th):
                out.append(('high', dates[ei], ext))
                mode, ext, ei = 'down', p, i
                continue
        if mode in (None, 'down'):
            if p < ext:
                ext, ei = p, i
            elif p > ext * (1 + th):
                out.append(('low', dates[ei], ext))
                mode, ext, ei = 'up', p, i
    out.append(('high' if mode == 'up' else 'low', dates[ei], ext))
    return out


def days_from(d, ref):
    return (date.fromisoformat(d) - date.fromisoformat(ref)).days


def main():
    dates, px = load()
    idx = {d: i for i, d in enumerate(dates)}
    ma200 = np.array([px[max(0, i - 199):i + 1].mean() for i in range(len(px))])
    a, b = idx[A], idx[B]
    w = px[a:b + 1]
    r = np.diff(np.log(w))
    print(f"BTC {A} → {B}: ${w[0]:,.0f} → ${w[-1]:,.0f}  ({w[-1] / w[0] - 1:+.0%})")
    pk = np.maximum.accumulate(w)
    print(f"  worst drop inside {np.min(w / pk - 1):.0%}, yearly volatility {r.std() * math.sqrt(365):.0%}, "
          f"days above the 200-day average {np.mean(px[a:b + 1] > ma200[a:b + 1]):.0%}")
    print(f"  high ${w.max():,.0f} on {dates[a + int(np.argmax(w))]}, low ${w.min():,.0f} on {dates[a + int(np.argmin(w))]}")
    print(f"  halving 2016-07-09: window ran from {days_from(A, '2016-07-09')} to +{days_from(B, '2016-07-09')} days around it; "
          f"the 2013 top was {days_from(A, '2013-12-04')} days before, the Jan 2015 low {days_from(A, '2015-01-14')} days before")
    print("\n  month    close   return")
    m_end = {}
    for i in range(a, b + 1):
        m_end[dates[i][:7]] = i
    prev = px[a]
    for m, i in sorted(m_end.items()):
        print(f"  {m}  ${px[i]:>7,.0f}  {px[i] / prev - 1:+6.0%}")
        prev = px[i]
    print("\n  legs (reversals of 15%+):")
    sw = swings(w, dates[a:b + 1])
    for k in range(1, len(sw)):
        t0, d0, p0 = sw[k - 1]
        t1, d1, p1 = sw[k]
        print(f"    {d0} ${p0:>6,.0f} → {d1} ${p1:>6,.0f}  {p1 / p0 - 1:+5.0%}  over {days_from(d1, d0)} days")
    print(f"\n  what came next: +6 months {px[min(len(px) - 1, b + 182)] / px[b] - 1:+.0%}, "
          f"+12 months {px[min(len(px) - 1, b + 365)] / px[b] - 1:+.0%} (to ${px[min(len(px) - 1, b + 365)]:,.0f})")

    # shape match
    L = b - a
    ref = np.log(w / w[0])
    rz = (ref - ref.mean()) / ref.std()
    res = []
    for s in range(idx['2016-10-01'], len(px) - L):
        x = np.log(px[s:s + L + 1] / px[s])
        if x.std() == 0:
            continue
        corr = float(np.mean(rz * (x - x.mean()) / x.std()))
        res.append((corr, s))
    res.sort(reverse=True)
    picked = []
    for corr, s in res:
        if all(abs(s - t) > 180 for _, t in picked):
            picked.append((corr, s))
        if len(picked) == 6:
            break
    print("\nShape match: the 12-month stretches since Oct 2016 most like Oct 2015 - Oct 2016")
    print(f"  {'window':25} {'match':>5} {'change':>7} {'worst':>6} | {'next 6m':>8} {'next 12m':>8} | position vs halving")
    for corr, s in sorted(picked, key=lambda x: x[1]):
        e = s + L
        x = px[s:e + 1]
        nxt6 = px[e + 182] / px[e] - 1 if e + 182 < len(px) else None
        nxt12 = px[e + 365] / px[e] - 1 if e + 365 < len(px) else None
        hv = min(HALVINGS, key=lambda h: abs(days_from(dates[e], h)))
        print(f"  {dates[s]} → {dates[e]} {corr:5.2f} {x[-1] / x[0] - 1:+7.0%} {np.min(x / np.maximum.accumulate(x) - 1):6.0%} | "
              f"{(f'{nxt6:+.0%}' if nxt6 is not None else 'n/a'):>8} {(f'{nxt12:+.0%}' if nxt12 is not None else 'n/a'):>8} | "
              f"ends {days_from(dates[e], hv):+d} days from the {hv} halving")
    print(f"  (all {len(res)} windows: average match {np.mean([c for c, _ in res]):.2f}; "
          f"{np.mean([c > 0.8 for c, _ in res]):.0%} of them above 0.80)")

    # does a close match predict a big move? compare with every window (the base rate)
    def fut(e):
        if e + 365 >= len(px):
            return None
        f = px[e:e + 366] / px[e]
        return f[-1] - 1, f.max() - 1, f.min() - 1
    rows = [(c, fut(s + L)) for c, s in res]
    rows = [(c, f) for c, f in rows if f]
    print("\nDoes looking like 2015-16 mean a big move is coming? Next 12 months after each window's end:")
    print(f"  {'windows':28} {'n':>5} {'avg end':>8} {'median':>7} {'best rise inside':>17} {'up 100%+ at some point':>23} {'fell 50%+ at some point':>24}")
    for lab, lo, hi in (('match 0.90+', 0.90, 9), ('match 0.80-0.90', 0.80, 0.90), ('match 0.50-0.80', 0.5, 0.8),
                        ('match below 0.50', -9, 0.5), ('ALL windows (base rate)', -9, 9)):
        sel = [f for c, f in rows if lo <= c < hi]
        if not sel:
            continue
        e12, mx, mn = (np.array([f[k] for f in sel]) for k in range(3))
        print(f"  {lab:28} {len(sel):5} {e12.mean():+8.0%} {np.median(e12):+7.0%} {np.median(mx):+17.0%} {np.mean(mx >= 1):23.0%} {np.mean(mn <= -0.5):24.0%}")
    print("  (windows overlap day by day, so counts are not independent - the few separate episodes above matter more)")

    # cycle match
    print("\nCycle match: the same days around later halvings (window = halving -282 to +84 days)")
    for h in HALVINGS[1:]:
        s_d = (date.fromisoformat(h) - timedelta(days=282)).isoformat()
        e_d = (date.fromisoformat(h) + timedelta(days=84)).isoformat()
        s = next(i for i, d in enumerate(dates) if d >= s_d)
        e = next((i for i, d in enumerate(dates) if d >= e_d), None)
        if e is None:
            continue
        x = px[s:e + 1]
        xr = np.log(x / x[0])
        xr = np.interp(np.linspace(0, len(xr) - 1, L + 1), np.arange(len(xr)), xr)
        corr = float(np.mean(rz * (xr - xr.mean()) / xr.std()))
        nxt12 = px[e + 365] / px[e] - 1 if e + 365 < len(px) else None
        top = int(np.argmax(px[e:e + 600])) + e if e < len(px) else e
        print(f"  {dates[s]} → {dates[e]}: {x[-1] / x[0] - 1:+.0%}, worst {np.min(x / np.maximum.accumulate(x) - 1):.0%}, "
              f"shape match {corr:.2f}, next 12 months {f'{nxt12:+.0%}' if nxt12 is not None else 'n/a'}, "
              f"cycle top {dates[top]} ${px[top]:,.0f} ({px[top] / px[e] - 1:+.0%} from window end)")

    # the last 12 months
    e = len(px) - 1
    s = e - L
    x = np.log(px[s:] / px[s])
    corr = float(np.mean(rz * (x - x.mean()) / x.std()))
    print(f"\nLast 12 months {dates[s]} → {dates[e]}: ${px[s]:,.0f} → ${px[e]:,.0f} ({px[e] / px[s] - 1:+.0%}), "
          f"worst {np.min(px[s:] / np.maximum.accumulate(px[s:]) - 1):.0%}, shape match with 2015-16 {corr:.2f}")
    print(f"  now ${px[e]:,.0f} vs 200-day average ${ma200[e]:,.0f} ({px[e] / ma200[e] - 1:+.0%}); "
          f"all-time high ${px.max():,.0f} on {dates[int(np.argmax(px))]} ({px[e] / px.max() - 1:+.0%}); "
          f"{days_from(dates[e], '2024-04-20')} days after the 2024 halving "
          f"(2015-16 window ended {days_from(B, '2016-07-09')} days after its halving)")
    for h, top in (('2016-07-09', '2017-12-17'), ('2020-05-11', '2021-11-10')):
        print(f"  past cycle: halving {h} → top {top} = {days_from(top, h)} days")
    print("  past cycle tops → bottoms: 2017-12-17 → 2018-12-15 (-84%), 2021-11-10 → 2022-11-21 (-77%)")


if __name__ == '__main__':
    main()
